package xiaozhi.modules.device.service.impl;

import java.util.ArrayList;
import java.util.Date;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;

import org.apache.commons.lang3.StringUtils;
import org.springframework.stereotype.Service;

import com.baomidou.mybatisplus.core.conditions.query.QueryWrapper;

import lombok.AllArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import xiaozhi.common.exception.ErrorCode;
import xiaozhi.common.exception.RenException;
import xiaozhi.common.utils.JsonUtils;
import xiaozhi.modules.device.dao.DeviceConfigDao;
import xiaozhi.modules.device.entity.DeviceConfigEntity;
import xiaozhi.common.utils.WakeWordPinyinUtils;
import xiaozhi.modules.device.entity.DeviceEntity;
import xiaozhi.modules.device.service.DeviceConfigService;
import xiaozhi.modules.device.service.DeviceService;

/**
 * 设备云端配置服务实现（B线，design §3.2/§5.1/§5.2）
 * - 白名单契约源：design §5.2（与 Python 侧 DEVICE_CONFIG_TOOL_RULES 以交集生效）
 * - 上报校验：key 必须在白名单，值须为 int 0-100（theme 为 P1 预留，暂不收）
 * - 宽松策略：非法键/越界值忽略并告警日志，合法键照常落库，不让一次脏数据丢整包
 */
@Slf4j
@Service
@AllArgsConstructor
public class DeviceConfigServiceImpl implements DeviceConfigService {

    /** 配置键白名单（design §5.1 schema：volume/brightness；wake_word 动态唤醒词；
     *  wake_word_display 唤醒词展示原文；wake_word_threshold 唤醒词灵敏度 0~100
     *  （0=最灵敏，固件夹取到 esp-sr 最低有效值）；interrupt_threshold 实时打断灵敏度
     *  0~100（0=最容易打断）；theme P1 预留不收） */
    private static final Set<String> CONFIG_KEYS = Set.of(
            "volume", "brightness", "wake_word", "wake_word_display",
            "wake_word_threshold", "interrupt_threshold");

    /** 数值型配置键的合法范围（闭区间） */
    private static final int VALUE_MIN = 0;
    private static final int VALUE_MAX = 100;

    /** 唤醒词条数上限（设备 MultiNet 契约） */
    private static final int WAKE_WORD_MAX_COUNT = 5;

    private final DeviceConfigDao deviceConfigDao;
    private final DeviceService deviceService;

    @Override
    public DeviceConfigEntity getByDeviceId(String deviceId) {
        if (StringUtils.isBlank(deviceId)) {
            return null;
        }
        return deviceConfigDao.selectById(deviceId);
    }

    @Override
    public void upsertByMac(String macAddress, Map<String, Object> config) {
        if (StringUtils.isBlank(macAddress)) {
            throw new RenException(ErrorCode.PARAMS_GET_ERROR);
        }
        if (config == null || config.isEmpty()) {
            throw new RenException(ErrorCode.PARAMS_GET_ERROR);
        }
        // MAC 定位设备（找不到直接报错，不落库，design §3.2：PARAMS_GET_ERROR）
        DeviceEntity device = deviceService.getDeviceByMacAddress(macAddress);
        if (device == null) {
            throw new RenException(ErrorCode.PARAMS_GET_ERROR);
        }
        // 白名单 + 范围校验，提取本次合法增量
        Map<String, Object> delta = sanitizeConfig(macAddress, config);
        if (delta.isEmpty()) {
            // 全部键非法：告警已记录，无内容可写，视为成功返回（宽松策略）
            return;
        }
        upsert(device.getId(), delta);
    }

    /**
     * 白名单过滤 + 值域校验：非法键/越界值忽略并告警日志
     */
    private Map<String, Object> sanitizeConfig(String macAddress, Map<String, Object> config) {
        Map<String, Object> delta = new LinkedHashMap<>();
        for (Map.Entry<String, Object> entry : config.entrySet()) {
            String key = entry.getKey();
            Object value = entry.getValue();
            if (!CONFIG_KEYS.contains(key)) {
                log.warn("[device-config] 忽略非法配置键: mac={}, key={}", macAddress, key);
                continue;
            }
            // 唤醒词命令 / 展示文本：字符串或字符串数组，按下标配对，不走数值校验
            if ("wake_word".equals(key) || "wake_word_display".equals(key)) {
                Object sanitizedWake = sanitizeWakeWord(macAddress, key, value);
                if (sanitizedWake != null) {
                    delta.put(key, sanitizedWake);
                }
                continue;
            }
            Integer intValue = toIntValue(value);
            if (intValue == null || intValue < VALUE_MIN || intValue > VALUE_MAX) {
                log.warn("[device-config] 忽略越界配置值: mac={}, key={}, value={}", macAddress, key, value);
                continue;
            }
            delta.put(key, intValue);
        }
        return delta;
    }

    /**
     * 唤醒词值校验：单串 trim 后返回；数组 ≤5 项返回 List。
     * 长度上限按键区分：wake_word（拼音）{@link WakeWordPinyinUtils#MAX_PINYIN_LENGTH}、
     * wake_word_display（汉字）{@link WakeWordPinyinUtils#MAX_DISPLAY_LENGTH}。
     * <p><b>数组保留位置</b>：非法项留空串占位，绝不压缩——wake_word 与
     * wake_word_display 按下标配对，压缩会让"第 2 个词"配上"第 3 个词"的展示文案。
     * 空占位由下发侧成对剔除。全空视为非法整体返回 null。
     */
    private Object sanitizeWakeWord(String macAddress, String key, Object value) {
        final int maxLen = "wake_word_display".equals(key)
                ? WakeWordPinyinUtils.MAX_DISPLAY_LENGTH
                : WakeWordPinyinUtils.MAX_PINYIN_LENGTH;
        if (value instanceof String s) {
            String t = s.trim();
            if (t.isEmpty() || t.length() > maxLen) {
                log.warn("[device-config] 忽略非法{}: mac={}, len={}", key, macAddress, t.length());
                return null;
            }
            return t;
        }
        if (value instanceof List<?> list) {
            if (list.isEmpty() || list.size() > WAKE_WORD_MAX_COUNT) {
                log.warn("[device-config] 忽略非法{}数组: mac={}, count={}", key, macAddress, list.size());
                return null;
            }
            List<String> words = new ArrayList<>(list.size());
            boolean anyValid = false;
            for (Object w : list) {
                if (w instanceof String s) {
                    String t = s.trim();
                    if (!t.isEmpty() && t.length() <= maxLen) {
                        words.add(t);
                        anyValid = true;
                        continue;
                    }
                }
                words.add("");  // 保留位置占位
            }
            if (!anyValid) {
                return null;
            }
            return words;
        }
        log.warn("[device-config] 忽略非法{}类型: mac={}, type={}", key, macAddress,
                value == null ? "null" : value.getClass().getSimpleName());
        return null;
    }

    /**
     * 值必须是整数（或整数值的数字，如 80.0），布尔/字符串等一律拒绝
     */
    private Integer toIntValue(Object value) {
        if (value instanceof Integer) {
            return (Integer) value;
        }
        if (value instanceof Number) {
            double d = ((Number) value).doubleValue();
            if (d == Math.rint(d) && !Double.isInfinite(d)) {
                return (int) d;
            }
            return null;
        }
        return null;
    }

    /**
     * 原子 upsert（P1-6）：单条 INSERT ... ON DUPLICATE KEY UPDATE + JSON_MERGE_PATCH，
     * 由数据库完成「不存在则插入，存在则增量合并」，消除原「读-改-写 LWW」的并发覆盖问题。
     * 幂等语义保持：delta 与旧值相同则 JSON_MERGE_PATCH 结果不变，不产生 diff。
     * 建表 config_json 为 NOT NULL 且插入时即写入 JSON，故不存在 NULL 旧值需特判
     * （若未来出现 NULL 旧值，JSON_MERGE_PATCH(NULL, x)=x 也天然成立）。
     * 设备上报无操作人上下文，creator/updater 置 null；create_date 列默认 NULL 不在本语句内维护。
     */
    private void upsert(String deviceId, Map<String, Object> delta) {
        String deltaJson = JsonUtils.toJsonString(delta);
        Date now = new Date();
        deviceConfigDao.upsertMergePatch(deviceId, deltaJson, null, null, null, now);
    }
}

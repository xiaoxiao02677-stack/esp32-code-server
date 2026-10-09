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

    /** 配置键白名单（design §5.1 schema：volume/brightness；wake_word 动态唤醒词；theme P1 预留不收） */
    private static final Set<String> CONFIG_KEYS = Set.of("volume", "brightness", "wake_word");

    /** 数值型配置键的合法范围（闭区间） */
    private static final int VALUE_MIN = 0;
    private static final int VALUE_MAX = 100;

    /** 唤醒词长度上限（字符）；数组形式最多词数 */
    private static final int WAKE_WORD_MAX_LEN = 32;
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
            // wake_word：字符串或字符串数组（长度/数量上限校验），不走数值校验
            if ("wake_word".equals(key)) {
                Object sanitizedWake = sanitizeWakeWord(macAddress, value);
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
     * 唤醒词值校验：单串 ≤32 字符 trim 后返回；数组 ≤5 项×每项 ≤32 字符返回 List；
     * 非法（空/超限/类型不符）返回 null 并告警
     */
    private Object sanitizeWakeWord(String macAddress, Object value) {
        if (value instanceof String s) {
            String t = s.trim();
            if (t.isEmpty() || t.length() > WAKE_WORD_MAX_LEN) {
                log.warn("[device-config] 忽略非法唤醒词: mac={}, len={}", macAddress, t.length());
                return null;
            }
            return t;
        }
        if (value instanceof List<?> list) {
            if (list.isEmpty() || list.size() > WAKE_WORD_MAX_COUNT) {
                log.warn("[device-config] 忽略非法唤醒词数组: mac={}, count={}", macAddress, list.size());
                return null;
            }
            List<String> words = new ArrayList<>();
            for (Object w : list) {
                if (w instanceof String s) {
                    String t = s.trim();
                    if (!t.isEmpty() && t.length() <= WAKE_WORD_MAX_LEN) {
                        words.add(t);
                    }
                }
            }
            if (words.isEmpty()) {
                return null;
            }
            return words;
        }
        log.warn("[device-config] 忽略非法唤醒词类型: mac={}, type={}", macAddress,
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

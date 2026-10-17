package xiaozhi.modules.device.service.impl;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.Map;

import org.apache.commons.lang3.StringUtils;
import org.springframework.stereotype.Service;

import lombok.AllArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import xiaozhi.common.constant.Constant;
import xiaozhi.common.utils.JsonUtils;
import xiaozhi.modules.device.entity.DeviceConfigEntity;
import xiaozhi.modules.device.entity.DeviceEntity;
import xiaozhi.modules.device.service.DeviceConfigFileService;
import xiaozhi.modules.device.service.DeviceConfigService;
import xiaozhi.modules.device.service.DeviceService;
import xiaozhi.modules.sys.service.SysParamsService;

/**
 * 设备配置文件服务实现
 *
 * 契约要点：
 * 1. 内容确定性：使用 LinkedHashMap 固定键序，同一份配置多次序列化结果完全一致；
 *    不写入任何时间戳/随机值，避免「内容未变但版本抖动」导致设备反复认为配置已更新。
 * 2. 版本 = 内容 SHA-256 前 12 位十六进制，前缀 cfg-；无状态、可重复计算。
 * 3. 未绑定设备同样返回可用的 version/download_url（内容为服务端端点信息），
 *    避免固件每次启动都拿到 404 而中断配置同步流程。
 */
@Slf4j
@Service
@AllArgsConstructor
public class DeviceConfigFileServiceImpl implements DeviceConfigFileService {

    /** 版本号前缀，便于日志与前端识别 */
    private static final String VERSION_PREFIX = "cfg-";

    /** 摘要截断长度（十六进制字符数） */
    private static final int DIGEST_LEN = 12;

    /** 配置下载端点相对路径（拼接在 server.ota 之后） */
    private static final String DOWNLOAD_PATH = "config/download";

    /** 壁纸子对象键（P1-3：由壁纸下发写入 ai_device_config.config_json） */
    private static final String WALLPAPER_KEY = "wallpaper";

    private final DeviceService deviceService;
    private final DeviceConfigService deviceConfigService;
    private final SysParamsService sysParamsService;

    @Override
    public String buildPayload(String macAddress) {
        Map<String, Object> root = new LinkedHashMap<>();
        root.put("device_id", macAddress);

        Map<String, Object> server = new LinkedHashMap<>();
        server.put("ota", paramValue(Constant.SERVER_OTA));
        server.put("websocket", paramValue(Constant.SERVER_WEBSOCKET));
        root.put("server", server);

        // 设备云端配置（仅已绑定设备才有；未绑定时给空对象，保持结构稳定）
        Map<String, Object> deviceConfig = Collections.emptyMap();
        DeviceEntity device = deviceService.getDeviceByMacAddress(macAddress);
        if (device != null) {
            DeviceConfigEntity entity = deviceConfigService.getByDeviceId(device.getId());
            if (entity != null && StringUtils.isNotBlank(entity.getConfigJson())) {
                try {
                    deviceConfig = JsonUtils.parseMap(entity.getConfigJson());
                } catch (Exception e) {
                    // 库里脏 JSON 不应导致固件拿不到配置，降级为空对象并告警
                    log.warn("[ota-config] 设备云端配置 JSON 解析失败，按空配置下发: mac={}, err={}",
                            macAddress, e.getMessage());
                    deviceConfig = Collections.emptyMap();
                }
            }
        }
        root.put("device_config", normalizeWallpaper(deviceConfig, macAddress));

        return JsonUtils.toJsonString(root);
    }

    /**
     * 壁纸透出（P1-3）：config_json 中的 wallpaper 子对象原样带到 device_config.wallpaper，
     * 固件下次启动即可拿到 url/md5/size/format 并从 /wallpaperMag/download 拉取。
     * 类型异常（脏数据）时丢弃该键并告警，避免整包配置解析失败。
     */
    private Map<String, Object> normalizeWallpaper(Map<String, Object> deviceConfig, String macAddress) {
        if (deviceConfig == null) {
            return Collections.emptyMap();
        }
        Object wallpaper = deviceConfig.get(WALLPAPER_KEY);
        if (wallpaper == null || wallpaper instanceof Map) {
            return deviceConfig;
        }
        log.warn("[ota-config] 壁纸配置类型异常，按无壁纸下发: mac={}, type={}",
                macAddress, wallpaper.getClass().getSimpleName());
        Map<String, Object> copy = new LinkedHashMap<>(deviceConfig);
        copy.remove(WALLPAPER_KEY);
        return copy;
    }

    @Override
    public String buildVersion(String macAddress) {
        String payload = buildPayload(macAddress);
        try {
            MessageDigest digest = MessageDigest.getInstance("SHA-256");
            byte[] hash = digest.digest(payload.getBytes(StandardCharsets.UTF_8));
            StringBuilder sb = new StringBuilder(VERSION_PREFIX);
            for (int i = 0; i < DIGEST_LEN / 2; i++) {
                sb.append(String.format("%02x", hash[i]));
            }
            return sb.toString();
        } catch (Exception e) {
            // 摘要算法不可能缺失；真出现异常时退化为内容长度，保证仍有稳定且可比较的版本号
            log.warn("[ota-config] 计算配置摘要失败，退化使用内容长度: mac={}, err={}",
                    macAddress, e.getMessage());
            return VERSION_PREFIX + payload.length();
        }
    }

    @Override
    public String buildDownloadUrl(String macAddress, String fallbackBase) {
        String base = paramValue(Constant.SERVER_OTA);
        if (StringUtils.isBlank(base)) {
            base = fallbackBase;
        }
        if (StringUtils.isBlank(base)) {
            return "";
        }
        if (!base.endsWith("/")) {
            base = base + "/";
        }
        // MAC 中的冒号在 query 中合法，固件自身也以同样形式传参，保持一致不做转义
        return base + DOWNLOAD_PATH + "?device_id=" + macAddress;
    }

    private String paramValue(String key) {
        String value = sysParamsService.getValue(key, true);
        return StringUtils.isBlank(value) || "null".equals(value) ? "" : value;
    }
}

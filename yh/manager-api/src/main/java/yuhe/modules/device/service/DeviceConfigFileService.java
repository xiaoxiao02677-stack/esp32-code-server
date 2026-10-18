package yuhe.modules.device.service;

/**
 * 设备配置文件服务（OTA 配置下发链路，design: 配置版本检查 + 配置包下载）
 *
 * 固件侧契约（main/ota.cc）：
 *   GET {OTA_URL}/config/version?device_id={MAC}  ->  {"version":"...","download_url":"..."}
 *   与本地 NVS config_version/version 比较，不同则视为配置已变更。
 *
 * 版本号为「配置内容的稳定摘要」：内容不变则版本不变，内容变化版本随之变化，
 * 无需落库、无状态、可重复计算。
 */
public interface DeviceConfigFileService {

    /**
     * 生成设备配置文件内容（确定性 JSON，键序固定）
     *
     * @param macAddress 设备 MAC 地址
     * @return 配置 JSON 字符串
     */
    String buildPayload(String macAddress);

    /**
     * 生成设备配置版本号（配置内容摘要）
     *
     * @param macAddress 设备 MAC 地址
     * @return 形如 cfg-xxxxxxxxxxxx 的版本号
     */
    String buildVersion(String macAddress);

    /**
     * 生成配置包下载地址（绝对 URL，指向本服务的 config/download 端点）
     *
     * @param macAddress 设备 MAC 地址
     * @param fallbackBase 当参数表未配置 server.ota 时的兜底基地址（如 http://host:8002/yuhe/ota/）
     * @return 可被设备直接 GET 的下载地址
     */
    String buildDownloadUrl(String macAddress, String fallbackBase);
}

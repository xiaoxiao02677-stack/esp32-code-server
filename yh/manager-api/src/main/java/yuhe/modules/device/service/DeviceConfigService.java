package yuhe.modules.device.service;

import java.util.Map;

import yuhe.modules.device.entity.DeviceConfigEntity;

/**
 * 设备云端配置服务（B线：配置云端记忆）
 * - 存储仅允许白名单键（design §5.1：volume/brightness，P1 预留 theme）
 * - upsert 语义为「读旧值 → 白名单键合并 → 写回」，非盲覆盖
 */
public interface DeviceConfigService {

    /**
     * 按设备ID查询云端配置
     *
     * @param deviceId 设备ID（ai_device.id）
     * @return 配置实体；无记录时返回 null
     */
    DeviceConfigEntity getByDeviceId(String deviceId);

    /**
     * 按MAC地址定位设备并合并写入配置
     *
     * @param macAddress 设备MAC地址
     * @param config     本次上报的配置（仅白名单键生效，非法键忽略并告警日志）
     */
    void upsertByMac(String macAddress, Map<String, Object> config);
}

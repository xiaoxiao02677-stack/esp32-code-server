package yuhe.modules.device.dto;

import jakarta.validation.constraints.Size;
import lombok.Data;

import java.io.Serializable;

/**
 * 设备 OTA 定向配置 DTO（管理端）。
 *
 * targetOtaId：单台指定 ai_ota 记录 id；空串 = 清除指定（回到轨道逻辑）。
 * otaType：主题轨道（如 yh-154tft-wifi-emopet）；空串 = 跟随设备上报 type。
 * 两个字段都可选，只更新出现的字段（null 跳过）。
 */
@Data
public class DeviceOtaTargetDTO implements Serializable {

    /** 单台指定固件（ai_ota.id；空串=清除） */
    @Size(max = 32)
    private String targetOtaId;

    /** OTA 主题轨道（空串=跟随设备上报 type） */
    @Size(max = 64)
    private String otaType;

    private static final long serialVersionUID = 1L;
}

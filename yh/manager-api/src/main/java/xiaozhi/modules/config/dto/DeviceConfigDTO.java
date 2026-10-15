package xiaozhi.modules.config.dto;

import java.util.Map;

import io.swagger.v3.oas.annotations.media.Schema;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotEmpty;
import lombok.Data;

/**
 * 服务端上报设备配置DTO（xiaozhi-server → manager-api，B线 design §3.2）
 */
@Data
@Schema(description = "服务端上报设备配置DTO")
public class DeviceConfigDTO {

    @NotBlank(message = "设备MAC地址不能为空")
    @Schema(description = "设备MAC地址")
    private String macAddress;

    @NotEmpty(message = "配置内容不能为空")
    @Schema(description = "配置内容（仅白名单键生效：volume/brightness，int 0-100）")
    private Map<String, Object> config;
}

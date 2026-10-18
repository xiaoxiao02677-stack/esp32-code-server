package yuhe.modules.wallpaper.dto;

import java.util.List;

import io.swagger.v3.oas.annotations.media.Schema;
import lombok.Data;

/**
 * 壁纸下发请求（P1-3）
 * targetType=devices 用 deviceIds（ai_device.id）；targetType=group 用 agentIds（ai_agent.id）；
 * targetType=all 忽略两者，取全部设备。applyMode=immediate 即时推送在线设备，
 * next_boot 仅落 ai_device_config，等设备下次启动生效。
 */
@Data
@Schema(description = "壁纸下发请求")
public class WallpaperDispatchDTO {

    @Schema(description = "壁纸ID", requiredMode = Schema.RequiredMode.REQUIRED)
    private String wallpaperId;

    @Schema(description = "目标类型：devices/group/all", requiredMode = Schema.RequiredMode.REQUIRED)
    private String targetType;

    @Schema(description = "目标设备ID列表（targetType=devices）")
    private List<String> deviceIds;

    @Schema(description = "目标智能体ID列表（targetType=group）")
    private List<String> agentIds;

    @Schema(description = "生效方式：immediate/next_boot")
    private String applyMode;
}

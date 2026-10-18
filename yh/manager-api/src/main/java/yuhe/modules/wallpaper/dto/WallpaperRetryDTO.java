package yuhe.modules.wallpaper.dto;

import java.util.List;

import io.swagger.v3.oas.annotations.media.Schema;
import lombok.Data;

/**
 * 壁纸任务重试请求（P1-3）
 * deviceIds 为空时重试该任务下全部未成功（pending/failed/sent）的设备。
 */
@Data
@Schema(description = "壁纸任务重试请求")
public class WallpaperRetryDTO {

    @Schema(description = "需要重试的设备ID列表（ai_device.id），空表示全部未成功设备")
    private List<String> deviceIds;
}

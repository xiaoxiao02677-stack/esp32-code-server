package yuhe.modules.wallpaper.vo;

import java.util.List;

import io.swagger.v3.oas.annotations.media.Schema;
import lombok.Data;

/**
 * 壁纸任务详情（P1-3）
 * 统计值为读取时实时汇总：success/failed 以 Python 写回的 Redis 回执为准，
 * sent 为「在线通道已推送」数量（next_boot 模式下为 0）。
 */
@Data
@Schema(description = "壁纸任务详情")
public class WallpaperTaskDetailVO {

    @Schema(description = "任务ID")
    private String taskId;

    @Schema(description = "壁纸槽位：idle=待机壁纸/boot=开机壁纸")
    private String kind;

    @Schema(description = "任务状态：pending/sent/partial/failed")
    private String status;

    @Schema(description = "目标设备总数")
    private int total;

    @Schema(description = "已推送设备数")
    private int sent;

    @Schema(description = "回执成功数")
    private int success;

    @Schema(description = "失败数")
    private int failed;

    @Schema(description = "设备明细")
    private List<Device> devices;

    @Data
    @Schema(description = "壁纸任务设备明细")
    public static class Device {

        @Schema(description = "设备ID")
        private String deviceId;

        @Schema(description = "设备MAC地址")
        private String mac;

        @Schema(description = "设备状态：pending/sent/failed/applied")
        private String status;

        @Schema(description = "失败原因")
        private String error;
    }
}

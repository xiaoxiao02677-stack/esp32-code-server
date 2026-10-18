package yuhe.modules.wallpaper.entity;

import java.util.Date;

import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;

import io.swagger.v3.oas.annotations.media.Schema;
import lombok.Data;
import lombok.EqualsAndHashCode;

/**
 * 壁纸下发任务设备明细（P1-3）
 * status 取值：pending（待设备下次启动）/sent（在线通道已推送）/failed（推送或回执失败）/applied（设备回执成功）
 */
@Data
@EqualsAndHashCode(callSuper = false)
@TableName("ai_wallpaper_task_device")
@Schema(description = "壁纸下发任务设备明细")
public class WallpaperTaskDeviceEntity {

    @TableId(type = IdType.AUTO)
    @Schema(description = "主键")
    private Long id;

    @Schema(description = "任务ID")
    private String taskId;

    @Schema(description = "设备ID")
    private String deviceId;

    @Schema(description = "设备状态")
    private String status;

    @Schema(description = "失败原因")
    private String error;

    @Schema(description = "设备回执时间")
    private Date ackTime;
}

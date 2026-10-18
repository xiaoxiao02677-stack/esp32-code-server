package yuhe.modules.wallpaper.entity;

import java.util.Date;

import com.baomidou.mybatisplus.annotation.FieldFill;
import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableField;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;

import io.swagger.v3.oas.annotations.media.Schema;
import lombok.Data;
import lombok.EqualsAndHashCode;

/**
 * 壁纸下发任务（P1-3）
 * target_type=devices 时 target_ids 为 ai_device.id 数组；
 * target_type=group 时为 ai_agent.id 数组；all 时为空。
 */
@Data
@EqualsAndHashCode(callSuper = false)
@TableName("ai_wallpaper_task")
@Schema(description = "壁纸下发任务")
public class WallpaperTaskEntity {

    @TableId(type = IdType.ASSIGN_UUID)
    @Schema(description = "任务ID")
    private String id;

    @Schema(description = "壁纸ID")
    private String wallpaperId;

    @Schema(description = "目标类型：devices/group/all")
    private String targetType;

    @Schema(description = "目标ID列表（JSON数组）")
    private String targetIds;

    @Schema(description = "生效方式：immediate/next_boot")
    private String applyMode;

    @Schema(description = "壁纸槽位：idle=待机壁纸/boot=开机壁纸")
    private String kind;

    @Schema(description = "任务状态：pending/sent/partial/failed")
    private String status;

    @Schema(description = "目标设备总数")
    private Integer total;

    @Schema(description = "已成功推送在线通道的设备数")
    private Integer sent;

    @Schema(description = "设备回执成功数")
    private Integer success;

    @Schema(description = "失败数")
    private Integer failed;

    @Schema(description = "创建者")
    @TableField(fill = FieldFill.INSERT)
    private Long creator;

    @Schema(description = "创建时间")
    @TableField(fill = FieldFill.INSERT)
    private Date createDate;
}

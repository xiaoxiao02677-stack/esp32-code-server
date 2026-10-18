package yuhe.modules.device.entity;

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
 * 设备云端配置（B线：配置云端记忆，design §3.1）
 * 一设备一行，config_json 为白名单键的 JSON 对象（design §5.1）
 */
@Data
@EqualsAndHashCode(callSuper = false)
@TableName("ai_device_config")
@Schema(description = "设备云端配置")
public class DeviceConfigEntity {

    @TableId(type = IdType.INPUT)
    @Schema(description = "设备ID（关联 ai_device.id）")
    private String deviceId;

    @Schema(description = "设备配置JSON（如 {\"volume\":80,\"brightness\":60}）")
    private String configJson;

    @Schema(description = "创建者")
    @TableField(fill = FieldFill.INSERT)
    private Long creator;

    @Schema(description = "创建时间")
    @TableField(fill = FieldFill.INSERT)
    private Date createDate;

    @Schema(description = "更新者")
    @TableField(fill = FieldFill.UPDATE)
    private Long updater;

    @Schema(description = "更新时间")
    @TableField(fill = FieldFill.UPDATE)
    private Date updateDate;
}

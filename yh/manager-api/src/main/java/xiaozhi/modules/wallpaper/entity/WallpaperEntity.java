package xiaozhi.modules.wallpaper.entity;

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
 * 壁纸资源（P1-3）
 * 一行对应一份已转码的 RGB565 小端原始像素文件（240x240x2 字节）及其元数据。
 */
@Data
@EqualsAndHashCode(callSuper = false)
@TableName("ai_wallpaper")
@Schema(description = "壁纸资源")
public class WallpaperEntity {

    @TableId(type = IdType.ASSIGN_UUID)
    @Schema(description = "壁纸ID")
    private String id;

    @Schema(description = "壁纸名称")
    private String name;

    @Schema(description = "RGB565 壁纸文件下载地址")
    private String url;

    @Schema(description = "PNG 缩略图地址")
    private String thumbUrl;

    @Schema(description = "RGB565 文件 MD5")
    private String md5;

    @Schema(description = "RGB565 文件字节数")
    private Integer size;

    @Schema(description = "像素宽")
    private Integer width;

    @Schema(description = "像素高")
    private Integer height;

    @Schema(description = "像素格式")
    private String format;

    @Schema(description = "可见范围")
    private String scope;

    @Schema(description = "创建者")
    @TableField(fill = FieldFill.INSERT)
    private Long creator;

    @Schema(description = "创建时间")
    @TableField(fill = FieldFill.INSERT)
    private Date createDate;
}

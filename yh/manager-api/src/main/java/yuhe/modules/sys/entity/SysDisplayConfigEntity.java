package yuhe.modules.sys.entity;

import java.io.Serializable;
import java.util.Date;

import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;

import lombok.Data;

/**
 * 字段展示配置（表 sys_display_config；scope_type 0系统 1角色 2用户）
 */
@Data
@TableName("sys_display_config")
public class SysDisplayConfigEntity implements Serializable {
    @TableId(type = IdType.ASSIGN_ID)
    private Long id;
    private Integer scopeType;
    private Long roleId;
    private Long userId;
    /** JSON 字符串透传：{"fields":{key:{visible,editable}}} */
    private String configJson;
    private Long creator;
    private Date createDate;
    private Long updater;
    private Date updateDate;
}

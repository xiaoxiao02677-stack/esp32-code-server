package yuhe.modules.sys.entity;

import java.io.Serializable;
import java.util.Date;

import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;

import lombok.Data;

/**
 * 用户-角色关联（表 sys_user_role 双环境已存在；雪花 id 主键 + uk(user_id, role_id)）
 */
@Data
@TableName("sys_user_role")
public class SysUserRoleEntity implements Serializable {
    /** 雪花ID（DB 无自增默认值，必须 ASSIGN_ID） */
    @TableId(type = IdType.ASSIGN_ID)
    private Long id;
    private Long userId;
    private Long roleId;
    private Long creator;
    private Date createDate;
    private Long updater;
    private Date updateDate;
}

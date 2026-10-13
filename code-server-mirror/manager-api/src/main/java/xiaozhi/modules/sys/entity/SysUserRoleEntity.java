package xiaozhi.modules.sys.entity;

import com.baomidou.mybatisplus.annotation.TableName;

import lombok.Data;
import lombok.EqualsAndHashCode;
import xiaozhi.common.entity.BaseEntity;

/**
 * 用户角色关联
 */
@Data
@EqualsAndHashCode(callSuper = false)
@TableName("sys_user_role")
public class SysUserRoleEntity extends BaseEntity {
    /**
     * 用户ID（sys_user.id）
     */
    private Long userId;
    /**
     * 角色ID（sys_role.id）
     */
    private Long roleId;
}

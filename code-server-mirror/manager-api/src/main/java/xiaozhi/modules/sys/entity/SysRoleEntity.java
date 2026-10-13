package xiaozhi.modules.sys.entity;

import java.util.Date;

import com.baomidou.mybatisplus.annotation.FieldFill;
import com.baomidou.mybatisplus.annotation.TableField;
import com.baomidou.mybatisplus.annotation.TableName;

import lombok.Data;
import lombok.EqualsAndHashCode;
import xiaozhi.common.entity.BaseEntity;

/**
 * 角色
 */
@Data
@EqualsAndHashCode(callSuper = false)
@TableName("sys_role")
public class SysRoleEntity extends BaseEntity {
    /**
     * 角色编码（唯一，保留码：super_admin/admin/user/readonly）
     */
    private String roleCode;
    /**
     * 角色名称
     */
    private String roleName;
    /**
     * 权限点列表（JSON 数组原文，如 ["admin:user:list"]，Service 层解析）
     */
    private String permissions;
    /**
     * 备注
     */
    private String remark;
    /**
     * 状态 0：停用 1：正常
     */
    private Integer status;
    /**
     * 内置角色 0：否 1：是（内置不可删除、不可改编码/名称/状态）
     */
    private Integer isBuiltin;
    /**
     * 排序
     */
    private Integer sort;
    /**
     * 更新者
     */
    @TableField(fill = FieldFill.INSERT_UPDATE)
    private Long updater;
    /**
     * 更新时间
     */
    @TableField(fill = FieldFill.INSERT_UPDATE)
    private Date updateDate;
}

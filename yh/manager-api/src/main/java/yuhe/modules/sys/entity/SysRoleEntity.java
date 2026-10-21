package yuhe.modules.sys.entity;

import java.io.Serializable;
import java.util.Date;

import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;

import lombok.Data;

/**
 * 系统角色（表 sys_role 双环境已存在）
 */
@Data
@TableName("sys_role")
public class SysRoleEntity implements Serializable {
    @TableId
    private Long id;
    /** 角色编码 */
    private String roleCode;
    /** 角色名称 */
    private String roleName;
    /** 权限点列表 JSON（本模块只读不写，String 透传） */
    private String permissions;
    /** 备注 */
    private String remark;
    /** 状态 0停用 1正常 */
    private Integer status;
    /** 内置角色 0否 1是 */
    private Integer isBuiltin;
    /** 排序 */
    private Integer sort;
    private Long creator;
    /** 创建时间 */
    private Date createDate;
    private Long updater;
    private Date updateDate;
}

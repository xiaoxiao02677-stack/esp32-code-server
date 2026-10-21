package yuhe.modules.sys.entity;

import java.util.Date;

import com.baomidou.mybatisplus.annotation.FieldFill;
import com.baomidou.mybatisplus.annotation.TableField;
import com.baomidou.mybatisplus.annotation.TableName;

import lombok.Data;
import lombok.EqualsAndHashCode;
import yuhe.common.entity.BaseEntity;

/**
 * 系统用户
 */
@Data
@EqualsAndHashCode(callSuper = false)
@TableName("sys_user")
public class SysUserEntity extends BaseEntity {
    /**
     * 用户名
     */
    private String username;
    /**
     * 密码
     */
    private String password;
    /**
     * 超级管理员 0：否 1：是
     */
    private Integer superAdmin;
    /**
     * 状态 0：停用 1：正常
     */
    private Integer status;
    /**
     * 软删除 0：正常 1：已删除（DB 列已存在，历史建表未映射）
     */
    private Integer deleted;
    /**
     * 删除时间
     */
    private Date deletedDate;
    /**
     * 锁定 0：未锁 1：已锁定
     */
    private Integer locked;
    /**
     * 最后登录时间
     */
    private Date lastLoginDate;
    /**
     * 下次登录须改密 0/1
     */
    private Integer mustChangePwd;
    /**
     * 密码更新时间
     */
    private Date pwdUpdateDate;
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
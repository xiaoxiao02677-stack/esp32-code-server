package xiaozhi.common.user;

import java.io.Serializable;
import java.util.ArrayList;
import java.util.List;

import lombok.Data;

/**
 * 登录用户信息
 * Copyright (c) 人人开源 All rights reserved.
 * Website: https://www.renren.io
 */
@Data
public class UserDetail implements Serializable {
    private Long id;
    private String username;
    private Integer superAdmin;
    private String token;
    private Integer status;
    /** 用户角色编码列表（sys_role.role_code，如 super_admin/admin/user/readonly），无角色为空列表 */
    private List<String> roles = new ArrayList<>();
    /** 是否需要强制修改密码（管理员新建/重置密码后置 1） */
    private Integer mustChangePwd;
    /** 最后登录时间（yyyy-MM-dd HH:mm:ss 字符串） */
    private String lastLoginDate;
}
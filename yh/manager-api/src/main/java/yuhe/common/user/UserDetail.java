package yuhe.common.user;

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
    /** 角色码列表（sys_role.role_code，认证时填充）；前端 hasAdminRole/isModuleVisible 消费 */
    private List<String> roles = new ArrayList<>();
}

package yuhe.modules.security.oauth2;

import java.util.ArrayList;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;

import org.apache.shiro.authc.AuthenticationException;
import org.apache.shiro.authc.AuthenticationInfo;
import org.apache.shiro.authc.AuthenticationToken;
import org.apache.shiro.authc.DisabledAccountException;
import org.apache.shiro.authc.IncorrectCredentialsException;
import org.apache.shiro.authc.LockedAccountException;
import org.apache.shiro.authc.SimpleAuthenticationInfo;
import org.apache.shiro.authz.AuthorizationInfo;
import org.apache.shiro.authz.SimpleAuthorizationInfo;
import org.apache.shiro.realm.AuthorizingRealm;
import org.apache.shiro.subject.PrincipalCollection;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.context.annotation.Lazy;
import org.springframework.stereotype.Component;

import jakarta.annotation.Resource;
import yuhe.common.exception.ErrorCode;
import yuhe.common.user.UserDetail;
import yuhe.common.utils.ConvertUtils;
import yuhe.common.utils.MessageUtils;
import yuhe.modules.security.entity.SysUserTokenEntity;
import yuhe.modules.security.service.ShiroService;
import yuhe.modules.sys.entity.SysUserEntity;
import yuhe.modules.sys.enums.SuperAdminEnum;
import yuhe.modules.sys.service.SysAdminModuleService;

/**
 * 认证
 * Copyright (c) 人人开源 All rights reserved.
 * Website: https://www.renren.io
 */
@Component
public class Oauth2Realm extends AuthorizingRealm {
    @Lazy
    @Resource
    private ShiroService shiroService;

    @Lazy
    @Resource
    private SysAdminModuleService sysAdminModuleService;

    private static final Logger logger = LoggerFactory.getLogger(Oauth2Realm.class);

    @Override
    public boolean supports(AuthenticationToken token) {
        return token instanceof Oauth2Token;
    }

    /**
     * 授权(验证权限时调用)
     *
     * 权限码发放规则：
     * 1. 所有登录用户 → sys:role:normal
     * 2. 超管 → sys:role:superAdmin（保留旧语义，/admin 注解兜底）
     * 3. 非超管 → 按其生效展示配置（系统→角色→用户三层合并）中 visible:true 的管理模块
     *    逐个发放模块级权限码 admin:<模块>（/admin/users → admin:users）。
     *    展示配置页勾选的「可见模块」由此真正作用于接口层。
     */
    @Override
    protected AuthorizationInfo doGetAuthorizationInfo(PrincipalCollection principals) {
        UserDetail user = (UserDetail) principals.getPrimaryPrincipal();

        // 用户权限列表
        Set<String> permsSet = new HashSet<>();

        if (user.getSuperAdmin() == SuperAdminEnum.YES.value()) {
            permsSet.add("sys:role:superAdmin");
            permsSet.add("sys:role:normal");
        } else {
            permsSet.add("sys:role:normal");
            // 模块级权限：按生效展示配置的可见管理模块发放
            collectModulePerms(user.getId(), permsSet);
        }

        SimpleAuthorizationInfo info = new SimpleAuthorizationInfo();
        info.setStringPermissions(permsSet);
        return info;
    }

    /**
     * 展示配置 modules 的 key 是管理端路由前缀（如 /admin/users），
     * 转成模块权限码 admin:users 发放给普通用户。
     */
    private void collectModulePerms(Long userId, Set<String> permsSet) {
        if (userId == null) {
            return;
        }
        try {
            Map<String, Object> cfg = sysAdminModuleService.mergedDisplayConfig(userId);
            Object modulesObj = cfg == null ? null : cfg.get("modules");
            if (!(modulesObj instanceof Map)) {
                return;
            }
            for (Object keyObj : ((Map<?, ?>) modulesObj).keySet()) {
                String path = String.valueOf(keyObj);
                if (!path.startsWith("/admin/")) {
                    continue;
                }
                Object v = ((Map<?, ?>) modulesObj).get(keyObj);
                boolean visible = !(v instanceof Map) || !Boolean.FALSE.equals(((Map<?, ?>) v).get("visible"));
                if (!visible) {
                    continue;
                }
                String module = path.substring("/admin/".length());
                if (!module.isEmpty() && !module.contains("/")) {
                    permsSet.add("admin:" + module);
                }
            }
        } catch (Exception e) {
            logger.warn("模块权限码发放失败 userId={}: {}", userId, e.getMessage());
        }
    }

    /**
     * 认证(登录时调用)
     */
    @Override
    protected AuthenticationInfo doGetAuthenticationInfo(AuthenticationToken token) throws AuthenticationException {
        String accessToken = (String) token.getPrincipal();

        // 根据accessToken，查询用户信息
        SysUserTokenEntity tokenEntity = shiroService.getByToken(accessToken);
        // token失效
        if (tokenEntity == null || tokenEntity.getExpireDate().getTime() < System.currentTimeMillis()) {
            throw new IncorrectCredentialsException(MessageUtils.getMessage(ErrorCode.TOKEN_INVALID));
        }

        // 查询用户信息
        SysUserEntity userEntity = shiroService.getUser(tokenEntity.getUserId());

        // 转换成UserDetail对象
        UserDetail userDetail = ConvertUtils.sourceToTarget(userEntity, UserDetail.class);

        userDetail.setToken(accessToken);

        // 账号锁定
        if (userDetail.getStatus() == null) {
            logger.error("账号状态异常，status 不能为空");
            throw new DisabledAccountException(MessageUtils.getMessage(ErrorCode.ACCOUNT_DISABLE));
        }

        if (userDetail.getStatus() == 0) {
            throw new LockedAccountException(MessageUtils.getMessage(ErrorCode.ACCOUNT_LOCK));
        }

        // 角色码（前端 hasAdminRole/管理端准入判定数据源；roles 为空列表时不影响超管位判定）
        List<String> roleCodes = shiroService.getRoleCodes(userDetail.getId());
        userDetail.setRoles(roleCodes == null ? new ArrayList<>() : roleCodes);

        SimpleAuthenticationInfo info = new SimpleAuthenticationInfo(userDetail, accessToken, getName());
        return info;
    }

}

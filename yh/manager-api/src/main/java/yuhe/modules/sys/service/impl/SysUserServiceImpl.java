package yuhe.modules.sys.service.impl;

import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Random;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

import org.apache.commons.lang3.StringUtils;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import com.baomidou.mybatisplus.core.conditions.query.QueryWrapper;
import com.baomidou.mybatisplus.core.metadata.IPage;

import lombok.AllArgsConstructor;
import yuhe.common.constant.Constant;
import yuhe.common.exception.ErrorCode;
import yuhe.common.exception.RenException;
import yuhe.modules.security.user.SecurityUser;
import yuhe.common.page.PageData;
import yuhe.common.service.impl.BaseServiceImpl;
import yuhe.common.utils.ConvertUtils;
import yuhe.modules.agent.service.AgentService;
import yuhe.modules.device.service.DeviceService;
import yuhe.modules.security.password.PasswordUtils;
import yuhe.modules.sys.dao.SysUserDao;
import yuhe.modules.sys.dao.SysRoleDao;
import yuhe.modules.sys.dao.SysUserRoleDao;
import yuhe.modules.sys.dto.AdminPageUserDTO;
import yuhe.modules.sys.dto.AdminUserCreateDTO;
import yuhe.modules.sys.dto.AdminUserImportItemDTO;
import yuhe.modules.sys.dto.AdminUserRolesDTO;
import yuhe.modules.sys.dto.PasswordDTO;
import yuhe.modules.sys.dto.SysUserDTO;
import yuhe.modules.sys.entity.SysUserEntity;
import yuhe.modules.sys.entity.SysRoleEntity;
import yuhe.modules.sys.entity.SysUserRoleEntity;
import yuhe.modules.sys.enums.SuperAdminEnum;
import yuhe.modules.sys.service.SysParamsService;
import yuhe.modules.sys.service.SysUserService;
import yuhe.modules.sys.vo.AdminPageUserVO;

/**
 * 系统用户
 */
@AllArgsConstructor
@Service
public class SysUserServiceImpl extends BaseServiceImpl<SysUserDao, SysUserEntity> implements SysUserService {
    private final SysUserDao sysUserDao;

    private final DeviceService deviceService;

    private final AgentService agentService;

    private final SysParamsService sysParamsService;

    @Override
    public SysUserDTO getByUsername(String username) {
        QueryWrapper<SysUserEntity> queryWrapper = new QueryWrapper<>();
        queryWrapper.eq("username", username);
        List<SysUserEntity> users = sysUserDao.selectList(queryWrapper);
        if (users == null || users.isEmpty()) {
            return null;
        }
        SysUserEntity entity = users.get(0);
        return ConvertUtils.sourceToTarget(entity, SysUserDTO.class);
    }

    @Override
    public SysUserDTO getByUserId(Long userId) {
        SysUserEntity sysUserEntity = sysUserDao.selectById(userId);

        return ConvertUtils.sourceToTarget(sysUserEntity, SysUserDTO.class);
    }

    @Override
    @Transactional(rollbackFor = Exception.class)
    public void save(SysUserDTO dto) {
        SysUserEntity entity = ConvertUtils.sourceToTarget(dto, SysUserEntity.class);

        // 密码强度
        if (!isStrongPassword(entity.getPassword())) {
            throw new RenException(ErrorCode.PASSWORD_WEAK_ERROR);
        }

        // 密码加密
        String password = PasswordUtils.encode(entity.getPassword());
        entity.setPassword(password);

        // 保存用户
        Long userCount = getUserCount();
        if (userCount == 0) {
            entity.setSuperAdmin(SuperAdminEnum.YES.value());
        } else {
            entity.setSuperAdmin(SuperAdminEnum.NO.value());
        }
        entity.setStatus(1);

        insert(entity);
    }

    @Override
    @Transactional(rollbackFor = Exception.class)
    public void deleteById(Long id) {
        // 删除用户
        baseDao.deleteById(id);
        // 删除设备
        deviceService.deleteByUserId(id);
        // 删除智能体
        agentService.deleteAgentByUserId(id);
    }

    @Override
    @Transactional(rollbackFor = Exception.class)
    public void changePassword(Long userId, PasswordDTO passwordDTO) {
        SysUserEntity sysUserEntity = sysUserDao.selectById(userId);

        if (null == sysUserEntity) {
            throw new RenException(ErrorCode.TOKEN_INVALID);
        }

        // 判断旧密码是否正确
        if (!PasswordUtils.matches(passwordDTO.getPassword(), sysUserEntity.getPassword())) {
            throw new RenException(ErrorCode.OLD_PASSWORD_ERROR);
        }

        // 新密码强度
        if (!isStrongPassword(passwordDTO.getNewPassword())) {
            throw new RenException(ErrorCode.PASSWORD_WEAK_ERROR);
        }

        // 密码加密
        String password = PasswordUtils.encode(passwordDTO.getNewPassword());
        sysUserEntity.setPassword(password);

        updateById(sysUserEntity);
    }

    @Override
    @Transactional(rollbackFor = Exception.class)
    public void changePasswordDirectly(Long userId, String password) {
        // 新密码强度
        if (!isStrongPassword(password)) {
            throw new RenException(ErrorCode.PASSWORD_WEAK_ERROR);
        }
        SysUserEntity sysUserEntity = new SysUserEntity();
        sysUserEntity.setId(userId);
        sysUserEntity.setPassword(PasswordUtils.encode(password));
        updateById(sysUserEntity);
    }

    @Override
    @Transactional(rollbackFor = Exception.class)
    public String resetPassword(Long userId) {
        String password = generatePassword();
        changePasswordDirectly(userId, password);
        return password;
    }

    private Long getUserCount() {
        QueryWrapper<SysUserEntity> queryWrapper = new QueryWrapper<>();
        return baseDao.selectCount(queryWrapper);
    }

    @Override
    public PageData<AdminPageUserVO> page(AdminPageUserDTO dto) {
        Map<String, Object> params = new HashMap<String, Object>();
        params.put(Constant.PAGE, dto.getPage());
        params.put(Constant.LIMIT, dto.getLimit());
        // console-v2 传 keyword（匹配用户名）；AdminPageUserDTO 的 mobile 字段同名语义
        IPage<SysUserEntity> page = baseDao.selectPage(
                getPage(params, "id", true),
                new QueryWrapper<SysUserEntity>().like(StringUtils.isNotBlank(dto.getMobile()), "username",
                        dto.getMobile()));
        // 循环处理page获取回来的数据，返回需要的字段
        List<AdminPageUserVO> list = page.getRecords().stream().map(user -> {
            AdminPageUserVO adminPageUserVO = new AdminPageUserVO();
            adminPageUserVO.setUserid(user.getId().toString());
            adminPageUserVO.setMobile(user.getUsername());
            String deviceCount = deviceService.selectCountByUserId(user.getId()).toString();
            adminPageUserVO.setDeviceCount(deviceCount);
            adminPageUserVO.setStatus(user.getStatus());
            adminPageUserVO.setCreateDate(user.getCreateDate());
            return adminPageUserVO;
        }).toList();
        return new PageData<>(list, page.getTotal());
    }

    @Override
    public PageData<yuhe.modules.sys.vo.AdminUserListVO> adminPage(java.util.Map<String, Object> params) {
        String pageStr = (String) params.get(Constant.PAGE);
        String limitStr = (String) params.get(Constant.LIMIT);
        String keyword = (String) params.get("keyword");
        int deleted = params.get("deleted") == null ? 0
                : Integer.parseInt(String.valueOf(params.get("deleted")));

        Map<String, Object> pageParams = new HashMap<>();
        pageParams.put(Constant.PAGE, pageStr);
        pageParams.put(Constant.LIMIT, limitStr);

        QueryWrapper<SysUserEntity> qw = new QueryWrapper<>();
        qw.eq("deleted", deleted);
        qw.like(StringUtils.isNotBlank(keyword), "username", keyword);
        // 按角色过滤（角色分组视图）：EXISTS 子查询命中该角色的用户
        String roleIdStr = params.get("roleId") == null ? null : String.valueOf(params.get("roleId"));
        if (StringUtils.isNotBlank(roleIdStr)) {
            qw.exists("SELECT 1 FROM sys_user_role ur WHERE ur.user_id = sys_user.id AND ur.role_id = {0}",
                    Long.parseLong(roleIdStr));
        }
        // 列排序（表头点击）：前端字段名 → DB 列名白名单，防 SQL 注入；
        // 排序统一走 QueryWrapper（避免 Page OrderItem 与 wrapper 拼接顺序歧义），id 作稳定次序
        String sort = String.valueOf(params.getOrDefault("sort", ""));
        String order = String.valueOf(params.getOrDefault("order", ""));
        java.util.Map<String, String> sortWhiteList = java.util.Map.of(
                "username", "username",
                "status", "status",
                "lastLoginDate", "last_login_date",
                "createDate", "create_date");
        if (sortWhiteList.containsKey(sort)) {
            boolean asc = "asc".equalsIgnoreCase(order);
            qw.orderBy(true, asc, sortWhiteList.get(sort));
        }
        qw.orderByDesc("id");
        IPage<SysUserEntity> page = baseDao.selectPage(getPage(pageParams, null, false), qw);

        // 角色名批量装配（避免 N+1：一次拉全量 user_role + role 内存映射）
        List<Long> userIds = page.getRecords().stream().map(SysUserEntity::getId).toList();
        Map<Long, List<String>> roleNamesByUser = loadRoleNames(userIds);

        List<yuhe.modules.sys.vo.AdminUserListVO> list = page.getRecords().stream().map(u -> {
            yuhe.modules.sys.vo.AdminUserListVO vo = new yuhe.modules.sys.vo.AdminUserListVO();
            vo.setId(u.getId());
            vo.setUsername(u.getUsername());
            vo.setRoleNames(roleNamesByUser.getOrDefault(u.getId(), java.util.Collections.emptyList()));
            vo.setStatus(u.getStatus());
            vo.setLocked(u.getLocked());
            vo.setDeleted(u.getDeleted());
            vo.setDeviceCount(deviceService.selectCountByUserId(u.getId()));
            vo.setLastLoginDate(u.getLastLoginDate());
            vo.setCreateDate(u.getCreateDate());
            return vo;
        }).toList();
        return new PageData<>(list, page.getTotal());
    }

    /** 批量装配用户→角色名映射（user_role join role，两表数据量小，内存映射足够） */
    private Map<Long, List<String>> loadRoleNames(List<Long> userIds) {
        Map<Long, List<String>> map = new HashMap<>();
        if (userIds == null || userIds.isEmpty()) {
            return map;
        }
        List<SysUserRoleEntity> rels = sysUserRoleDao.selectList(
                new QueryWrapper<SysUserRoleEntity>().in("user_id", userIds));
        if (rels.isEmpty()) {
            return map;
        }
        List<Long> roleIds = rels.stream().map(SysUserRoleEntity::getRoleId).distinct().toList();
        Map<Long, String> roleNameById = sysRoleDao.selectBatchIds(roleIds).stream()
                .collect(java.util.stream.Collectors.toMap(SysRoleEntity::getId, SysRoleEntity::getRoleName, (a, b) -> a));
        for (SysUserRoleEntity rel : rels) {
            String name = roleNameById.get(rel.getRoleId());
            if (name != null) {
                map.computeIfAbsent(rel.getUserId(), k -> new java.util.ArrayList<>()).add(name);
            }
        }
        return map;
    }

    private boolean isStrongPassword(String password) {
        // 弱密码的正则表达式
        String weakPasswordRegex = "^(?=.*[0-9])(?=.*[a-z])(?=.*[A-Z]).+$";
        Pattern pattern = Pattern.compile(weakPasswordRegex);
        Matcher matcher = pattern.matcher(password);
        return matcher.matches();
    }

    private static final String CHARACTERS = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789!@#$%^&*()";
    private static final Random random = new Random();

    /**
     * 生成随机密码
     * 
     * @return 随机生成的密码
     */
    private String generatePassword() {
        StringBuilder password = new StringBuilder();

        // 确保包含至少一个数字
        password.append("0123456789".charAt(random.nextInt(10)));
        // 确保包含至少一个小写字母
        password.append("abcdefghijklmnopqrstuvwxyz".charAt(random.nextInt(26)));
        // 确保包含至少一个大写字母
        password.append("ABCDEFGHIJKLMNOPQRSTUVWXYZ".charAt(random.nextInt(26)));
        // 确保包含至少一个特殊符号
        password.append("!@#$%^&*()".charAt(random.nextInt(10)));

        // 生成剩余的8个字符
        for (int i = 4; i < 12; i++) {
            password.append(CHARACTERS.charAt(random.nextInt(CHARACTERS.length())));
        }

        // 打乱密码中字符的顺序
        char[] passwordChars = password.toString().toCharArray();
        for (int i = 0; i < passwordChars.length; i++) {
            int randomIndex = random.nextInt(passwordChars.length);
            char temp = passwordChars[i];
            passwordChars[i] = passwordChars[randomIndex];
            passwordChars[randomIndex] = temp;
        }

        return new String(passwordChars);
    }

    @Override
    @Transactional(rollbackFor = Exception.class)
    public void changeStatus(Integer status, String[] userIds) {
        for (String userId : userIds) {
            // 不许封禁自己（封完自己 token 虽在但登录态被拒，管理页面会"假死"）
            if (status != null && status == 0 && SecurityUser.getUserId() != null
                    && String.valueOf(SecurityUser.getUserId()).equals(userId)) {
                throw new RenException(ErrorCode.USER_BAN_SELF_FORBIDDEN);
            }
            SysUserEntity entity = new SysUserEntity();
            entity.setId(Long.parseLong(userId));
            entity.setStatus(status);
            updateById(entity);
        }
    }

    @Override
    public boolean getAllowUserRegister() {
        String allowUserRegister = sysParamsService.getValue(Constant.SERVER_ALLOW_USER_REGISTER, true);
        if (allowUserRegister.equals("true")) {
            return true;
        }
        Long userCount = baseDao.selectCount(new QueryWrapper<SysUserEntity>());
        if (userCount == 0) {
            return true;
        }
        return false;
    }

    // ===== 管理端用户管理（console-v2 Users.vue 全功能对齐，2026-10-21）=====

    private final yuhe.modules.sys.dao.SysRoleDao sysRoleDao;
    private final yuhe.modules.sys.dao.SysUserRoleDao sysUserRoleDao;
    private final yuhe.modules.security.dao.SysUserTokenDao sysUserTokenDao;

    @Override
    @Transactional(rollbackFor = Exception.class)
    public String adminCreate(AdminUserCreateDTO dto) {
        String username = dto.getUsername().trim();
        // 查重只看未删除用户（同名已删账号在回收站，DB 唯一索引兜底冲突场景极罕见）
        Long sameName = baseDao.selectCount(new QueryWrapper<SysUserEntity>()
                .eq("username", username).eq("deleted", 0));
        if (sameName != null && sameName > 0) {
            throw new RenException(ErrorCode.USER_USERNAME_EXISTS);
        }
        String password = StringUtils.isNotBlank(dto.getPassword()) ? dto.getPassword() : generatePassword();
        if (!isStrongPassword(password)) {
            throw new RenException(ErrorCode.PASSWORD_WEAK_ERROR);
        }
        SysUserEntity entity = new SysUserEntity();
        entity.setUsername(username);
        entity.setPassword(PasswordUtils.encode(password));
        entity.setSuperAdmin(SuperAdminEnum.NO.value());
        entity.setStatus(1);
        entity.setDeleted(0);
        entity.setLocked(0);
        entity.setMustChangePwd(0); // 创建后不强制改密（用户要求：初始密码可直接用）
        insert(entity);
        saveUserRoles(entity.getId(), dto.getRoleIds());
        return password;
    }

    @Override
    public yuhe.modules.sys.vo.AdminUserDetailVO detail(Long userId) {
        SysUserEntity u = sysUserDao.selectById(userId);
        if (u == null || (u.getDeleted() != null && u.getDeleted() == 1)) {
            throw new RenException(ErrorCode.USER_NOT_EXIST);
        }
        yuhe.modules.sys.vo.AdminUserDetailVO vo = new yuhe.modules.sys.vo.AdminUserDetailVO();
        yuhe.modules.sys.vo.AdminUserListVO uv = new yuhe.modules.sys.vo.AdminUserListVO();
        uv.setId(u.getId());
        uv.setUsername(u.getUsername());
        uv.setStatus(u.getStatus());
        uv.setLocked(u.getLocked());
        uv.setDeleted(u.getDeleted());
        uv.setDeviceCount(deviceService.selectCountByUserId(u.getId()));
        uv.setLastLoginDate(u.getLastLoginDate());
        uv.setCreateDate(u.getCreateDate());
        vo.setUser(uv);

        List<Long> roleIds = sysUserRoleDao.selectRoleIdsByUserId(userId);
        if (!roleIds.isEmpty()) {
            sysRoleDao.selectBatchIds(roleIds).forEach(r -> {
                yuhe.modules.sys.vo.AdminUserDetailVO.RoleItem item = new yuhe.modules.sys.vo.AdminUserDetailVO.RoleItem();
                item.setId(r.getId());
                item.setRoleCode(r.getRoleCode());
                item.setRoleName(r.getRoleName());
                vo.getRoles().add(item);
            });
        }
        return vo;
    }

    @Override
    @Transactional(rollbackFor = Exception.class)
    public void assignRoles(AdminUserRolesDTO dto) {
        SysUserEntity u = sysUserDao.selectById(dto.getUserId());
        if (u == null) {
            throw new RenException(ErrorCode.USER_NOT_EXIST);
        }
        // 校验角色 ID 合法
        if (dto.getRoleIds() != null && !dto.getRoleIds().isEmpty()) {
            Long valid = sysRoleDao.selectCount(
                    new QueryWrapper<SysRoleEntity>().in("id", dto.getRoleIds()));
            if (valid != dto.getRoleIds().size()) {
                throw new RenException(ErrorCode.USER_ROLE_NOT_EXIST);
            }
        }
        sysUserRoleDao.deleteByUserId(dto.getUserId());
        saveUserRoles(dto.getUserId(), dto.getRoleIds());
    }

    private void saveUserRoles(Long userId, java.util.List<Long> roleIds) {
        if (roleIds == null || roleIds.isEmpty()) {
            return;
        }
        for (Long roleId : roleIds.stream().distinct().toList()) {
            SysUserRoleEntity rel = new SysUserRoleEntity();
            rel.setUserId(userId);
            rel.setRoleId(roleId);
            rel.setCreateDate(new java.util.Date());
            sysUserRoleDao.insert(rel);
        }
    }

    @Override
    @Transactional(rollbackFor = Exception.class)
    public void softDelete(Long userId, Long operatorId) {
        if (userId.equals(operatorId)) {
            throw new RenException(ErrorCode.USER_DELETE_FORBIDDEN);
        }
        SysUserEntity u = sysUserDao.selectById(userId);
        if (u == null) {
            throw new RenException(ErrorCode.USER_NOT_EXIST);
        }
        if (u.getDeleted() != null && u.getDeleted() == 1) {
            throw new RenException(ErrorCode.USER_ALREADY_DELETED);
        }
        // 最后一个超管不可删（删了就没有人能进管理端）
        if (u.getSuperAdmin() != null && u.getSuperAdmin() == 1) {
            Long superAdminCount = baseDao.selectCount(new QueryWrapper<SysUserEntity>()
                    .eq("super_admin", 1).eq("deleted", 0));
            if (superAdminCount <= 1) {
                throw new RenException(ErrorCode.USER_DELETE_FORBIDDEN);
            }
        }
        SysUserEntity patch = new SysUserEntity();
        patch.setId(userId);
        patch.setDeleted(1);
        patch.setDeletedDate(new java.util.Date());
        updateById(patch);
        // 同步踢下线
        forceLogout(userId);
    }

    @Override
    @Transactional(rollbackFor = Exception.class)
    public void restore(Long userId) {
        SysUserEntity u = sysUserDao.selectById(userId);
        if (u == null) {
            throw new RenException(ErrorCode.USER_NOT_EXIST);
        }
        if (u.getDeleted() == null || u.getDeleted() != 1) {
            throw new RenException(ErrorCode.USER_NOT_EXIST);
        }
        SysUserEntity patch = new SysUserEntity();
        patch.setId(userId);
        patch.setDeleted(0);
        patch.setDeletedDate(null);
        updateById(patch);
    }

    @Override
    @Transactional(rollbackFor = Exception.class)
    public java.util.Map<String, Object> importUsers(java.util.List<AdminUserImportItemDTO> list) {
        List<String> success = new java.util.ArrayList<>();
        List<Map<String, String>> failed = new java.util.ArrayList<>();
        for (AdminUserImportItemDTO item : list) {
            try {
                AdminUserCreateDTO one = new AdminUserCreateDTO();
                one.setUsername(item.getUsername());
                one.setPassword(item.getPassword());
                adminCreate(one);
                success.add(item.getUsername());
            } catch (RenException e) {
                Map<String, String> f = new HashMap<>();
                f.put("username", item.getUsername());
                f.put("reason", e.getMsg());
                failed.add(f);
            }
        }
        if (success.isEmpty() && !failed.isEmpty()) {
            throw new RenException(ErrorCode.USER_IMPORT_ALL_FAIL);
        }
        Map<String, Object> result = new HashMap<>();
        result.put("success", success);
        result.put("failed", failed);
        if (!failed.isEmpty()) {
            // 10225：部分失败，data 携带明细（前端 catch e.data 展示清单）
            RenException ex = new RenException(ErrorCode.USER_IMPORT_PARTIAL_FAIL);
            ex.setData(result);
            throw ex;
        }
        return result;
    }

    @Override
    public yuhe.common.page.PageData<yuhe.modules.sys.vo.AdminSessionVO> pageSessions(
            java.util.Map<String, Object> params) {
        // getPage() 泛型跟随本类 T=SysUserEntity，token 表需自建分页对象
        long curPage = 1, limit = 10;
        if (params.get(Constant.PAGE) != null) {
            curPage = Long.parseLong(String.valueOf(params.get(Constant.PAGE)));
        }
        if (params.get(Constant.LIMIT) != null) {
            limit = Long.parseLong(String.valueOf(params.get(Constant.LIMIT)));
        }
        com.baomidou.mybatisplus.extension.plugins.pagination.Page<yuhe.modules.security.entity.SysUserTokenEntity> page =
                new com.baomidou.mybatisplus.extension.plugins.pagination.Page<>(curPage, limit);
        page.addOrder(com.baomidou.mybatisplus.core.metadata.OrderItem.desc("create_date"));
        sysUserTokenDao.selectPage(page,
                new QueryWrapper<yuhe.modules.security.entity.SysUserTokenEntity>()
                        .gt("expire_date", new java.util.Date()));
        List<yuhe.modules.sys.vo.AdminSessionVO> list = page.getRecords().stream().map(t -> {
            yuhe.modules.sys.vo.AdminSessionVO vo = new yuhe.modules.sys.vo.AdminSessionVO();
            vo.setUserId(t.getUserId());
            SysUserEntity u = sysUserDao.selectById(t.getUserId());
            vo.setUsername(u == null ? "已删除用户" : u.getUsername());
            // token 前缀掩码，避免会话劫持面
            vo.setToken(t.getToken() == null ? "" : t.getToken().substring(0, Math.min(8, t.getToken().length())) + "****");
            vo.setExpireDate(t.getExpireDate());
            vo.setCreateDate(t.getCreateDate());
            return vo;
        }).toList();
        return new PageData<>(list, page.getTotal());
    }

    @Override
    public void forceLogout(Long userId) {
        sysUserTokenDao.logout(userId, new java.util.Date(System.currentTimeMillis() - 60_000));
    }

    @Override
    public java.util.List<SysRoleEntity> listRoles() {
        // 只返回启用角色，按 sort、id 排序（内置角色 id 小排前）
        return sysRoleDao.selectList(new QueryWrapper<SysRoleEntity>()
                .eq("status", 1).orderByAsc("sort").orderByAsc("id"));
    }

    @Override
    public void assertLoginAllowed(Long userId) {
        SysUserEntity u = sysUserDao.selectById(userId);
        if (u == null) {
            throw new RenException(ErrorCode.ACCOUNT_PASSWORD_ERROR);
        }
        if (u.getDeleted() != null && u.getDeleted() == 1) {
            throw new RenException(ErrorCode.USER_DELETED);
        }
        if (u.getLocked() != null && u.getLocked() == 1) {
            throw new RenException(ErrorCode.ACCOUNT_LOCK);
        }
        if (u.getStatus() == null || u.getStatus() != 1) {
            throw new RenException(ErrorCode.ACCOUNT_DISABLE);
        }
    }

    @Override
    public void touchLastLogin(Long userId) {
        SysUserEntity patch = new SysUserEntity();
        patch.setId(userId);
        patch.setLastLoginDate(new java.util.Date());
        updateById(patch);
    }
}

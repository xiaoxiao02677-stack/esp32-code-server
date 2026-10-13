package xiaozhi.modules.sys.service.impl;

import java.util.ArrayList;
import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Random;
import java.util.regex.Matcher;
import java.util.regex.Pattern;
import java.util.stream.Collectors;

import org.apache.commons.lang3.StringUtils;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.baomidou.mybatisplus.core.conditions.query.QueryWrapper;
import com.baomidou.mybatisplus.core.metadata.IPage;

import lombok.AllArgsConstructor;
import xiaozhi.common.constant.Constant;
import xiaozhi.common.exception.ErrorCode;
import xiaozhi.common.exception.RenException;
import xiaozhi.common.page.PageData;
import xiaozhi.common.service.impl.BaseServiceImpl;
import xiaozhi.common.utils.ConvertUtils;
import xiaozhi.modules.agent.service.AgentService;
import xiaozhi.modules.device.service.DeviceService;
import xiaozhi.modules.security.password.PasswordUtils;
import xiaozhi.modules.security.service.SysUserTokenService;
import xiaozhi.modules.security.user.SecurityUser;
import xiaozhi.modules.sys.dao.SysUserDao;
import xiaozhi.modules.sys.dao.SysUserRoleDao;
import xiaozhi.modules.sys.dto.AdminPageUserDTO;
import xiaozhi.modules.sys.dto.AdminUserCreateDTO;
import xiaozhi.modules.sys.dto.PasswordDTO;
import xiaozhi.modules.sys.dto.SysUserDTO;
import xiaozhi.modules.sys.dto.UserImportDTO;
import xiaozhi.modules.sys.entity.SysRoleEntity;
import xiaozhi.modules.sys.entity.SysUserEntity;
import xiaozhi.modules.sys.entity.SysUserRoleEntity;
import xiaozhi.modules.sys.enums.SuperAdminEnum;
import xiaozhi.modules.sys.service.AuditService;
import xiaozhi.modules.sys.service.SysParamsService;
import xiaozhi.modules.sys.service.SysRoleService;
import xiaozhi.modules.sys.service.SysUserService;
import xiaozhi.modules.sys.vo.AdminPageUserVO;
import xiaozhi.modules.sys.vo.AdminUserDetailVO;
import xiaozhi.modules.sys.vo.AdminUserPageVO;
import xiaozhi.modules.sys.vo.SysRoleVO;
import xiaozhi.modules.sys.vo.UserImportResultVO;
import xiaozhi.modules.sys.vo.UserSessionVO;

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

    private final SysRoleService sysRoleService;

    private final SysUserRoleDao sysUserRoleDao;

    private final SysUserTokenService sysUserTokenService;

    private final AuditService auditService;

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

        // 重置密码后强制改密
        sysUserDao.clearMustChangePwd(userId);
        SysUserEntity entity = new SysUserEntity();
        entity.setId(userId);
        entity.setMustChangePwd(1);
        updateById(entity);

        auditService.log("user", "resetPwd", "sys_user", String.valueOf(userId), null, true, null);
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
        Long operatorId = SecurityUser.getUserId();
        for (String userId : userIds) {
            Long id = Long.parseLong(userId);
            SysUserEntity exists = sysUserDao.getByIdIncludeDeleted(id);
            if (exists == null) {
                throw new RenException(ErrorCode.USER_NOT_FOUND);
            }
            // 跳过已删除用户
            if (exists.getDeleted() != null && exists.getDeleted() == 1) {
                continue;
            }
            // 防自禁
            if (status == 0 && id.equals(operatorId)) {
                throw new RenException(ErrorCode.CANNOT_DISABLE_SELF);
            }
            // 防最后一个启用超管被停用
            if (status == 0 && exists.getSuperAdmin() != null
                    && exists.getSuperAdmin() == SuperAdminEnum.YES.value()) {
                long enabledSuperAdminCount = sysUserDao.countEnabledSuperAdmin();
                if (enabledSuperAdminCount <= 1) {
                    throw new RenException(ErrorCode.CANNOT_DELETE_LAST_ADMIN);
                }
            }
            SysUserEntity entity = new SysUserEntity();
            entity.setId(id);
            entity.setStatus(status);
            updateById(entity);

            auditService.log("user", status == 0 ? "disable" : "enable", "sys_user", userId, null, true, null);
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

    // ==================== 用户管理模块扩展 ====================

    @Override
    public PageData<AdminUserPageVO> pageUsers(Map<String, Object> params) {
        String keyword = (String) params.get("keyword");
        Integer deleted = params.get("deleted") == null ? 0 : Integer.parseInt(String.valueOf(params.get("deleted")));
        String roleId = (String) params.get("roleId");

        // 含已删用户的过滤条件集
        List<SysUserEntity> filtered = sysUserDao.selectAllIncludeDeleted(keyword, deleted);

        // roleId 过滤：查该角色关联的用户
        if (StringUtils.isNotBlank(roleId)) {
            LambdaQueryWrapper<SysUserRoleEntity> urWrapper = new LambdaQueryWrapper<>();
            urWrapper.eq(SysUserRoleEntity::getRoleId, Long.parseLong(roleId));
            List<Long> userIds = sysUserRoleDao.selectList(urWrapper).stream()
                    .map(SysUserRoleEntity::getUserId).collect(Collectors.toList());
            filtered = filtered.stream().filter(u -> userIds.contains(u.getId())).collect(Collectors.toList());
        }

        // 手动分页
        long pageNum = Long.parseLong(String.valueOf(params.getOrDefault(Constant.PAGE, "1")));
        long limit = Long.parseLong(String.valueOf(params.getOrDefault(Constant.LIMIT, "10")));
        long from = (pageNum - 1) * limit;
        long to = Math.min(from + limit, filtered.size());
        List<SysUserEntity> pageRecords = from >= filtered.size() ? new ArrayList<>()
                : new ArrayList<>(filtered.subList((int) from, (int) to));

        // 角色名称映射
        Map<Long, List<SysRoleEntity>> roleMap = batchRoleNames(pageRecords);
        Map<Long, String> roleNameMap = roleMap.entrySet().stream().collect(Collectors.toMap(
                Map.Entry::getKey,
                e -> e.getValue().stream().map(SysRoleEntity::getRoleName).collect(Collectors.joining(",")),
                (a, b) -> a));

        List<AdminUserPageVO> voList = pageRecords.stream().map(u -> {
            AdminUserPageVO vo = new AdminUserPageVO();
            vo.setId(u.getId());
            vo.setUsername(u.getUsername());
            vo.setSuperAdmin(u.getSuperAdmin());
            vo.setStatus(u.getStatus());
            vo.setDeleted(u.getDeleted());
            vo.setLocked(u.getLocked());
            vo.setMustChangePwd(u.getMustChangePwd());
            vo.setLastLoginDate(u.getLastLoginDate());
            vo.setCreateDate(u.getCreateDate());
            vo.setRoleNames(roleNameMap.containsKey(u.getId())
                    ? roleMap.get(u.getId()).stream().map(SysRoleEntity::getRoleName).collect(Collectors.toList())
                    : new ArrayList<>());
            return vo;
        }).collect(Collectors.toList());

        return new PageData<>(voList, filtered.size());
    }

    /** 批量查用户角色（含停用角色） */
    private Map<Long, List<SysRoleEntity>> batchRoleNames(List<SysUserEntity> users) {
        Map<Long, List<SysRoleEntity>> result = new LinkedHashMap<>();
        if (users.isEmpty()) {
            return result;
        }
        List<Long> userIds = users.stream().map(SysUserEntity::getId).collect(Collectors.toList());
        LambdaQueryWrapper<SysUserRoleEntity> urWrapper = new LambdaQueryWrapper<>();
        urWrapper.in(SysUserRoleEntity::getUserId, userIds);
        List<SysUserRoleEntity> relations = sysUserRoleDao.selectList(urWrapper);
        if (relations.isEmpty()) {
            return result;
        }
        List<Long> roleIds = relations.stream().map(SysUserRoleEntity::getRoleId).distinct()
                .collect(Collectors.toList());
        Map<Long, SysRoleEntity> rolesById = new LinkedHashMap<>();
        List<SysRoleEntity> roleEntities = sysRoleService.getRolesByIds(roleIds);
        for (SysRoleEntity r : roleEntities) {
            rolesById.put(r.getId(), r);
        }
        for (SysUserRoleEntity rel : relations) {
            SysRoleEntity role = rolesById.get(rel.getRoleId());
            if (role != null) {
                result.computeIfAbsent(rel.getUserId(), k -> new ArrayList<>()).add(role);
            }
        }
        return result;
    }

    @Override
    @Transactional(rollbackFor = Exception.class)
    public String createUser(AdminUserCreateDTO dto) {
        // 用户名查重（含已删用户，避免回收站重名冲突）
        List<SysUserEntity> existList = sysUserDao.selectAllIncludeDeleted(dto.getUsername(), null);
        if (existList != null && !existList.stream()
                .filter(u -> dto.getUsername().equals(u.getUsername())).collect(Collectors.toList()).isEmpty()) {
            throw new RenException(ErrorCode.USERNAME_EXISTS);
        }

        String rawPassword = StringUtils.isBlank(dto.getPassword()) ? generatePassword() : dto.getPassword();
        if (!isStrongPassword(rawPassword)) {
            throw new RenException(ErrorCode.PASSWORD_WEAK_ERROR);
        }

        SysUserEntity entity = new SysUserEntity();
        entity.setUsername(dto.getUsername());
        entity.setPassword(PasswordUtils.encode(rawPassword));
        entity.setSuperAdmin(SuperAdminEnum.NO.value());
        entity.setStatus(1);
        entity.setDeleted(0);
        entity.setLocked(0);
        entity.setMustChangePwd(1);
        entity.setPwdUpdateDate(null);
        insert(entity);

        // 分配角色
        if (dto.getRoleIds() != null && !dto.getRoleIds().isEmpty()) {
            sysRoleService.assignUserRoles(entity.getId(), dto.getRoleIds());
        }

        auditService.log("user", "create", "sys_user", String.valueOf(entity.getId()), dto, true, null);
        return rawPassword;
    }

    @Override
    public AdminUserDetailVO getUserDetail(Long id) {
        SysUserEntity entity = sysUserDao.getByIdIncludeDeleted(id);
        if (entity == null) {
            throw new RenException(ErrorCode.USER_NOT_FOUND);
        }
        AdminUserDetailVO vo = new AdminUserDetailVO();
        vo.setId(entity.getId());
        vo.setUsername(entity.getUsername());
        vo.setSuperAdmin(entity.getSuperAdmin());
        vo.setStatus(entity.getStatus());
        vo.setDeleted(entity.getDeleted());
        vo.setLocked(entity.getLocked());
        vo.setMustChangePwd(entity.getMustChangePwd());
        vo.setLastLoginDate(entity.getLastLoginDate());
        vo.setPwdUpdateDate(entity.getPwdUpdateDate());
        vo.setDeletedDate(entity.getDeletedDate());
        vo.setCreateDate(entity.getCreateDate());
        vo.setRoleIds(sysRoleService.getRoleIdsByUserId(id));
        vo.setRoleNames(sysRoleService.getRoleCodesByUserId(id));
        return vo;
    }

    @Override
    @Transactional(rollbackFor = Exception.class)
    public void softDelete(Long id) {
        SysUserEntity exists = sysUserDao.getByIdIncludeDeleted(id);
        if (exists == null) {
            throw new RenException(ErrorCode.USER_NOT_FOUND);
        }
        if (exists.getDeleted() != null && exists.getDeleted() == 1) {
            throw new RenException(ErrorCode.USER_DELETED);
        }
        // 防删最后一个启用超管
        if (exists.getSuperAdmin() != null && exists.getSuperAdmin() == SuperAdminEnum.YES.value()) {
            long enabledSuperAdminCount = sysUserDao.countEnabledSuperAdmin();
            if (enabledSuperAdminCount <= 1) {
                throw new RenException(ErrorCode.CANNOT_DELETE_LAST_ADMIN);
            }
        }
        // 防删自己
        if (id.equals(SecurityUser.getUserId())) {
            throw new RenException(ErrorCode.CANNOT_DISABLE_SELF);
        }

        int rows = sysUserDao.softDelete(id);
        if (rows == 0) {
            throw new RenException(ErrorCode.USER_NOT_FOUND);
        }
        // 软删不级联删设备/智能体（保留用户数据）
        auditService.log("user", "delete", "sys_user", String.valueOf(id), null, true, null);
    }

    @Override
    @Transactional(rollbackFor = Exception.class)
    public void restore(Long id) {
        SysUserEntity exists = sysUserDao.getByIdIncludeDeleted(id);
        if (exists == null) {
            throw new RenException(ErrorCode.USER_NOT_FOUND);
        }
        if (exists.getDeleted() == null || exists.getDeleted() == 0) {
            return;
        }
        int rows = sysUserDao.restore(id);
        if (rows == 0) {
            throw new RenException(ErrorCode.USER_NOT_FOUND);
        }
        auditService.log("user", "restore", "sys_user", String.valueOf(id), null, true, null);
    }

    @Override
    @Transactional(rollbackFor = Exception.class)
    public void assignRoles(Long userId, List<Long> roleIds) {
        SysUserEntity exists = sysUserDao.getByIdIncludeDeleted(userId);
        if (exists == null) {
            throw new RenException(ErrorCode.USER_NOT_FOUND);
        }
        // 防自改
        if (userId.equals(SecurityUser.getUserId())) {
            throw new RenException(ErrorCode.CANNOT_DISABLE_SELF);
        }
        // 防最后一个启用超管失去 super_admin 角色
        if (exists.getSuperAdmin() != null && exists.getSuperAdmin() == SuperAdminEnum.YES.value()
                && exists.getStatus() != null && exists.getStatus() == 1
                && exists.getDeleted() != null && exists.getDeleted() == 0) {
            // 目标角色中未保留 super_admin 角色（id=1）时，必须是还有其他启用超管
            boolean keepSuperAdmin = roleIds != null && roleIds.contains(1L);
            if (!keepSuperAdmin) {
                long enabledSuperAdminCount = sysUserDao.countEnabledSuperAdmin();
                if (enabledSuperAdminCount <= 1) {
                    throw new RenException(ErrorCode.CANNOT_DELETE_LAST_ADMIN);
                }
            }
        }
        sysRoleService.assignUserRoles(userId, roleIds);
        auditService.log("user", "assignRoles", "sys_user", String.valueOf(userId), roleIds, true, null);
    }

    @Override
    @Transactional(rollbackFor = Exception.class)
    public UserImportResultVO importUsers(List<UserImportDTO> list) {
        List<String> success = new ArrayList<>();
        List<UserImportResultVO.FailedItem> failed = new ArrayList<>();

        for (UserImportDTO item : list) {
            if (StringUtils.isBlank(item.getUsername())) {
                UserImportResultVO.FailedItem fi = new UserImportResultVO.FailedItem();
                fi.setUsername("");
                fi.setReason("username.blank");
                failed.add(fi);
                continue;
            }
            try {
                AdminUserCreateDTO create = new AdminUserCreateDTO();
                create.setUsername(item.getUsername());
                create.setPassword(item.getPassword());
                // roleCode → roleId（用启用角色下拉解析）
                if (StringUtils.isNotBlank(item.getRoleCode())) {
                    Long roleId = sysRoleService.listEnabled().stream()
                            .filter(r -> item.getRoleCode().equals(r.getRoleCode()))
                            .map(SysRoleVO::getId).findFirst().orElse(null);
                    if (roleId == null) {
                        throw new RenException(ErrorCode.ROLE_NOT_FOUND);
                    }
                    create.setRoleIds(List.of(roleId));
                }
                createUser(create);
                success.add(item.getUsername());
            } catch (RenException e) {
                UserImportResultVO.FailedItem fi = new UserImportResultVO.FailedItem();
                fi.setUsername(item.getUsername());
                fi.setReason(e.getMsg() != null ? e.getMsg() : String.valueOf(e.getCode()));
                failed.add(fi);
            } catch (Exception e) {
                UserImportResultVO.FailedItem fi = new UserImportResultVO.FailedItem();
                fi.setUsername(item.getUsername());
                fi.setReason(e.getMessage());
                failed.add(fi);
            }
        }

        UserImportResultVO result = new UserImportResultVO();
        result.setSuccess(success);
        result.setFailed(failed);
        auditService.log("user", "import", "sys_user", null, Map.of("total", list.size(),
                "success", success.size(), "failed", failed.size()), true, null);
        return result;
    }

    @Override
    public List<String[]> exportRows(String keyword, Integer deleted) {
        int deletedVal = deleted == null ? 0 : deleted;
        List<SysUserEntity> users = sysUserDao.selectAllIncludeDeleted(keyword, deletedVal);
        Map<Long, List<SysRoleEntity>> roleMap = batchRoleNames(users);
        Map<Long, String> roleNameMap = roleMap.entrySet().stream().collect(Collectors.toMap(
                Map.Entry::getKey,
                e -> e.getValue().stream().map(SysRoleEntity::getRoleName).collect(Collectors.joining(",")),
                (a, b) -> a));

        List<String[]> rows = new ArrayList<>();
        rows.add(new String[] { "用户名", "状态", "角色", "创建时间", "最后登录" });
        for (SysUserEntity u : users) {
            String statusText;
            if (u.getDeleted() != null && u.getDeleted() == 1) {
                statusText = "已删除";
            } else if (u.getLocked() != null && u.getLocked() == 1) {
                statusText = "已锁定";
            } else if (u.getStatus() != null && u.getStatus() == 1) {
                statusText = "正常";
            } else {
                statusText = "已停用";
            }
            rows.add(new String[] {
                    u.getUsername(),
                    statusText,
                    roleNameMap.getOrDefault(u.getId(), ""),
                    u.getCreateDate() == null ? "" : String.format("%1$tF %1$tT", u.getCreateDate()),
                    u.getLastLoginDate() == null ? "" : String.format("%1$tF %1$tT", u.getLastLoginDate())
            });
        }
        auditService.log("user", "export", "sys_user", null, Map.of("keyword", keyword == null ? "" : keyword,
                "deleted", deletedVal, "rows", users.size()), true, null);
        return rows;
    }

    @Override
    public PageData<UserSessionVO> pageSessions(Map<String, Object> params) {
        String keyword = (String) params.get("keyword");
        List<UserSessionVO> all = sysUserDao.selectSessions(keyword);

        long pageNum = Long.parseLong(String.valueOf(params.getOrDefault(Constant.PAGE, "1")));
        long limit = Long.parseLong(String.valueOf(params.getOrDefault(Constant.LIMIT, "10")));
        long from = (pageNum - 1) * limit;
        long to = Math.min(from + limit, all.size());
        List<UserSessionVO> pageRecords = from >= all.size() ? new ArrayList<>()
                : new ArrayList<>(all.subList((int) from, (int) to));

        // token 掩码：前8位 + ****
        pageRecords.forEach(vo -> {
            if (vo.getTokenMasked() != null && vo.getTokenMasked().length() > 8) {
                vo.setTokenMasked(vo.getTokenMasked().substring(0, 8) + "****");
            } else if (vo.getTokenMasked() != null) {
                vo.setTokenMasked(vo.getTokenMasked() + "****");
            }
        });

        return new PageData<>(pageRecords, all.size());
    }

    @Override
    @Transactional(rollbackFor = Exception.class)
    public void forceLogout(Long userId) {
        SysUserEntity exists = sysUserDao.getByIdIncludeDeleted(userId);
        if (exists == null) {
            throw new RenException(ErrorCode.USER_NOT_FOUND);
        }
        sysUserDao.expireUserTokens(userId);
        auditService.log("user", "forceLogout", "sys_user", String.valueOf(userId), null, true, null);
    }

    @Override
    public void updateLastLogin(Long userId) {
        sysUserDao.updateLastLogin(userId);
    }

    @Override
    public void clearMustChangePwd(Long userId) {
        sysUserDao.clearMustChangePwd(userId);
    }

    @Override
    public List<String> getUserRoleCodes(Long userId) {
        try {
            List<String> codes = sysRoleService.getRoleCodesByUserId(userId);
            return codes == null ? new ArrayList<>() : codes;
        } catch (Exception e) {
            return new ArrayList<>();
        }
    }
}

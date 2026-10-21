package yuhe.modules.sys.service.impl;

import java.util.ArrayList;
import java.util.Date;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

import org.apache.commons.lang3.StringUtils;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.baomidou.mybatisplus.core.conditions.query.QueryWrapper;
import com.baomidou.mybatisplus.core.conditions.update.UpdateWrapper;
import com.baomidou.mybatisplus.core.metadata.IPage;

import yuhe.common.constant.Constant;
import yuhe.common.exception.ErrorCode;
import yuhe.common.exception.RenException;
import yuhe.common.page.PageData;
import yuhe.common.utils.DateUtils;
import yuhe.common.utils.JsonUtils;
import yuhe.common.utils.SensitiveDataUtils;
import yuhe.modules.security.user.SecurityUser;
import yuhe.modules.sys.dao.SysAuditLogDao;
import yuhe.modules.sys.dao.SysDisplayConfigDao;
import yuhe.modules.sys.dao.SysRoleDao;
import yuhe.modules.sys.dao.SysUserCustomModelDao;
import yuhe.modules.sys.dao.SysUserCustomVoiceDao;
import yuhe.modules.sys.dao.SysUserDao;
import yuhe.modules.sys.dao.SysUserDefaultDao;
import yuhe.modules.sys.dao.SysUserRoleDao;
import yuhe.modules.sys.dto.AdminCustomAuditDTO;
import yuhe.modules.sys.dto.AdminCustomQuotaDTO;
import yuhe.modules.sys.dto.SysDisplayConfigSaveDTO;
import yuhe.modules.sys.dto.SysRoleSaveDTO;
import yuhe.modules.sys.dto.SysUserDefaultSaveDTO;
import yuhe.modules.sys.entity.SysAuditLogEntity;
import yuhe.modules.sys.entity.SysDisplayConfigEntity;
import yuhe.modules.sys.entity.SysRoleEntity;
import yuhe.modules.sys.entity.SysUserCustomModelEntity;
import yuhe.modules.sys.entity.SysUserCustomVoiceEntity;
import yuhe.modules.sys.entity.SysUserDefaultEntity;
import yuhe.modules.sys.entity.SysUserEntity;
import yuhe.modules.sys.entity.SysUserRoleEntity;
import yuhe.modules.sys.service.SysAdminModuleService;
import yuhe.modules.sys.vo.AdminAuditLogVO;
import yuhe.modules.sys.vo.AdminCustomModelVO;
import yuhe.modules.sys.vo.AdminCustomVoiceVO;
import yuhe.modules.sys.vo.AdminRoleVO;

/**
 * 管理端扩展模块实现（console-v2 五页面后端契约，SPEC §4）
 */
@Service
public class SysAdminModuleServiceImpl implements SysAdminModuleService {

    private final SysRoleDao sysRoleDao;
    private final SysUserRoleDao sysUserRoleDao;
    private final SysUserDao sysUserDao;
    private final SysAuditLogDao sysAuditLogDao;
    private final SysDisplayConfigDao sysDisplayConfigDao;
    private final SysUserDefaultDao sysUserDefaultDao;
    private final SysUserCustomModelDao sysUserCustomModelDao;
    private final SysUserCustomVoiceDao sysUserCustomVoiceDao;

    public SysAdminModuleServiceImpl(SysRoleDao sysRoleDao, SysUserRoleDao sysUserRoleDao, SysUserDao sysUserDao,
            SysAuditLogDao sysAuditLogDao, SysDisplayConfigDao sysDisplayConfigDao,
            SysUserDefaultDao sysUserDefaultDao, SysUserCustomModelDao sysUserCustomModelDao,
            SysUserCustomVoiceDao sysUserCustomVoiceDao) {
        this.sysRoleDao = sysRoleDao;
        this.sysUserRoleDao = sysUserRoleDao;
        this.sysUserDao = sysUserDao;
        this.sysAuditLogDao = sysAuditLogDao;
        this.sysDisplayConfigDao = sysDisplayConfigDao;
        this.sysUserDefaultDao = sysUserDefaultDao;
        this.sysUserCustomModelDao = sysUserCustomModelDao;
        this.sysUserCustomVoiceDao = sysUserCustomVoiceDao;
    }

    // ==================== 角色管理（SPEC §4.1） ====================

    @Override
    public PageData<AdminRoleVO> rolePage(Map<String, Object> params) {
        String keyword = StringUtils.trimToNull((String) params.get("keyword"));
        long page = 1;
        long limit = 10;
        if (params.get(Constant.PAGE) != null) {
            page = Long.parseLong(String.valueOf(params.get(Constant.PAGE)));
        }
        if (params.get(Constant.LIMIT) != null) {
            limit = Long.parseLong(String.valueOf(params.get(Constant.LIMIT)));
        }
        LambdaQueryWrapper<SysRoleEntity> qw = new LambdaQueryWrapper<>();
        if (keyword != null) {
            qw.and(w -> w.like(SysRoleEntity::getRoleCode, keyword).or().like(SysRoleEntity::getRoleName, keyword));
        }
        qw.orderByAsc(SysRoleEntity::getSort).orderByAsc(SysRoleEntity::getId);
        IPage<SysRoleEntity> p = sysRoleDao.selectPage(new com.baomidou.mybatisplus.extension.plugins.pagination.Page<>(page, limit), qw);
        List<AdminRoleVO> list = p.getRecords().stream().map(this::toRoleVO).collect(Collectors.toList());
        return new PageData<>(list, p.getTotal());
    }

    @Override
    public AdminRoleVO roleDetail(Long id) {
        SysRoleEntity role = sysRoleDao.selectById(id);
        if (role == null) {
            throw new RenException(ErrorCode.ADMIN_ROLE_NOT_EXIST);
        }
        return toRoleVO(role);
    }

    @Override
    @Transactional(rollbackFor = Exception.class)
    public void roleSave(SysRoleSaveDTO dto) {
        checkRoleCode(dto.getRoleCode(), null);
        SysRoleEntity entity = new SysRoleEntity();
        entity.setRoleCode(dto.getRoleCode());
        entity.setRoleName(dto.getRoleName());
        entity.setPermissions(toJsonArray(dto.getPermissions()));
        entity.setRemark(dto.getRemark());
        entity.setSort(dto.getSort() == null ? 0 : dto.getSort());
        entity.setStatus(dto.getStatus() == null ? 1 : dto.getStatus());
        entity.setIsBuiltin(0);
        entity.setCreator(SecurityUser.getUserId());
        entity.setCreateDate(new Date());
        sysRoleDao.insert(entity);
    }

    @Override
    @Transactional(rollbackFor = Exception.class)
    public void roleUpdate(SysRoleSaveDTO dto) {
        if (dto.getId() == null) {
            throw new RenException(ErrorCode.ADMIN_ROLE_NOT_EXIST);
        }
        SysRoleEntity role = sysRoleDao.selectById(dto.getId());
        if (role == null) {
            throw new RenException(ErrorCode.ADMIN_ROLE_NOT_EXIST);
        }
        checkRoleCode(dto.getRoleCode(), dto.getId());
        role.setRoleCode(dto.getRoleCode());
        role.setRoleName(dto.getRoleName());
        role.setPermissions(toJsonArray(dto.getPermissions()));
        role.setRemark(dto.getRemark());
        role.setSort(dto.getSort() == null ? 0 : dto.getSort());
        if (dto.getStatus() != null) {
            role.setStatus(dto.getStatus());
        }
        role.setUpdater(SecurityUser.getUserId());
        role.setUpdateDate(new Date());
        sysRoleDao.updateById(role);
    }

    @Override
    @Transactional(rollbackFor = Exception.class)
    public void roleDelete(List<Long> ids) {
        if (ids == null || ids.isEmpty()) {
            return;
        }
        for (Long id : ids) {
            SysRoleEntity role = sysRoleDao.selectById(id);
            if (role == null) {
                continue;
            }
            if (role.getIsBuiltin() != null && role.getIsBuiltin() == 1) {
                throw new RenException(ErrorCode.ADMIN_ROLE_BUILTIN_FORBIDDEN);
            }
            Long cnt = sysUserRoleDao.selectCount(new QueryWrapper<SysUserRoleEntity>().eq("role_id", id));
            if (cnt != null && cnt > 0) {
                throw new RenException(ErrorCode.ADMIN_ROLE_HAS_USERS);
            }
            sysRoleDao.deleteById(id);
        }
    }

    private void checkRoleCode(String roleCode, Long excludeId) {
        if (StringUtils.isBlank(roleCode)) {
            throw new RenException("角色编码不能为空");
        }
        LambdaQueryWrapper<SysRoleEntity> qw = new LambdaQueryWrapper<SysRoleEntity>()
                .eq(SysRoleEntity::getRoleCode, roleCode);
        if (excludeId != null) {
            qw.ne(SysRoleEntity::getId, excludeId);
        }
        if (sysRoleDao.selectCount(qw) > 0) {
            throw new RenException(ErrorCode.ADMIN_ROLE_CODE_EXISTS);
        }
    }

    private AdminRoleVO toRoleVO(SysRoleEntity r) {
        AdminRoleVO vo = new AdminRoleVO();
        vo.setId(r.getId());
        vo.setRoleCode(r.getRoleCode());
        vo.setRoleName(r.getRoleName());
        vo.setRemark(r.getRemark());
        vo.setStatus(r.getStatus());
        vo.setIsBuiltIn(r.getIsBuiltin());
        vo.setSort(r.getSort());
        vo.setCreateDate(r.getCreateDate() == null ? null : DateUtils.format(r.getCreateDate(), DateUtils.DATE_PATTERN));
        Long cnt = sysUserRoleDao.selectCount(new QueryWrapper<SysUserRoleEntity>().eq("role_id", r.getId()));
        vo.setUserCount(cnt == null ? 0L : cnt);
        if (r.getCreator() != null) {
            SysUserEntity creator = sysUserDao.selectById(r.getCreator());
            vo.setCreatorName(creator == null ? null : creator.getUsername());
        }
        vo.setPermissions(parsePermissions(r.getPermissions()));
        return vo;
    }

    private List<String> parsePermissions(String json) {
        if (StringUtils.isBlank(json)) {
            return new ArrayList<>();
        }
        try {
            List<String> list = JsonUtils.parseArray(json, String.class);
            return list == null ? new ArrayList<>() : list;
        } catch (Exception e) {
            return new ArrayList<>();
        }
    }

    /** permissions 数组 → JSON 数组字符串（不含权限时存空数组便于前端直接消费） */
    private String toJsonArray(List<String> perms) {
        return JsonUtils.toJsonString(perms == null ? new ArrayList<>() : perms);
    }

    // ==================== 审计日志（SPEC §4.5） ====================

    @Override
    public PageData<AdminAuditLogVO> auditPage(Map<String, Object> params) {
        long page = 1;
        long limit = 10;
        if (params.get(Constant.PAGE) != null) {
            page = Long.parseLong(String.valueOf(params.get(Constant.PAGE)));
        }
        if (params.get(Constant.LIMIT) != null) {
            limit = Long.parseLong(String.valueOf(params.get(Constant.LIMIT)));
        }
        QueryWrapper<SysAuditLogEntity> qw = new QueryWrapper<>();
        String userId = StringUtils.trimToNull((String) params.get("userId"));
        String module = StringUtils.trimToNull((String) params.get("module"));
        String operation = StringUtils.trimToNull((String) params.get("operation"));
        String startDate = StringUtils.trimToNull((String) params.get("startDate"));
        String endDate = StringUtils.trimToNull((String) params.get("endDate"));
        if (userId != null) {
            try {
                qw.eq("user_id", Long.parseLong(userId));
            } catch (NumberFormatException ignored) {
                // 非数字用户ID → 命中空结果（与前端语义一致：不匹配任何记录）
                qw.apply("1=0");
            }
        }
        qw.eq(module != null, "module", module);
        qw.like(operation != null, "operation", operation);
        if (startDate != null) {
            qw.ge("created_at", startDate + " 00:00:00");
        }
        if (endDate != null) {
            qw.le("created_at", endDate + " 23:59:59");
        }
        qw.orderByDesc("created_at").orderByDesc("id");
        IPage<SysAuditLogEntity> p = sysAuditLogDao.selectPage(
                new com.baomidou.mybatisplus.extension.plugins.pagination.Page<>(page, limit), qw);
        List<AdminAuditLogVO> list = p.getRecords().stream().map(e -> {
            AdminAuditLogVO vo = new AdminAuditLogVO();
            vo.setId(e.getId());
            vo.setUserId(e.getUserId());
            vo.setUsername(e.getUsername());
            vo.setModule(e.getModule());
            vo.setOperation(e.getOperation());
            vo.setTargetType(e.getTargetType());
            vo.setTargetId(e.getTargetId());
            vo.setRequestUri(e.getRequestUri());
            vo.setRequestMethod(e.getRequestMethod());
            vo.setParams(e.getParams());
            vo.setResult(e.getResult());
            vo.setErrorMsg(e.getErrorMsg());
            vo.setIp(e.getIp());
            vo.setUserAgent(e.getUserAgent());
            vo.setDuration(e.getDuration());
            vo.setCreatedDate(
                    e.getCreatedAt() == null ? null : DateUtils.format(e.getCreatedAt(), DateUtils.DATE_TIME_PATTERN));
            return vo;
        }).collect(Collectors.toList());
        return new PageData<>(list, p.getTotal());
    }

    @Override
    public List<String> auditModules() {
        // 纯模块名去重列表（前端下拉直接消费）
        return sysAuditLogDao.selectObjs(
                new QueryWrapper<SysAuditLogEntity>().select("DISTINCT module").isNotNull("module").ne("module", "")
                        .orderByAsc("module"))
                .stream().map(o -> (String) o).collect(Collectors.toList());
    }

    // ==================== 展示配置（SPEC §4.3） ====================

    @Override
    public Map<String, Object> displayConfigGet(Integer scopeType, Long roleId, Long userId) {
        validateScope(scopeType, roleId, userId);
        SysDisplayConfigEntity row = findDisplayConfig(scopeType, roleId, userId);
        Map<String, Object> data = new LinkedHashMap<>();
        if (row == null) {
            // 无存量行：返回空 fields，前端按缺省规则全量渲染
            data.put("configJson", "{\"fields\":{}}");
            data.put("scopeType", scopeType);
            data.put("roleId", roleId);
            data.put("userId", userId);
            return data;
        }
        data.put("id", row.getId());
        data.put("scopeType", row.getScopeType());
        data.put("roleId", row.getRoleId());
        data.put("userId", row.getUserId());
        // 契约：data.configJson 必须是对象（新格式）或字符串；返回字符串由前端自行 parse
        data.put("configJson", row.getConfigJson());
        return data;
    }

    @Override
    @Transactional(rollbackFor = Exception.class)
    public void displayConfigSave(SysDisplayConfigSaveDTO dto) {
        validateScope(dto.getScopeType(), dto.getRoleId(), dto.getUserId());
        String json;
        if (dto.getConfigJson() instanceof String s) {
            json = s;
        } else {
            json = JsonUtils.toJsonString(dto.getConfigJson());
        }
        SysDisplayConfigEntity row = findDisplayConfig(dto.getScopeType(), dto.getRoleId(), dto.getUserId());
        if (row == null) {
            row = new SysDisplayConfigEntity();
            row.setScopeType(dto.getScopeType());
            row.setRoleId(dto.getRoleId());
            row.setUserId(dto.getUserId());
            row.setConfigJson(json);
            row.setCreator(SecurityUser.getUserId());
            row.setCreateDate(new Date());
            sysDisplayConfigDao.insert(row);
        } else {
            row.setConfigJson(json);
            row.setUpdater(SecurityUser.getUserId());
            row.setUpdateDate(new Date());
            sysDisplayConfigDao.updateById(row);
        }
    }

    /**
     * 当前登录用户的生效配置：系统(0) → 角色(1) → 用户(2) 逐层 merge。
     * fields/modules 均为键级覆盖（上层缺省下层补，显式配置覆盖下层）。
     */
    @Override
    public Map<String, Object> myDisplayConfig() {
        Long userId = SecurityUser.getUserId();
        if (userId == null) {
            Map<String, Object> empty = new LinkedHashMap<>();
            empty.put("fields", new LinkedHashMap<String, Object>());
            empty.put("modules", new LinkedHashMap<String, Object>());
            return empty;
        }
        List<Long> roleIds = sysUserRoleDao.selectRoleIdsByUserId(userId);
        Map<String, Object> merged = new LinkedHashMap<>();
        merged.put("fields", new LinkedHashMap<String, Object>());
        merged.put("modules", new LinkedHashMap<String, Object>());
        // 逐层：系统 → 各角色（按 roleId 升序，靠后的覆盖靠前的）→ 用户
        List<SysDisplayConfigEntity> layers = new ArrayList<>();
        layers.add(findDisplayConfig(0, null, null));
        if (roleIds != null) {
            roleIds.stream().sorted().forEach(rid -> layers.add(findDisplayConfig(1, rid, null)));
        }
        layers.add(findDisplayConfig(2, null, userId));
        for (SysDisplayConfigEntity layer : layers) {
            if (layer == null || StringUtils.isBlank(layer.getConfigJson())) {
                continue;
            }
            try {
                Map<String, Object> cfg = JsonUtils.parseMap(layer.getConfigJson());
                if (cfg == null) {
                    continue;
                }
                mergeSection(merged, cfg, "fields");
                mergeSection(merged, cfg, "modules");
            } catch (Exception e) {
                // 单层损坏不阻塞整体合并
            }
        }
        return merged;
    }

    /** 把 cfg 里的指定 section（fields/modules）键级合并进 merged；值须为 Map */
    @SuppressWarnings("unchecked")
    private void mergeSection(Map<String, Object> merged, Map<String, Object> cfg, String section) {
        Object sec = cfg.get(section);
        if (!(sec instanceof Map)) {
            return;
        }
        Map<String, Object> target = (Map<String, Object>) merged.computeIfAbsent(section,
                k -> new LinkedHashMap<String, Object>());
        target.putAll((Map<String, Object>) sec);
    }

    private void validateScope(Integer scopeType, Long roleId, Long userId) {
        if (scopeType == null) {
            throw new RenException(ErrorCode.ADMIN_SCOPE_INVALID);
        }
        if (scopeType == 1 && (roleId == null || roleId <= 0)) {
            throw new RenException(ErrorCode.ADMIN_SCOPE_INVALID);
        }
        if (scopeType == 2 && (userId == null || userId <= 0)) {
            throw new RenException(ErrorCode.ADMIN_SCOPE_INVALID);
        }
    }

    private SysDisplayConfigEntity findDisplayConfig(Integer scopeType, Long roleId, Long userId) {
        LambdaQueryWrapper<SysDisplayConfigEntity> qw = new LambdaQueryWrapper<SysDisplayConfigEntity>()
                .eq(SysDisplayConfigEntity::getScopeType, scopeType);
        if (scopeType == 1) {
            qw.eq(SysDisplayConfigEntity::getRoleId, roleId);
        } else if (scopeType == 2) {
            qw.eq(SysDisplayConfigEntity::getUserId, userId);
        } else {
            qw.eq(SysDisplayConfigEntity::getRoleId, 0L).eq(SysDisplayConfigEntity::getUserId, 0L);
        }
        return sysDisplayConfigDao.selectOne(qw);
    }

    // ==================== 默认配置（SPEC §4.3） ====================

    @Override
    public Map<String, Object> userDefaultGet(Integer scopeType, Long roleId, Long userId) {
        validateScope(scopeType, roleId, userId);
        SysUserDefaultEntity row = findUserDefault(scopeType, roleId, userId);
        if (row == null) {
            Map<String, Object> empty = new LinkedHashMap<>();
            empty.put("scopeType", scopeType);
            empty.put("roleId", roleId);
            empty.put("userId", userId);
            return empty;
        }
        Map<String, Object> data = new LinkedHashMap<>();
        data.put("id", row.getId());
        data.put("scopeType", row.getScopeType());
        data.put("roleId", row.getRoleId());
        data.put("userId", row.getUserId());
        data.put("llmModelId", row.getLlmModelId());
        data.put("ttsModelId", row.getTtsModelId());
        data.put("ttsVoiceId", row.getTtsVoiceId());
        data.put("asrModelId", row.getAsrModelId());
        data.put("paramJson", row.getParamJson());
        data.put("lockPolicy", Boolean.TRUE.equals(row.getLockPolicy()));
        return data;
    }

    @Override
    @Transactional(rollbackFor = Exception.class)
    public void userDefaultSave(SysUserDefaultSaveDTO dto) {
        validateScope(dto.getScopeType(), dto.getRoleId(), dto.getUserId());
        SysUserDefaultEntity row = findUserDefault(dto.getScopeType(), dto.getRoleId(), dto.getUserId());
        if (row == null) {
            row = new SysUserDefaultEntity();
            row.setScopeType(dto.getScopeType());
            row.setRoleId(dto.getRoleId());
            row.setUserId(dto.getUserId());
            row.setLlmModelId(dto.getLlmModelId());
            row.setTtsModelId(dto.getTtsModelId());
            row.setTtsVoiceId(dto.getTtsVoiceId());
            row.setAsrModelId(dto.getAsrModelId());
            row.setParamJson(dto.getParamJson());
            row.setLockPolicy(Boolean.TRUE.equals(dto.getLockPolicy()));
            row.setCreator(SecurityUser.getUserId());
            row.setCreateDate(new Date());
            sysUserDefaultDao.insert(row);
        } else {
            // 更新走 UpdateWrapper：用户清空字段（null）也要写库，实体 updateById 会跳过 null
            UpdateWrapper<SysUserDefaultEntity> uw = new UpdateWrapper<SysUserDefaultEntity>()
                    .eq("id", row.getId())
                    .set("llm_model_id", dto.getLlmModelId())
                    .set("tts_model_id", dto.getTtsModelId())
                    .set("tts_voice_id", dto.getTtsVoiceId())
                    .set("asr_model_id", dto.getAsrModelId())
                    .set("param_json", dto.getParamJson())
                    .set("lock_policy", Boolean.TRUE.equals(dto.getLockPolicy()) ? 1 : 0)
                    .set("updater", SecurityUser.getUserId())
                    .set("update_date", new Date());
            sysUserDefaultDao.update(null, uw);
        }
    }

    private SysUserDefaultEntity findUserDefault(Integer scopeType, Long roleId, Long userId) {
        LambdaQueryWrapper<SysUserDefaultEntity> qw = new LambdaQueryWrapper<SysUserDefaultEntity>()
                .eq(SysUserDefaultEntity::getScopeType, scopeType);
        if (scopeType == 1) {
            qw.eq(SysUserDefaultEntity::getRoleId, roleId);
        } else if (scopeType == 2) {
            qw.eq(SysUserDefaultEntity::getUserId, userId);
        } else {
            qw.eq(SysUserDefaultEntity::getRoleId, 0L).eq(SysUserDefaultEntity::getUserId, 0L);
        }
        return sysUserDefaultDao.selectOne(qw);
    }

    // ==================== 自定义审核（SPEC §4.4） ====================

    @Override
    public PageData<AdminCustomModelVO> customModelPage(Map<String, Object> params) {
        long page = 1;
        long limit = 10;
        if (params.get(Constant.PAGE) != null) {
            page = Long.parseLong(String.valueOf(params.get(Constant.PAGE)));
        }
        if (params.get(Constant.LIMIT) != null) {
            limit = Long.parseLong(String.valueOf(params.get(Constant.LIMIT)));
        }
        String keyword = StringUtils.trimToNull((String) params.get("keyword"));
        Integer auditStatus = null;
        if (params.get("auditStatus") != null && StringUtils.isNotBlank(String.valueOf(params.get("auditStatus")))) {
            auditStatus = Integer.parseInt(String.valueOf(params.get("auditStatus")));
        }
        QueryWrapper<SysUserCustomModelEntity> qw = new QueryWrapper<>();
        qw.eq(auditStatus != null, "audit_status", auditStatus);
        if (keyword != null) {
            // keyword 命中 模型名 / 用户名（join 语义：子查询反查 user_id 或直接 LIKE 模型名）
            qw.and(w -> w.like("model_name", keyword)
                    .or().like("provider_code", keyword)
                    .or().inSql("user_id",
                            "SELECT id FROM sys_user WHERE username LIKE '%" + keyword.replace("'", "''") + "%'"));
        }
        qw.orderByDesc("create_date").orderByDesc("id");
        IPage<SysUserCustomModelEntity> p = sysUserCustomModelDao.selectPage(
                new com.baomidou.mybatisplus.extension.plugins.pagination.Page<>(page, limit), qw);
        List<AdminCustomModelVO> list = p.getRecords().stream().map(e -> {
            AdminCustomModelVO vo = new AdminCustomModelVO();
            vo.setId(e.getId());
            vo.setUserId(e.getUserId());
            vo.setUsername(usernameOf(e.getUserId()));
            vo.setModelType(e.getModelType());
            vo.setModelName(e.getModelName());
            vo.setProviderCode(e.getProviderCode());
            vo.setBaseUrl(e.getBaseUrl());
            vo.setApiKeyMasked(SensitiveDataUtils.maskMiddle(e.getApiKeyCipher()));
            vo.setAuditStatus(e.getAuditStatus());
            vo.setAuditRemark(e.getAuditRemark());
            vo.setAuditor(e.getAuditor());
            vo.setAuditDate(e.getAuditDate() == null ? null : DateUtils.format(e.getAuditDate(), DateUtils.DATE_TIME_PATTERN));
            vo.setStatus(e.getStatus());
            vo.setHealthStatus(e.getHealthStatus());
            vo.setQuotaLimit(e.getQuotaLimit());
            vo.setUsedCount(e.getUsedCount());
            vo.setRemark(e.getRemark());
            vo.setCreateDate(e.getCreateDate() == null ? null : DateUtils.format(e.getCreateDate(), DateUtils.DATE_TIME_PATTERN));
            return vo;
        }).collect(Collectors.toList());
        return new PageData<>(list, p.getTotal());
    }

    @Override
    @Transactional(rollbackFor = Exception.class)
    public void customModelAudit(AdminCustomAuditDTO dto) {
        SysUserCustomModelEntity e = sysUserCustomModelDao.selectById(dto.getId());
        if (e == null) {
            throw new RenException(ErrorCode.ADMIN_CUSTOM_NOT_EXIST);
        }
        boolean pass = Boolean.TRUE.equals(dto.getPass());
        if (!pass && StringUtils.isBlank(dto.getRemark())) {
            throw new RenException(ErrorCode.ADMIN_AUDIT_REMARK_REQUIRED);
        }
        // 通过时清空驳回意见：updateById 跳过 null，必须走 UpdateWrapper 显式 set
        UpdateWrapper<SysUserCustomModelEntity> uw = new UpdateWrapper<SysUserCustomModelEntity>()
                .eq("id", dto.getId())
                .set("audit_status", pass ? 1 : 2)
                .set("audit_remark", pass ? null : dto.getRemark())
                .set("auditor", SecurityUser.getUserId())
                .set("audit_date", new Date())
                .set("updater", SecurityUser.getUserId())
                .set("update_date", new Date());
        sysUserCustomModelDao.update(null, uw);
    }

    @Override
    @Transactional(rollbackFor = Exception.class)
    public void customModelQuota(AdminCustomQuotaDTO dto) {
        SysUserCustomModelEntity e = sysUserCustomModelDao.selectById(dto.getId());
        if (e == null) {
            throw new RenException(ErrorCode.ADMIN_CUSTOM_NOT_EXIST);
        }
        // quotaLimit=null 表示不限：updateById 跳过 null，必须显式 set
        UpdateWrapper<SysUserCustomModelEntity> uw = new UpdateWrapper<SysUserCustomModelEntity>()
                .eq("id", dto.getId())
                .set("quota_limit", dto.getQuotaLimit())
                .set("updater", SecurityUser.getUserId())
                .set("update_date", new Date());
        sysUserCustomModelDao.update(null, uw);
    }

    @Override
    public PageData<AdminCustomVoiceVO> customVoicePage(Map<String, Object> params) {
        long page = 1;
        long limit = 10;
        if (params.get(Constant.PAGE) != null) {
            page = Long.parseLong(String.valueOf(params.get(Constant.PAGE)));
        }
        if (params.get(Constant.LIMIT) != null) {
            limit = Long.parseLong(String.valueOf(params.get(Constant.LIMIT)));
        }
        String keyword = StringUtils.trimToNull((String) params.get("keyword"));
        Integer auditStatus = null;
        if (params.get("auditStatus") != null && StringUtils.isNotBlank(String.valueOf(params.get("auditStatus")))) {
            auditStatus = Integer.parseInt(String.valueOf(params.get("auditStatus")));
        }
        QueryWrapper<SysUserCustomVoiceEntity> qw = new QueryWrapper<>();
        qw.eq(auditStatus != null, "audit_status", auditStatus);
        if (keyword != null) {
            qw.and(w -> w.like("name", keyword)
                    .or().like("tts_voice", keyword)
                    .or().inSql("user_id",
                            "SELECT id FROM sys_user WHERE username LIKE '%" + keyword.replace("'", "''") + "%'"));
        }
        qw.orderByDesc("create_date").orderByDesc("id");
        IPage<SysUserCustomVoiceEntity> p = sysUserCustomVoiceDao.selectPage(
                new com.baomidou.mybatisplus.extension.plugins.pagination.Page<>(page, limit), qw);
        List<AdminCustomVoiceVO> list = p.getRecords().stream().map(e -> {
            AdminCustomVoiceVO vo = new AdminCustomVoiceVO();
            vo.setId(e.getId());
            vo.setUserId(e.getUserId());
            vo.setUsername(usernameOf(e.getUserId()));
            vo.setName(e.getName());
            vo.setTtsModelId(e.getTtsModelId());
            vo.setTtsVoice(e.getTtsVoice());
            vo.setLanguages(e.getLanguages());
            vo.setReferenceText(e.getReferenceText());
            vo.setAuditStatus(e.getAuditStatus());
            vo.setAuditRemark(e.getAuditRemark());
            vo.setAuditor(e.getAuditor());
            vo.setAuditDate(e.getAuditDate() == null ? null : DateUtils.format(e.getAuditDate(), DateUtils.DATE_TIME_PATTERN));
            vo.setStatus(e.getStatus());
            vo.setRemark(e.getRemark());
            vo.setCreateDate(e.getCreateDate() == null ? null : DateUtils.format(e.getCreateDate(), DateUtils.DATE_TIME_PATTERN));
            return vo;
        }).collect(Collectors.toList());
        return new PageData<>(list, p.getTotal());
    }

    @Override
    @Transactional(rollbackFor = Exception.class)
    public void customVoiceAudit(AdminCustomAuditDTO dto) {
        SysUserCustomVoiceEntity e = sysUserCustomVoiceDao.selectById(dto.getId());
        if (e == null) {
            throw new RenException(ErrorCode.ADMIN_CUSTOM_NOT_EXIST);
        }
        boolean pass = Boolean.TRUE.equals(dto.getPass());
        if (!pass && StringUtils.isBlank(dto.getRemark())) {
            throw new RenException(ErrorCode.ADMIN_AUDIT_REMARK_REQUIRED);
        }
        UpdateWrapper<SysUserCustomVoiceEntity> uw = new UpdateWrapper<SysUserCustomVoiceEntity>()
                .eq("id", dto.getId())
                .set("audit_status", pass ? 1 : 2)
                .set("audit_remark", pass ? null : dto.getRemark())
                .set("auditor", SecurityUser.getUserId())
                .set("audit_date", new Date())
                .set("updater", SecurityUser.getUserId())
                .set("update_date", new Date());
        sysUserCustomVoiceDao.update(null, uw);
    }

    private String usernameOf(Long userId) {
        if (userId == null) {
            return null;
        }
        SysUserEntity u = sysUserDao.selectById(userId);
        return u == null ? null : u.getUsername();
    }
}

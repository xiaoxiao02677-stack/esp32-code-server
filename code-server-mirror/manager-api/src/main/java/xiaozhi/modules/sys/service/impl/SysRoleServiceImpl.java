package xiaozhi.modules.sys.service.impl;

import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;
import java.util.stream.Collectors;
import java.util.stream.Stream;

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
import xiaozhi.common.utils.JsonUtils;
import xiaozhi.modules.sys.dao.SysRoleDao;
import xiaozhi.modules.sys.dao.SysUserDao;
import xiaozhi.modules.sys.dao.SysUserRoleDao;
import xiaozhi.modules.sys.dto.SysRoleDTO;
import xiaozhi.modules.sys.entity.SysRoleEntity;
import xiaozhi.modules.sys.entity.SysUserEntity;
import xiaozhi.modules.sys.entity.SysUserRoleEntity;
import xiaozhi.modules.sys.service.AuditService;
import xiaozhi.modules.sys.service.SysRoleService;
import xiaozhi.modules.sys.vo.SysRoleVO;

/**
 * 角色
 */
@Service
@AllArgsConstructor
public class SysRoleServiceImpl extends BaseServiceImpl<SysRoleDao, SysRoleEntity>
        implements SysRoleService {

    /** 保留角色编码：不允许通过接口新建同名编码 */
    private static final List<String> RESERVED_CODES = Arrays.asList("super_admin", "admin", "user", "readonly");

    private final SysUserRoleDao sysUserRoleDao;
    private final SysUserDao sysUserDao;
    private final AuditService auditService;

    @Override
    public PageData<SysRoleVO> page(Map<String, Object> params) {
        // 多字段排序：sort asc, id asc（通过 ORDER_FIELD 传递）
        params.put(Constant.ORDER_FIELD, Arrays.asList("sort", "id"));
        IPage<SysRoleEntity> page = baseDao.selectPage(getPage(params, "id", true),
                getWrapper(params));

        List<SysRoleVO> voList = page.getRecords().stream().map(this::toVo).collect(Collectors.toList());
        fillExtra(voList);

        PageData<SysRoleVO> pageData = new PageData<>(voList, page.getTotal());
        return pageData;
    }

    private QueryWrapper<SysRoleEntity> getWrapper(Map<String, Object> params) {
        String keyword = (String) params.get("keyword");

        QueryWrapper<SysRoleEntity> wrapper = new QueryWrapper<>();
        if (StringUtils.isNotBlank(keyword)) {
            wrapper.and(w -> w.like("role_code", keyword).or().like("role_name", keyword));
        }
        return wrapper;
    }

    @Override
    public List<SysRoleVO> listEnabled() {
        LambdaQueryWrapper<SysRoleEntity> wrapper = new LambdaQueryWrapper<>();
        wrapper.eq(SysRoleEntity::getStatus, 1);
        wrapper.orderByAsc(SysRoleEntity::getSort).orderByAsc(SysRoleEntity::getId);
        List<SysRoleEntity> list = baseDao.selectList(wrapper);

        List<SysRoleVO> voList = list.stream().map(this::toVo).collect(Collectors.toList());
        return voList;
    }

    @Override
    public SysRoleVO get(Long id) {
        SysRoleEntity entity = baseDao.selectById(id);
        if (entity == null) {
            throw new RenException(ErrorCode.ROLE_NOT_FOUND);
        }
        SysRoleVO vo = toVo(entity);
        fillExtra(Collections.singletonList(vo));
        return vo;
    }

    @Override
    @Transactional(rollbackFor = Exception.class)
    public void save(SysRoleDTO dto) {
        // 保留码校验：接口不允许新建内置保留编码
        if (RESERVED_CODES.contains(dto.getRoleCode())) {
            throw new RenException(ErrorCode.ROLE_CODE_EXISTS);
        }
        checkRoleCodeUnique(dto.getRoleCode(), null);

        SysRoleEntity entity = ConvertUtils.sourceToTarget(dto, SysRoleEntity.class);
        entity.setPermissions(toPermissionsJson(dto.getPermissions()));
        entity.setIsBuiltin(0);
        insert(entity);

        auditService.log("role", "create", "sys_role", String.valueOf(entity.getId()), dto, true, null);
    }

    @Override
    @Transactional(rollbackFor = Exception.class)
    public void update(SysRoleDTO dto) {
        SysRoleEntity exists = baseDao.selectById(dto.getId());
        if (exists == null) {
            throw new RenException(ErrorCode.ROLE_NOT_FOUND);
        }

        SysRoleEntity entity;
        if (exists.getIsBuiltin() != null && exists.getIsBuiltin() == 1) {
            // 内置角色：仅允许改 permissions / remark
            entity = new SysRoleEntity();
            entity.setId(dto.getId());
            entity.setPermissions(toPermissionsJson(dto.getPermissions()));
            entity.setRemark(dto.getRemark());
        } else {
            checkRoleCodeUnique(dto.getRoleCode(), String.valueOf(dto.getId()));
            entity = ConvertUtils.sourceToTarget(dto, SysRoleEntity.class);
            entity.setPermissions(toPermissionsJson(dto.getPermissions()));
            // 编码/内置标记不允许改
            entity.setRoleCode(exists.getRoleCode());
            entity.setIsBuiltin(0);
        }
        updateById(entity);

        auditService.log("role", "update", "sys_role", String.valueOf(dto.getId()), dto, true, null);
    }

    @Override
    @Transactional(rollbackFor = Exception.class)
    public void delete(Long[] ids) {
        for (Long id : ids) {
            SysRoleEntity entity = baseDao.selectById(id);
            if (entity == null) {
                continue;
            }
            if (entity.getIsBuiltin() != null && entity.getIsBuiltin() == 1) {
                throw new RenException(ErrorCode.ROLE_BUILTIN);
            }
        }

        for (Long id : ids) {
            // 清理用户关联
            LambdaQueryWrapper<SysUserRoleEntity> wrapper = new LambdaQueryWrapper<>();
            wrapper.eq(SysUserRoleEntity::getRoleId, id);
            sysUserRoleDao.delete(wrapper);
        }
        deleteBatchIds(Arrays.asList(ids));

        for (Long id : ids) {
            auditService.log("role", "delete", "sys_role", String.valueOf(id), null, true, null);
        }
    }

    @Override
    public List<String> getRoleCodesByUserId(Long userId) {
        return getRolesByUserIdInternal(userId, false).stream().map(SysRoleEntity::getRoleCode)
                .collect(Collectors.toList());
    }

    @Override
    public List<Long> getRoleIdsByUserId(Long userId) {
        return getRolesByUserIdInternal(userId, false).stream().map(SysRoleEntity::getId)
                .collect(Collectors.toList());
    }

    @Override
    public List<SysRoleEntity> getEnabledRolesByUserId(Long userId) {
        return getRolesByUserIdInternal(userId, true);
    }

    @Override
    public List<SysRoleEntity> getRolesByIds(List<Long> roleIds) {
        if (roleIds == null || roleIds.isEmpty()) {
            return new ArrayList<>();
        }
        return baseDao.selectByIds(roleIds);
    }

    private List<SysRoleEntity> getRolesByUserIdInternal(Long userId, boolean onlyEnabled) {
        if (userId == null) {
            return new ArrayList<>();
        }
        LambdaQueryWrapper<SysUserRoleEntity> urWrapper = new LambdaQueryWrapper<>();
        urWrapper.eq(SysUserRoleEntity::getUserId, userId);
        List<SysUserRoleEntity> relations = sysUserRoleDao.selectList(urWrapper);
        if (relations.isEmpty()) {
            return new ArrayList<>();
        }

        List<Long> roleIds = relations.stream().map(SysUserRoleEntity::getRoleId).distinct()
                .collect(Collectors.toList());
        List<SysRoleEntity> roles = baseDao.selectByIds(roleIds);
        if (onlyEnabled) {
            roles = roles.stream()
                    .filter(r -> r.getStatus() != null && r.getStatus() == 1)
                    .collect(Collectors.toList());
        }
        return roles;
    }

    @Override
    @Transactional(rollbackFor = Exception.class)
    public void assignUserRoles(Long userId, List<Long> roleIds) {
        // 全删
        LambdaQueryWrapper<SysUserRoleEntity> wrapper = new LambdaQueryWrapper<>();
        wrapper.eq(SysUserRoleEntity::getUserId, userId);
        sysUserRoleDao.delete(wrapper);

        // 全插
        if (roleIds != null && !roleIds.isEmpty()) {
            List<Long> distinctIds = roleIds.stream().distinct().collect(Collectors.toList());
            List<SysRoleEntity> roles = baseDao.selectByIds(distinctIds);
            if (roles.size() != distinctIds.size()) {
                throw new RenException(ErrorCode.ROLE_NOT_FOUND);
            }
            for (Long roleId : distinctIds) {
                SysUserRoleEntity rel = new SysUserRoleEntity();
                rel.setUserId(userId);
                rel.setRoleId(roleId);
                sysUserRoleDao.insert(rel);
            }
        }
    }

    // ==================== 私有工具 ====================

    /** entity → VO（permissions JSON 字符串 → List<String>） */
    private SysRoleVO toVo(SysRoleEntity entity) {
        SysRoleVO vo = ConvertUtils.sourceToTarget(entity, SysRoleVO.class);
        if (vo != null) {
            vo.setPermissions(parsePermissions(entity.getPermissions()));
        }
        return vo;
    }

    /** permissions List → JSON 字符串（null 安全） */
    private String toPermissionsJson(List<String> permissions) {
        if (permissions == null || permissions.isEmpty()) {
            return "[]";
        }
        return JsonUtils.toJsonString(permissions);
    }

    /** permissions JSON 字符串 → List */
    private List<String> parsePermissions(String json) {
        if (StringUtils.isBlank(json) || "null".equals(json)) {
            return new ArrayList<>();
        }
        try {
            List<String> list = JsonUtils.parseArray(json, String.class);
            return list == null ? new ArrayList<>() : list;
        } catch (Exception e) {
            return new ArrayList<>();
        }
    }

    /** 填充 userCount / creatorName / updaterName */
    private void fillExtra(List<SysRoleVO> voList) {
        if (voList == null || voList.isEmpty()) {
            return;
        }
        // userCount
        List<Long> roleIds = voList.stream().map(SysRoleVO::getId).collect(Collectors.toList());
        LambdaQueryWrapper<SysUserRoleEntity> countWrapper = new LambdaQueryWrapper<>();
        countWrapper.in(SysUserRoleEntity::getRoleId, roleIds);
        List<SysUserRoleEntity> relations = sysUserRoleDao.selectList(countWrapper);
        Map<Long, Long> countMap = relations.stream().collect(
                Collectors.groupingBy(SysUserRoleEntity::getRoleId, Collectors.counting()));
        voList.forEach(vo -> vo.setUserCount(countMap.getOrDefault(vo.getId(), 0L)));

        // creator/updater 名称
        Set<Long> userIds = voList.stream().flatMap(vo -> Stream.of(vo.getCreator(), vo.getUpdater()))
                .filter(Objects::nonNull).collect(Collectors.toSet());
        if (!userIds.isEmpty()) {
            List<SysUserEntity> users = sysUserDao.selectByIds(userIds);
            Map<Long, String> userNameMap = users.stream().collect(
                    Collectors.toMap(SysUserEntity::getId, SysUserEntity::getUsername, (a, b) -> a));
            voList.forEach(vo -> {
                vo.setCreatorName(userNameMap.get(vo.getCreator()));
                vo.setUpdaterName(userNameMap.get(vo.getUpdater()));
            });
        }
    }

    private void checkRoleCodeUnique(String roleCode, String excludeId) {
        LambdaQueryWrapper<SysRoleEntity> queryWrapper = new LambdaQueryWrapper<>();
        queryWrapper.eq(SysRoleEntity::getRoleCode, roleCode);
        if (StringUtils.isNotBlank(excludeId)) {
            queryWrapper.ne(SysRoleEntity::getId, excludeId);
        }
        if (baseDao.exists(queryWrapper)) {
            throw new RenException(ErrorCode.ROLE_CODE_EXISTS);
        }
    }
}

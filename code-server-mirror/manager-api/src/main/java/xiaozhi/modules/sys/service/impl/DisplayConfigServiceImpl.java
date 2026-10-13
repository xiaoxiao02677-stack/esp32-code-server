package xiaozhi.modules.sys.service.impl;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

import org.apache.commons.lang3.StringUtils;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.fasterxml.jackson.databind.JsonNode;

import lombok.AllArgsConstructor;
import xiaozhi.common.exception.ErrorCode;
import xiaozhi.common.exception.RenException;
import xiaozhi.common.utils.JsonUtils;
import xiaozhi.modules.sys.dao.SysDisplayConfigDao;
import xiaozhi.modules.sys.entity.SysDisplayConfigEntity;
import xiaozhi.modules.sys.enums.ScopeTypeEnum;
import xiaozhi.modules.sys.service.DisplayConfigService;
import xiaozhi.modules.sys.service.SysRoleService;

/**
 * 展示项配置实现。
 * <p>
 * 三级继承合并规则：用户(2) > 角色(1) > 系统(0)。
 * configJson 结构 {"fields":{field:{visible,editable}}}——fields 同名字段按层级覆盖；
 * 缺省 field 视为 {"visible":true,"editable":true}（由前端处理，后端原样透传合并结果）。
 * </p>
 */
@Service
@AllArgsConstructor
public class DisplayConfigServiceImpl implements DisplayConfigService {

    private final SysDisplayConfigDao sysDisplayConfigDao;
    private final SysRoleService sysRoleService;

    @Override
    public Map<String, Object> getConfig(Integer scopeType, Long roleId, Long userId) {
        ScopeTypeEnum scope = ScopeTypeEnum.of(scopeType);
        validateScopeIds(scope, roleId, userId);

        SysDisplayConfigEntity entity = findEntity(scopeType, roleId, userId);
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("scopeType", scopeType);
        result.put("roleId", roleId == null ? 0L : roleId);
        result.put("userId", userId == null ? 0L : userId);
        result.put("configJson", entity == null ? null : parseJson(entity.getConfigJson()));
        return result;
    }

    @Override
    @Transactional(rollbackFor = Exception.class)
    public void saveConfig(Integer scopeType, Long roleId, Long userId, String configJson) {
        ScopeTypeEnum scope = ScopeTypeEnum.of(scopeType);
        validateScopeIds(scope, roleId, userId);

        // configJson 合法性校验（必须是可解析 JSON 对象）
        if (StringUtils.isBlank(configJson)) {
            throw new RenException(ErrorCode.DISPLAY_CONFIG_SCOPE);
        }
        try {
            JsonNode node = JsonUtils.parseObject(configJson, JsonNode.class);
            if (node == null || !node.isObject()) {
                throw new RenException(ErrorCode.DISPLAY_CONFIG_SCOPE);
            }
        } catch (RenException e) {
            throw e;
        } catch (Exception e) {
            throw new RenException(ErrorCode.DISPLAY_CONFIG_SCOPE);
        }

        SysDisplayConfigEntity entity = findEntity(scopeType, roleId, userId);
        if (entity == null) {
            entity = new SysDisplayConfigEntity();
            entity.setScopeType(scopeType);
            entity.setRoleId(roleId == null ? 0L : roleId);
            entity.setUserId(userId == null ? 0L : userId);
            entity.setConfigJson(configJson);
            sysDisplayConfigDao.insert(entity);
        } else {
            entity.setConfigJson(configJson);
            sysDisplayConfigDao.updateById(entity);
        }
    }

    @Override
    public Map<String, Object> getEffectiveForUser(Long userId) {
        // 用户全部角色（含停用角色过滤：启用角色才参与继承）
        List<Long> roleIds = new ArrayList<>();
        if (userId != null) {
            roleIds = sysRoleService.getRoleIdsByUserId(userId);
        }

        // 层级：系统(0) → 角色(1, 取第一个有配置的角色) → 用户(2)
        Map<String, Object> merged = new LinkedHashMap<>();
        merged.put("fields", new LinkedHashMap<String, Object>());

        // 1) 系统
        SysDisplayConfigEntity system = findEntity(0, 0L, 0L);
        mergeInto(merged, system);

        // 2) 角色（按角色 ID 升序，后者覆盖前者）
        for (Long roleId : roleIds.stream().sorted().toList()) {
            SysDisplayConfigEntity roleCfg = findEntity(1, roleId, 0L);
            mergeInto(merged, roleCfg);
        }

        // 3) 用户
        if (userId != null) {
            SysDisplayConfigEntity userCfg = findEntity(2, 0L, userId);
            mergeInto(merged, userCfg);
        }

        Map<String, Object> result = new LinkedHashMap<>();
        result.put("scopeChain", List.of("system", "role", "user"));
        result.put("fields", merged.get("fields"));
        return result;
    }

    @Override
    public SysDisplayConfigEntity findEntity(Integer scopeType, Long roleId, Long userId) {
        LambdaQueryWrapper<SysDisplayConfigEntity> wrapper = new LambdaQueryWrapper<>();
        wrapper.eq(SysDisplayConfigEntity::getScopeType, scopeType);
        wrapper.eq(SysDisplayConfigEntity::getRoleId, roleId == null ? 0L : roleId);
        wrapper.eq(SysDisplayConfigEntity::getUserId, userId == null ? 0L : userId);
        return sysDisplayConfigDao.selectOne(wrapper);
    }

    // ==================== 私有工具 ====================

    /** 深合并：source 的 fields 同名项覆盖 target */
    @SuppressWarnings("unchecked")
    private void mergeInto(Map<String, Object> target, SysDisplayConfigEntity source) {
        if (source == null || StringUtils.isBlank(source.getConfigJson())) {
            return;
        }
        try {
            JsonNode node = JsonUtils.parseObject(source.getConfigJson(), JsonNode.class);
            if (node == null || !node.isObject()) {
                return;
            }
            JsonNode fields = node.get("fields");
            if (fields == null || !fields.isObject()) {
                return;
            }
            Map<String, Object> targetFields = (Map<String, Object>) target.get("fields");
            fields.fieldNames().forEachRemaining(fieldName -> {
                JsonNode fieldCfg = fields.get(fieldName);
                try {
                    targetFields.put(fieldName,
                            JsonUtils.parseObject(fieldCfg.toString(), Object.class));
                } catch (Exception ignore) {
                }
            });
        } catch (Exception ignore) {
            // 单层配置解析失败跳过，不影响其他层级
        }
    }

    private Object parseJson(String json) {
        if (StringUtils.isBlank(json)) {
            return null;
        }
        try {
            return JsonUtils.parseObject(json, Object.class);
        } catch (Exception e) {
            return json;
        }
    }

    /** scope 对应的 ID 必填校验（sentinel 0） */
    private void validateScopeIds(ScopeTypeEnum scope, Long roleId, Long userId) {
        switch (scope) {
        case SYSTEM -> {
            // 系统级无需 roleId/userId
        }
        case ROLE -> {
            if (roleId == null || roleId <= 0) {
                throw new RenException(ErrorCode.DISPLAY_CONFIG_SCOPE);
            }
        }
        case USER -> {
            if (userId == null || userId <= 0) {
                throw new RenException(ErrorCode.DISPLAY_CONFIG_SCOPE);
            }
        }
        }
    }
}

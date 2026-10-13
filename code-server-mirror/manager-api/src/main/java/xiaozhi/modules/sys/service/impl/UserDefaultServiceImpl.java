package xiaozhi.modules.sys.service.impl;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

import org.apache.commons.lang3.StringUtils;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;

import lombok.AllArgsConstructor;
import xiaozhi.common.exception.ErrorCode;
import xiaozhi.common.exception.RenException;
import xiaozhi.common.utils.JsonUtils;
import xiaozhi.modules.model.entity.ModelConfigEntity;
import xiaozhi.modules.model.service.ModelConfigService;
import xiaozhi.modules.sys.dao.SysUserDefaultDao;
import xiaozhi.modules.sys.entity.SysUserDefaultEntity;
import xiaozhi.modules.sys.enums.ScopeTypeEnum;
import xiaozhi.modules.sys.service.SysRoleService;
import xiaozhi.modules.sys.service.UserDefaultService;
import xiaozhi.modules.timbre.dao.TimbreDao;
import xiaozhi.modules.timbre.entity.TimbreEntity;

/**
 * 默认模型/音色/参数配置实现。
 * <p>
 * 三级继承：用户(2) > 角色(1) > 平台(0)；同字段下级覆盖上级；
 * 上级 lockPolicy=1（锁定）时下级不允许覆盖该配置（查询时锁定层级即最终值）。
 * </p>
 */
@Service
@AllArgsConstructor
public class UserDefaultServiceImpl implements UserDefaultService {

    private final SysUserDefaultDao sysUserDefaultDao;
    private final SysRoleService sysRoleService;
    private final ModelConfigService modelConfigService;
    private final TimbreDao timbreDao;

    @Override
    public Map<String, Object> getConfig(Integer scopeType, Long roleId, Long userId) {
        ScopeTypeEnum scope = ScopeTypeEnum.of(scopeType);
        validateScopeIds(scope, roleId, userId);

        SysUserDefaultEntity entity = findEntity(scopeType, roleId, userId);
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("scopeType", scopeType);
        result.put("roleId", roleId == null ? 0L : roleId);
        result.put("userId", userId == null ? 0L : userId);
        if (entity == null) {
            result.put("llmModelId", null);
            result.put("ttsModelId", null);
            result.put("ttsVoiceId", null);
            result.put("asrModelId", null);
            result.put("paramJson", null);
            result.put("lockPolicy", null);
        } else {
            result.put("llmModelId", entity.getLlmModelId());
            result.put("ttsModelId", entity.getTtsModelId());
            result.put("ttsVoiceId", entity.getTtsVoiceId());
            result.put("asrModelId", entity.getAsrModelId());
            result.put("paramJson", parseJson(entity.getParamJson()));
            result.put("lockPolicy", entity.getLockPolicy());
        }
        return result;
    }

    @Override
    @Transactional(rollbackFor = Exception.class)
    public void saveConfig(Integer scopeType, Long roleId, Long userId, String llmModelId,
            String ttsModelId, String ttsVoiceId, String asrModelId, String paramJson, Integer lockPolicy) {
        ScopeTypeEnum scope = ScopeTypeEnum.of(scopeType);
        validateScopeIds(scope, roleId, userId);

        // 模型/音色 id 存在且启用校验（10231/10232）
        validateModelId(llmModelId, "LLM");
        validateModelId(ttsModelId, "TTS");
        validateModelId(asrModelId, "ASR");
        validateVoiceId(ttsVoiceId);

        // paramJson 合法性
        if (StringUtils.isNotBlank(paramJson)) {
            try {
                var node = JsonUtils.parseObject(paramJson, com.fasterxml.jackson.databind.JsonNode.class);
                if (node == null || !node.isObject()) {
                    throw new RenException(ErrorCode.DEFAULT_MODEL_INVALID);
                }
            } catch (RenException e) {
                throw e;
            } catch (Exception e) {
                throw new RenException(ErrorCode.DEFAULT_MODEL_INVALID);
            }
        }

        SysUserDefaultEntity entity = findEntity(scopeType, roleId, userId);
        if (entity == null) {
            entity = new SysUserDefaultEntity();
            entity.setScopeType(scopeType);
            entity.setRoleId(roleId == null ? 0L : roleId);
            entity.setUserId(userId == null ? 0L : userId);
            entity.setLlmModelId(llmModelId);
            entity.setTtsModelId(ttsModelId);
            entity.setTtsVoiceId(ttsVoiceId);
            entity.setAsrModelId(asrModelId);
            entity.setParamJson(paramJson);
            entity.setLockPolicy(lockPolicy == null ? 0 : lockPolicy);
            sysUserDefaultDao.insert(entity);
        } else {
            entity.setLlmModelId(llmModelId);
            entity.setTtsModelId(ttsModelId);
            entity.setTtsVoiceId(ttsVoiceId);
            entity.setAsrModelId(asrModelId);
            entity.setParamJson(paramJson);
            entity.setLockPolicy(lockPolicy == null ? 0 : lockPolicy);
            sysUserDefaultDao.updateById(entity);
        }
    }

    @Override
    public Map<String, Object> getEffectiveForUser(Long userId) {
        List<Long> roleIds = new ArrayList<>();
        if (userId != null) {
            roleIds = sysRoleService.getRoleIdsByUserId(userId);
        }

        // 逐字段三级合并；lockPolicy=1 的层级锁定后续覆盖
        Map<String, Object> effective = new LinkedHashMap<>();
        Integer lockedAt = null; // 锁定层级：null 未锁定

        // 1) 平台(0)
        SysUserDefaultEntity platform = findEntity(0, 0L, 0L);
        if (platform != null) {
            applyLayer(effective, platform);
            if (platform.getLockPolicy() != null && platform.getLockPolicy() == 1) {
                lockedAt = 0;
            }
        }

        // 2) 角色（角色 ID 升序）
        if (lockedAt == null) {
            for (Long roleId : roleIds.stream().sorted().toList()) {
                SysUserDefaultEntity roleCfg = findEntity(1, roleId, 0L);
                if (roleCfg == null) {
                    continue;
                }
                applyLayer(effective, roleCfg);
                if (roleCfg.getLockPolicy() != null && roleCfg.getLockPolicy() == 1) {
                    lockedAt = 1;
                    break; // 锁定后不再应用更深层级
                }
            }
        }

        // 3) 用户
        boolean userLocked = false;
        if (lockedAt == null && userId != null) {
            SysUserDefaultEntity userCfg = findEntity(2, 0L, userId);
            if (userCfg != null) {
                applyLayer(effective, userCfg);
                if (userCfg.getLockPolicy() != null && userCfg.getLockPolicy() == 1) {
                    userLocked = true;
                }
            }
        }

        effective.put("lockPolicy", lockedAt != null ? lockedAt : (userLocked ? 2 : 0));
        effective.put("locked", lockedAt != null);
        return effective;
    }

    @Override
    public SysUserDefaultEntity findEntity(Integer scopeType, Long roleId, Long userId) {
        LambdaQueryWrapper<SysUserDefaultEntity> wrapper = new LambdaQueryWrapper<>();
        wrapper.eq(SysUserDefaultEntity::getScopeType, scopeType);
        wrapper.eq(SysUserDefaultEntity::getRoleId, roleId == null ? 0L : roleId);
        wrapper.eq(SysUserDefaultEntity::getUserId, userId == null ? 0L : userId);
        return sysUserDefaultDao.selectOne(wrapper);
    }

    // ==================== 私有工具 ====================

    /** 非空字段覆盖 */
    private void applyLayer(Map<String, Object> effective, SysUserDefaultEntity layer) {
        if (layer.getLlmModelId() != null) {
            effective.put("llmModelId", layer.getLlmModelId());
        }
        if (layer.getTtsModelId() != null) {
            effective.put("ttsModelId", layer.getTtsModelId());
        }
        if (layer.getTtsVoiceId() != null) {
            effective.put("ttsVoiceId", layer.getTtsVoiceId());
        }
        if (layer.getAsrModelId() != null) {
            effective.put("asrModelId", layer.getAsrModelId());
        }
        if (StringUtils.isNotBlank(layer.getParamJson())) {
            try {
                effective.put("paramJson", JsonUtils.parseObject(layer.getParamJson(), Object.class));
            } catch (Exception ignore) {
            }
        }
    }

    private void validateModelId(String modelId, String typeLabel) {
        if (StringUtils.isBlank(modelId)) {
            return;
        }
        ModelConfigEntity model = modelConfigService.selectById(modelId);
        if (model == null || model.getIsEnabled() == null || model.getIsEnabled() != 1) {
            throw new RenException(ErrorCode.DEFAULT_MODEL_INVALID);
        }
    }

    private void validateVoiceId(String voiceId) {
        if (StringUtils.isBlank(voiceId)) {
            return;
        }
        TimbreEntity voice = timbreDao.selectById(voiceId);
        if (voice == null) {
            throw new RenException(ErrorCode.DEFAULT_VOICE_INVALID);
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

    private void validateScopeIds(ScopeTypeEnum scope, Long roleId, Long userId) {
        switch (scope) {
        case SYSTEM -> {
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

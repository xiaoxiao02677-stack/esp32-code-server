package xiaozhi.modules.sys.service;

import java.util.Map;

import xiaozhi.modules.sys.entity.SysUserDefaultEntity;

/**
 * 默认模型/音色/参数配置（平台→角色→用户三级，冲突按 lock_policy）
 */
public interface UserDefaultService {

    /** 管理端查询某 scope 的默认配置 */
    Map<String, Object> getConfig(Integer scopeType, Long roleId, Long userId);

    /** upsert（模型/音色 id 校验 10231/10232） */
    void saveConfig(Integer scopeType, Long roleId, Long userId, String llmModelId,
            String ttsModelId, String ttsVoiceId, String asrModelId, String paramJson, Integer lockPolicy);

    /** 用户端生效配置：用户>角色>平台合并，带 lockPolicy 标记 */
    Map<String, Object> getEffectiveForUser(Long userId);

    /** 内部：按 scope 查实体 */
    SysUserDefaultEntity findEntity(Integer scopeType, Long roleId, Long userId);
}

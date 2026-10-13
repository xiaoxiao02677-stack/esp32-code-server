package xiaozhi.modules.sys.service;

import java.util.Map;

import xiaozhi.modules.sys.entity.SysDisplayConfigEntity;

/**
 * 展示项配置（系统→角色→用户三级覆盖）
 */
public interface DisplayConfigService {

    /** 管理端查询某 scope 的配置（无则返回 null data） */
    Map<String, Object> getConfig(Integer scopeType, Long roleId, Long userId);

    /** upsert（校验 10230；scope 对应 roleId/userId 必填） */
    void saveConfig(Integer scopeType, Long roleId, Long userId, String configJson);

    /** 用户端生效配置：用户>角色>系统合并（同 key 用户覆盖角色覆盖系统） */
    Map<String, Object> getEffectiveForUser(Long userId);

    /** 内部：按 scope 查实体 */
    SysDisplayConfigEntity findEntity(Integer scopeType, Long roleId, Long userId);
}

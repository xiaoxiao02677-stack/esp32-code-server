package yuhe.modules.agent.service;

import java.util.List;
import java.util.Map;

import yuhe.modules.agent.entity.AgentShareEntity;

/**
 * 智能体共享授权
 */
public interface AgentShareService {

    /** 查询某智能体的共享配置（回显用） */
    List<AgentShareEntity> listByAgentId(String agentId);

    /**
     * 全量覆盖保存某智能体的共享配置（超管抽屉保存）。
     * 返回清理后的可见性缓存键集合说明（当前无缓存，预留给调用方记日志）。
     */
    void saveAgentShares(String agentId, List<Map<String, Object>> shares, Long operatorId);

    /** 用户是否有某智能体的共享授权（权限闸门） */
    boolean isSharedToUser(String agentId, Long userId);

    /** 用户可见的共享智能体ID集合（列表扩展用） */
    List<String> getSharedAgentIds(Long userId);

    /** 删除智能体时级联清理共享配置 */
    void deleteByAgentId(String agentId);
}

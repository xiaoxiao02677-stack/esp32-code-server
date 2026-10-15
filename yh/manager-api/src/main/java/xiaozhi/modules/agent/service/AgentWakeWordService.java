package xiaozhi.modules.agent.service;

import xiaozhi.modules.agent.entity.AgentWakeWordEntity;

/**
 * 智能体唤醒词 Service
 *
 * @author xiaozhi
 */
public interface AgentWakeWordService {

    /**
     * 获取智能体的唤醒词配置（若存在）
     */
    AgentWakeWordEntity getByAgentId(String agentId);

    /**
     * 保存/更新智能体的唤醒词配置（upsert）
     *
     * @param entity 配置实体（id 为空则新建，否则更新）
     * @param userId 当前操作用户 ID
     * @return 保存后的实体
     */
    AgentWakeWordEntity saveOrUpdate(AgentWakeWordEntity entity, Long userId);

    /**
     * 删除智能体的唤醒词配置
     *
     * @param agentId 智能体 ID
     * @param userId  当前操作用户 ID
     * @return 是否成功
     */
    boolean deleteByAgentId(String agentId, Long userId);
}

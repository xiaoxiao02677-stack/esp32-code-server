package yuhe.modules.agent.service;

import java.util.List;
import java.util.Map;

import yuhe.modules.agent.entity.AgentMcpConfigEntity;

/**
 * 智能体 MCP Server 配置 Service
 *
 * @author yuhe
 */
public interface AgentMcpConfigService {

    /**
     * 获取智能体的 MCP 配置（若存在）
     */
    AgentMcpConfigEntity getByAgentId(String agentId);

    /**
     * 保存/更新智能体的 MCP 配置（upsert）
     *
     * @param entity 配置实体（id 为空则新建，否则更新）
     * @param userId 当前操作用户 ID
     * @return 保存后的实体
     */
    AgentMcpConfigEntity saveOrUpdate(AgentMcpConfigEntity entity, Long userId);

    /**
     * 删除智能体的 MCP 配置
     *
     * @param agentId 智能体 ID
     * @param userId  当前操作用户 ID
     * @return 是否成功
     */
    boolean deleteByAgentId(String agentId, Long userId);

    /**
     * 测试 MCP 配置的 JSON 合法性（不连接网络）
     *
     * @param serverJson JSON 字符串
     * @return {"valid": true/false, "message": "..."}
     */
    Map<String, Object> validateJson(String serverJson);
}

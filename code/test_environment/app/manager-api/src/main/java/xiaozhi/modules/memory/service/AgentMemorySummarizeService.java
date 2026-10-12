package xiaozhi.modules.memory.service;

/**
 * 记忆快速总结服务：把智能体近期会话一键总结并写入记忆条目
 */
public interface AgentMemorySummarizeService {

    /**
     * 总结指定智能体近期会话，并将总结写为一条 summary 类型记忆条目
     *
     * @param agentId 智能体ID
     * @param userId  当前用户ID（用于权限校验与记忆写入）
     * @return 总结文本
     */
    String summarizeAgentChats(String agentId, Long userId);
}

package xiaozhi.modules.memory.service.impl;

import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.Map;

import org.apache.commons.lang3.StringUtils;
import org.springframework.stereotype.Service;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.baomidou.mybatisplus.core.metadata.IPage;
import com.baomidou.mybatisplus.extension.plugins.pagination.Page;

import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import xiaozhi.common.exception.ErrorCode;
import xiaozhi.common.exception.RenException;
import xiaozhi.common.utils.JsonUtils;
import xiaozhi.modules.agent.Enums.AgentChatHistoryType;
import xiaozhi.modules.agent.entity.AgentChatHistoryEntity;
import xiaozhi.modules.agent.service.AgentChatHistoryService;
import xiaozhi.modules.agent.service.AgentService;
import xiaozhi.modules.agent.vo.AgentInfoVO;
import xiaozhi.modules.llm.service.LLMService;
import xiaozhi.modules.memory.dto.MemoryFactDTO;
import xiaozhi.modules.memory.service.AgentMemorySummarizeService;
import xiaozhi.modules.memory.service.MemoryFactService;
import xiaozhi.modules.model.entity.ModelConfigEntity;
import xiaozhi.modules.model.service.ModelConfigService;

/**
 * 记忆快速总结服务实现：取智能体近期 user/assistant 会话 → LLM 总结 → 写入 summary 类型记忆条目
 */
@Slf4j
@Service
@RequiredArgsConstructor
public class AgentMemorySummarizeServiceImpl implements AgentMemorySummarizeService {

    /** 参与总结的最近消息条数（用户与智能体消息合计） */
    private static final int RECENT_MESSAGE_LIMIT = 20;

    /** 总结写入记忆条目时使用的类型 */
    private static final String SUMMARY_CATEGORY = "summary";

    /** 会话总结提示词（{conversation} 占位符由 LLM 服务替换） */
    private static final String CHAT_SUMMARY_PROMPT = "你是一个智能体记忆管理助手。请把下面这段智能体与用户的近期对话，总结成一条适合长期保存的记忆，规则：\n"
            + "1、只提炼用户透露的偏好、习惯、个人情况、计划安排、重要事件等有价值信息\n"
            + "2、忽略设备控制、音量播放、天气时间等与用户本身无关的内容和无意义寒暄\n"
            + "3、用第三人称中文简洁陈述，直接输出记忆内容本身，不要解释、标题或格式符号\n"
            + "4、控制在500字以内\n\n对话内容：\n{conversation}";

    /** LLM 服务出错时返回的固定文案（OpenAIStyleLLMServiceImpl 不抛异常而是返回错误串） */
    private static final List<String> LLM_FAILURE_REPLIES = List.of(
            "LLM服务不可用，无法生成总结",
            "未找到可用的LLM模型配置",
            "LLM配置不完整，无法生成总结",
            "生成总结失败，请稍后重试");

    private final AgentChatHistoryService agentChatHistoryService;
    private final AgentService agentService;
    private final MemoryFactService memoryFactService;
    private final ModelConfigService modelConfigService;
    private final LLMService llmService;

    @Override
    public String summarizeAgentChats(String agentId, Long userId) {
        if (StringUtils.isBlank(agentId)) {
            throw new RenException(ErrorCode.PARAMS_GET_ERROR);
        }

        // 智能体存在性与权限校验（不存在/无权限时由 AgentService 抛出异常）
        AgentInfoVO agent = agentService.getAgentById(agentId, userId);

        // 取最近 N 条 user/assistant 消息，按时间正序拼接对话
        List<AgentChatHistoryEntity> recentMessages = getRecentMessages(agentId);
        String conversation = buildConversationText(recentMessages);
        if (StringUtils.isBlank(conversation)) {
            throw new RenException("该智能体近期没有可总结的会话记录");
        }

        // 调 LLM 生成总结：智能体 llmModelId 优先，无则回落默认 LLM
        String modelId = resolveLlmModelId(agent);
        String summary = llmService.generateSummary(conversation, CHAT_SUMMARY_PROMPT, modelId);
        if (StringUtils.isBlank(summary)) {
            throw new RenException("生成会话总结失败");
        }
        summary = summary.trim();
        if (LLM_FAILURE_REPLIES.contains(summary)) {
            log.error("智能体 {} 会话总结生成失败: {}", agentId, summary);
            throw new RenException(summary);
        }

        // 等价 POST /memory/facts：写入一条 summary 类型记忆条目（内部含权限与引擎校验）
        MemoryFactDTO factDTO = new MemoryFactDTO();
        factDTO.setAgentId(agentId);
        factDTO.setContent(summary);
        factDTO.setCategory(SUMMARY_CATEGORY);
        MemoryFactDTO saved = memoryFactService.saveFact(factDTO, userId);

        log.info("智能体 {} 近期会话总结已写入记忆条目 factId={}, 总结长度={}",
                agentId, saved != null ? saved.getFactId() : null, summary.length());
        return summary;
    }

    /**
     * 取该智能体最近 N 条 user/assistant 消息（按 id 倒序取页后反转为时间正序）
     */
    private List<AgentChatHistoryEntity> getRecentMessages(String agentId) {
        LambdaQueryWrapper<AgentChatHistoryEntity> wrapper = new LambdaQueryWrapper<>();
        wrapper.select(AgentChatHistoryEntity::getContent, AgentChatHistoryEntity::getChatType)
                .eq(AgentChatHistoryEntity::getAgentId, agentId)
                .in(AgentChatHistoryEntity::getChatType,
                        AgentChatHistoryType.USER.getValue(), AgentChatHistoryType.AGENT.getValue())
                .isNotNull(AgentChatHistoryEntity::getContent)
                .orderByDesc(AgentChatHistoryEntity::getId);

        Page<AgentChatHistoryEntity> pageParam = new Page<>(1, RECENT_MESSAGE_LIMIT, false);
        IPage<AgentChatHistoryEntity> result = agentChatHistoryService.page(pageParam, wrapper);
        List<AgentChatHistoryEntity> records = result.getRecords();
        if (records == null || records.isEmpty()) {
            return Collections.emptyList();
        }
        List<AgentChatHistoryEntity> chronological = new ArrayList<>(records);
        Collections.reverse(chronological);
        return chronological;
    }

    /**
     * 拼接对话文本：用户消息提取 JSON 内 content 字段，智能体消息直接使用原文
     */
    private String buildConversationText(List<AgentChatHistoryEntity> messages) {
        StringBuilder conversation = new StringBuilder();
        for (AgentChatHistoryEntity message : messages) {
            String content = extractChatContent(message.getContent());
            if (StringUtils.isBlank(content)) {
                continue;
            }
            boolean isUser = message.getChatType() != null
                    && message.getChatType() == AgentChatHistoryType.USER.getValue();
            conversation.append(isUser ? "用户" : "助手").append("：").append(content).append("\n");
        }
        return conversation.toString();
    }

    /**
     * 从消息内容中提取文本：兼容 {"speaker": "...", "content": "..."} 的 JSON 存储格式
     */
    private String extractChatContent(String content) {
        if (StringUtils.isBlank(content)) {
            return content;
        }
        try {
            Map<String, Object> jsonMap = JsonUtils.parseMap(content);
            if (jsonMap != null && jsonMap.containsKey("content")) {
                Object contentObj = jsonMap.get("content");
                return contentObj != null ? contentObj.toString() : content;
            }
        } catch (Exception ignored) {
            // 非 JSON 格式，直接返回原文
        }
        return content;
    }

    /**
     * 解析总结用 LLM 模型：智能体 llmModelId 优先，无则回落默认启用的 LLM 配置
     */
    private String resolveLlmModelId(AgentInfoVO agent) {
        String llmModelId = agent.getLlmModelId();
        if (StringUtils.isNotBlank(llmModelId)) {
            return llmModelId;
        }
        try {
            List<ModelConfigEntity> llmConfigs = modelConfigService.getEnabledModelsByType("LLM");
            if (llmConfigs == null || llmConfigs.isEmpty()) {
                return null;
            }
            for (ModelConfigEntity config : llmConfigs) {
                if (config.getIsDefault() != null && config.getIsDefault() == 1) {
                    return config.getId();
                }
            }
            return llmConfigs.get(0).getId();
        } catch (Exception e) {
            log.error("获取默认LLM模型配置失败: {}", e.getMessage());
            return null;
        }
    }
}

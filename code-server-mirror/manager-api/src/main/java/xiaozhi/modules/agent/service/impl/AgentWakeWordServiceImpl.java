package xiaozhi.modules.agent.service.impl;

import java.util.Date;

import org.apache.commons.lang3.StringUtils;
import org.springframework.stereotype.Service;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;

import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import xiaozhi.common.exception.ErrorCode;
import xiaozhi.common.exception.RenException;
import xiaozhi.modules.agent.dao.AgentWakeWordDao;
import xiaozhi.modules.agent.entity.AgentWakeWordEntity;
import xiaozhi.modules.agent.service.AgentService;
import xiaozhi.modules.agent.service.AgentWakeWordService;

/**
 * 智能体唤醒词 Service 实现
 *
 * @author xiaozhi
 */
@Slf4j
@Service
@RequiredArgsConstructor
public class AgentWakeWordServiceImpl implements AgentWakeWordService {

    private final AgentWakeWordDao agentWakeWordDao;
    private final AgentService agentService;

    @Override
    public AgentWakeWordEntity getByAgentId(String agentId) {
        LambdaQueryWrapper<AgentWakeWordEntity> wrapper = new LambdaQueryWrapper<>();
        wrapper.eq(AgentWakeWordEntity::getAgentId, agentId);
        return agentWakeWordDao.selectOne(wrapper);
    }

    @Override
    public AgentWakeWordEntity saveOrUpdate(AgentWakeWordEntity entity, Long userId) {
        // 校验智能体存在
        if (entity.getAgentId() != null && agentService.getAgentById(entity.getAgentId()) == null) {
            throw new RenException(ErrorCode.WAKE_WORD_AGENT_NOT_FOUND);
        }
        // 校验唤醒词内容
        validateWakeWords(entity.getWakeWords());

        Date now = new Date();
        if (StringUtils.isNotBlank(entity.getId())) {
            // 更新
            entity.setUpdater(userId);
            entity.setUpdateDate(now);
            agentWakeWordDao.updateById(entity);
            log.info("更新唤醒词配置 id={}", entity.getId());
        } else {
            // 新建：检查是否已存在
            AgentWakeWordEntity existing = getByAgentId(entity.getAgentId());
            if (existing != null) {
                // 已有记录则走更新逻辑
                entity.setId(existing.getId());
                entity.setUpdater(userId);
                entity.setUpdateDate(now);
                agentWakeWordDao.updateById(entity);
                log.info("更新唤醒词配置 agentId={}", entity.getAgentId());
            } else {
                entity.setId(java.util.UUID.randomUUID().toString().replace("-", ""));
                entity.setCreator(userId);
                entity.setCreateDate(now);
                entity.setUpdater(userId);
                entity.setUpdateDate(now);
                agentWakeWordDao.insert(entity);
                log.info("创建唤醒词配置 agentId={}", entity.getAgentId());
            }
        }
        return getByAgentId(entity.getAgentId());
    }

    @Override
    public boolean deleteByAgentId(String agentId, Long userId) {
        AgentWakeWordEntity existing = getByAgentId(agentId);
        if (existing == null) {
            return true; // 幂等
        }
        agentWakeWordDao.deleteById(existing.getId());
        log.info("删除唤醒词配置 agentId={}, 操作者={}", agentId, userId);
        return true;
    }

    /**
     * 校验唤醒词 JSON 内容
     */
    private void validateWakeWords(String wakeWords) {
        if (StringUtils.isBlank(wakeWords)) {
            throw new RenException(ErrorCode.WAKE_WORD_EMPTY);
        }
        // 简单校验：JSON 中包含 words 数组，每项不超过30字符，总数不超过10个
        try {
            com.fasterxml.jackson.databind.ObjectMapper mapper = new com.fasterxml.jackson.databind.ObjectMapper();
            com.fasterxml.jackson.databind.JsonNode node = mapper.readTree(wakeWords);
            if (!node.isArray() && !node.has("words")) {
                throw new RenException(ErrorCode.WAKE_WORD_INVALID_CHAR);
            }
            com.fasterxml.jackson.databind.JsonNode words = node.has("words") ? node.get("words") : node;
            if (!words.isArray()) {
                throw new RenException(ErrorCode.WAKE_WORD_INVALID_CHAR);
            }
            if (words.size() > 10) {
                throw new RenException(ErrorCode.WAKE_WORD_TOO_MANY);
            }
            for (int i = 0; i < words.size(); i++) {
                String word = words.get(i).asText();
                if (word == null || word.trim().isEmpty()) {
                    throw new RenException(ErrorCode.WAKE_WORD_EMPTY);
                }
                if (word.length() > 30) {
                    throw new RenException(ErrorCode.WAKE_WORD_TOO_LONG);
                }
            }
        } catch (RenException e) {
            throw e;
        } catch (Exception e) {
            throw new RenException(ErrorCode.WAKE_WORD_INVALID_CHAR);
        }
    }
}

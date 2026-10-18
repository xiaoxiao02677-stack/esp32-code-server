package yuhe.modules.agent.service.impl;

import java.util.Date;
import java.util.HashMap;
import java.util.Map;

import org.apache.commons.lang3.StringUtils;
import org.springframework.stereotype.Service;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;

import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import yuhe.common.exception.ErrorCode;
import yuhe.common.exception.RenException;
import yuhe.common.utils.JsonUtils;
import yuhe.modules.agent.dao.AgentMcpConfigDao;
import yuhe.modules.agent.entity.AgentMcpConfigEntity;
import yuhe.modules.agent.service.AgentMcpConfigService;
import yuhe.modules.agent.service.AgentService;

/**
 * 智能体 MCP Server 配置 Service 实现
 *
 * @author yuhe
 */
@Slf4j
@Service
@RequiredArgsConstructor
public class AgentMcpConfigServiceImpl implements AgentMcpConfigService {

    private final AgentMcpConfigDao agentMcpConfigDao;
    private final AgentService agentService;

    @Override
    public AgentMcpConfigEntity getByAgentId(String agentId) {
        LambdaQueryWrapper<AgentMcpConfigEntity> wrapper = new LambdaQueryWrapper<>();
        wrapper.eq(AgentMcpConfigEntity::getAgentId, agentId);
        return agentMcpConfigDao.selectOne(wrapper);
    }

    @Override
    public AgentMcpConfigEntity saveOrUpdate(AgentMcpConfigEntity entity, Long userId) {
        // 校验智能体存在
        if (entity.getAgentId() != null && agentService.getAgentById(entity.getAgentId()) == null) {
            throw new RenException(ErrorCode.MCP_CONFIG_AGENT_NOT_FOUND);
        }
        // 校验 JSON 格式
        if (entity.getServerJson() != null && !isValidMcpJson(entity.getServerJson())) {
            throw new RenException(ErrorCode.MCP_CONFIG_JSON_INVALID);
        }
        Date now = new Date();
        if (StringUtils.isNotBlank(entity.getId())) {
            // 更新
            entity.setUpdater(userId);
            entity.setUpdateDate(now);
            agentMcpConfigDao.updateById(entity);
            log.info("更新 MCP 配置 id={}", entity.getId());
        } else {
            // 新建：检查是否已存在
            AgentMcpConfigEntity existing = getByAgentId(entity.getAgentId());
            if (existing != null) {
                throw new RenException(ErrorCode.MCP_CONFIG_ALREADY_EXISTS);
            }
            entity.setId(java.util.UUID.randomUUID().toString().replace("-", ""));
            entity.setCreator(userId);
            entity.setCreateDate(now);
            entity.setUpdater(userId);
            entity.setUpdateDate(now);
            agentMcpConfigDao.insert(entity);
            log.info("创建 MCP 配置 agentId={}", entity.getAgentId());
        }
        return getByAgentId(entity.getAgentId());
    }

    @Override
    public boolean deleteByAgentId(String agentId, Long userId) {
        AgentMcpConfigEntity existing = getByAgentId(agentId);
        if (existing == null) {
            return true; // 幂等
        }
        agentMcpConfigDao.deleteById(existing.getId());
        log.info("删除 MCP 配置 agentId={}, 操作者={}", agentId, userId);
        return true;
    }

    @Override
    public Map<String, Object> validateJson(String serverJson) {
        Map<String, Object> result = new HashMap<>();
        if (StringUtils.isBlank(serverJson)) {
            result.put("valid", false);
            result.put("message", "JSON 不能为空");
            return result;
        }
        try {
            Map<String, Object> parsed = JsonUtils.parseObject(serverJson, Map.class);
            if (parsed != null) {
                result.put("valid", true);
                result.put("message", "JSON 格式合法");
                result.put("keys", parsed.keySet());
            } else {
                result.put("valid", false);
                result.put("message", "JSON 解析结果为 null");
            }
        } catch (Exception e) {
            result.put("valid", false);
            result.put("message", "JSON 解析失败: " + e.getMessage());
        }
        return result;
    }

    private boolean isValidMcpJson(String json) {
        try {
            Map<String, Object> parsed = JsonUtils.parseObject(json, Map.class);
            return parsed != null;
        } catch (Exception e) {
            return false;
        }
    }
}

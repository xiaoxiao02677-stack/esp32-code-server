package yuhe.modules.agent.service.impl;

import java.util.ArrayList;
import java.util.Date;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;

import org.apache.commons.lang3.StringUtils;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import com.baomidou.mybatisplus.core.conditions.query.QueryWrapper;

import lombok.AllArgsConstructor;
import yuhe.modules.agent.dao.AgentShareDao;
import yuhe.modules.agent.entity.AgentShareEntity;
import yuhe.modules.agent.service.AgentShareService;

@Service
@AllArgsConstructor
public class AgentShareServiceImpl implements AgentShareService {

    private final AgentShareDao agentShareDao;

    @Override
    public List<AgentShareEntity> listByAgentId(String agentId) {
        if (StringUtils.isBlank(agentId)) {
            return new ArrayList<>();
        }
        return agentShareDao.selectByAgentId(agentId);
    }

    @Override
    @Transactional(rollbackFor = Exception.class)
    public void saveAgentShares(String agentId, List<Map<String, Object>> shares, Long operatorId) {
        agentShareDao.deleteByAgentId(agentId);
        if (shares == null || shares.isEmpty()) {
            return;
        }
        Date now = new Date();
        Set<String> seen = new HashSet<>();
        for (Map<String, Object> s : shares) {
            String targetType = s.get("targetType") == null ? null : s.get("targetType").toString();
            Object targetIdRaw = s.get("targetId");
            if (targetType == null || targetIdRaw == null) {
                continue;
            }
            if (!"user".equals(targetType) && !"role".equals(targetType)) {
                continue;
            }
            Long targetId = Long.valueOf(targetIdRaw.toString());
            // 去重（uk_agent_target 兜底前先过滤，避免批量插入撞唯一键）
            String key = targetType + ":" + targetId;
            if (!seen.add(key)) {
                continue;
            }
            AgentShareEntity entity = new AgentShareEntity();
            entity.setAgentId(agentId);
            entity.setTargetType(targetType);
            entity.setTargetId(targetId);
            entity.setCreator(operatorId);
            entity.setCreateDate(now);
            agentShareDao.insert(entity);
        }
    }

    @Override
    public boolean isSharedToUser(String agentId, Long userId) {
        if (StringUtils.isBlank(agentId) || userId == null) {
            return false;
        }
        return agentShareDao.countSharedToUser(agentId, userId) > 0;
    }

    @Override
    public List<String> getSharedAgentIds(Long userId) {
        if (userId == null) {
            return new ArrayList<>();
        }
        return agentShareDao.selectSharedAgentIds(userId);
    }

    @Override
    @Transactional(rollbackFor = Exception.class)
    public void deleteByAgentId(String agentId) {
        if (StringUtils.isNotBlank(agentId)) {
            agentShareDao.deleteByAgentId(agentId);
        }
    }
}

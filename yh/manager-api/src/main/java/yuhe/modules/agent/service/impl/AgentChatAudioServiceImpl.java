package yuhe.modules.agent.service.impl;

import org.springframework.stereotype.Service;

import com.baomidou.mybatisplus.spring.repository.CrudRepository;

import yuhe.modules.agent.dao.AiAgentChatAudioDao;
import yuhe.modules.agent.entity.AgentChatAudioEntity;
import yuhe.modules.agent.service.AgentChatAudioService;

/**
 * 智能体聊天音频数据表处理service {@link AgentChatAudioService} impl
 *
 * @author Goody
 * @version 1.0, 2025/5/8
 * @since 1.0.0
 */
@Service
public class AgentChatAudioServiceImpl extends CrudRepository<AiAgentChatAudioDao, AgentChatAudioEntity>
        implements AgentChatAudioService {
    @Override
    public String saveAudio(byte[] audioData) {
        AgentChatAudioEntity entity = new AgentChatAudioEntity();
        entity.setAudio(audioData);
        save(entity);
        return entity.getId();
    }

    @Override
    public byte[] getAudio(String audioId) {
        AgentChatAudioEntity entity = getById(audioId);
        return entity != null ? entity.getAudio() : null;
    }
}

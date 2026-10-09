package xiaozhi.modules.agent.dao;

import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import org.apache.ibatis.annotations.Mapper;
import xiaozhi.modules.agent.entity.AgentWakeWordEntity;

/**
 * 智能体唤醒词 Mapper
 *
 * @author xiaozhi
 */
@Mapper
public interface AgentWakeWordDao extends BaseMapper<AgentWakeWordEntity> {
}

package yuhe.modules.agent.dao;

import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import org.apache.ibatis.annotations.Mapper;
import yuhe.modules.agent.entity.AgentWakeWordEntity;

/**
 * 智能体唤醒词 Mapper
 *
 * @author yuhe
 */
@Mapper
public interface AgentWakeWordDao extends BaseMapper<AgentWakeWordEntity> {
}

package yuhe.modules.agent.dao;

import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import org.apache.ibatis.annotations.Mapper;
import yuhe.modules.agent.entity.AgentMcpConfigEntity;

/**
 * 智能体 MCP Server 配置 Mapper
 *
 * @author yuhe
 */
@Mapper
public interface AgentMcpConfigDao extends BaseMapper<AgentMcpConfigEntity> {
}

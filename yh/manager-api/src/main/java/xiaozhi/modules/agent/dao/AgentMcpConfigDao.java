package xiaozhi.modules.agent.dao;

import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import org.apache.ibatis.annotations.Mapper;
import xiaozhi.modules.agent.entity.AgentMcpConfigEntity;

/**
 * 智能体 MCP Server 配置 Mapper
 *
 * @author xiaozhi
 */
@Mapper
public interface AgentMcpConfigDao extends BaseMapper<AgentMcpConfigEntity> {
}

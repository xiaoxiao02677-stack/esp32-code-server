package yuhe.modules.agent.dao;

import java.util.List;

import org.apache.ibatis.annotations.Delete;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;
import org.apache.ibatis.annotations.Select;

import com.baomidou.mybatisplus.core.mapper.BaseMapper;

import yuhe.modules.agent.entity.AgentShareEntity;

/**
 * 智能体共享授权
 */
@Mapper
public interface AgentShareDao extends BaseMapper<AgentShareEntity> {

    /** 某智能体的全部共享配置（抽屉回显） */
    @Select("SELECT * FROM ai_agent_share WHERE agent_id = #{agentId}")
    List<AgentShareEntity> selectByAgentId(@Param("agentId") String agentId);

    /** 用户可见的智能体ID集合：本人直享 + 用户所属角色组共享（DISTINCT 合并） */
    @Select("SELECT DISTINCT agent_id FROM ai_agent_share WHERE (target_type = 'user' AND target_id = #{userId})"
            + " OR (target_type = 'role' AND target_id IN (SELECT role_id FROM sys_user_role WHERE user_id = #{userId}))")
    List<String> selectSharedAgentIds(@Param("userId") Long userId);

    /** 用户是否对某智能体有共享授权（权限闸门用，命中即 true） */
    @Select("SELECT COUNT(1) FROM ai_agent_share WHERE agent_id = #{agentId}"
            + " AND ((target_type = 'user' AND target_id = #{userId})"
            + " OR (target_type = 'role' AND target_id IN (SELECT role_id FROM sys_user_role WHERE user_id = #{userId})))")
    int countSharedToUser(@Param("agentId") String agentId, @Param("userId") Long userId);

    /** 删除智能体的全部共享配置（级联清理） */
    @Delete("DELETE FROM ai_agent_share WHERE agent_id = #{agentId}")
    int deleteByAgentId(@Param("agentId") String agentId);
}

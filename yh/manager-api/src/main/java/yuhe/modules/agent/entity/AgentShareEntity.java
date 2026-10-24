package yuhe.modules.agent.entity;

import java.io.Serializable;
import java.util.Date;

import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;

import lombok.Data;

/**
 * 智能体共享授权（超管配置：哪个用户/角色组可以看到该智能体及其绑定设备）
 */
@Data
@TableName("ai_agent_share")
public class AgentShareEntity implements Serializable {
    @TableId(type = IdType.AUTO)
    private Long id;
    /** 智能体ID */
    private String agentId;
    /** 共享目标类型：user/role */
    private String targetType;
    /** 目标ID：sys_user.id 或 sys_role.id */
    private Long targetId;
    private Long creator;
    private Date createDate;
}

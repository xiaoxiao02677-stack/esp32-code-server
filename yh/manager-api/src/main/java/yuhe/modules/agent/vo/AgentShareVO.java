package yuhe.modules.agent.vo;

import lombok.Data;

/**
 * 智能体共享配置项（回显）
 */
@Data
public class AgentShareVO {
    /** 共享目标类型：user/role */
    private String targetType;
    /** 目标ID：sys_user.id 或 sys_role.id */
    private Long targetId;
}

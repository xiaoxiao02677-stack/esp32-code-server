package yuhe.modules.agent.dto;

import java.util.List;
import java.util.Map;

import lombok.Data;

/**
 * 保存智能体共享配置（全量覆盖）
 */
@Data
public class AgentSharesSaveDTO {
    /**
     * 共享配置列表，每项 {targetType: "user"|"role", targetId: Long}。
     * 空数组/省略 = 清空全部共享。
     */
    private List<Map<String, Object>> shares;
}

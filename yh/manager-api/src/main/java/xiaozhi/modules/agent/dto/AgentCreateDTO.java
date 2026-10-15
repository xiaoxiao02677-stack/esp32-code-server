package xiaozhi.modules.agent.dto;

import java.io.Serializable;

import io.swagger.v3.oas.annotations.media.Schema;
import jakarta.validation.constraints.NotBlank;
import lombok.Data;

/**
 * 智能体创建DTO
 * 专用于新增智能体，不包含id、agentCode和sort字段，这些字段由系统自动生成/设置默认值
 */
@Data
@Schema(description = "智能体创建对象")
public class AgentCreateDTO implements Serializable {
    private static final long serialVersionUID = 1L;

    @Schema(description = "智能体名称", example = "客服助手")
    @NotBlank(message = "智能体名称不能为空")
    private String agentName;

    @Schema(description = "创建来源模板ID（可选，指定后以该模板为基准而非默认模板）")
    private String templateId;

    @Schema(description = "智能体自定义唤醒词，分号分隔；为空则使用全局 wakeup_words（默认「你好」）", example = "你好;早上好")
    private String wakeWords;
}
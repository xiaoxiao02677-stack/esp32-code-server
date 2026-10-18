package yuhe.modules.memory.vo;

import com.fasterxml.jackson.annotation.JsonProperty;

import io.swagger.v3.oas.annotations.media.Schema;
import lombok.Data;

/**
 * 记忆智能体视图对象（有记忆数据/绑定记忆引擎的 Agent）
 */
@Data
@Schema(description = "记忆智能体")
public class MemoryAgentVO {

    @Schema(description = "智能体ID")
    @JsonProperty("agent_id")
    private String agentId;

    @Schema(description = "智能体名称")
    @JsonProperty("name")
    private String name;

    @Schema(description = "记忆引擎类型：mem_holographic/mem0ai/mem_local_short/nomem等")
    @JsonProperty("engine")
    private String engine;

    @Schema(description = "记忆引擎模型ID（供引擎参数面板加载模型配置，C线）")
    @JsonProperty("mem_model_id")
    private String memModelId;

    @Schema(description = "引擎是否可用（mem0ai 未配置 API Key 时为 false）")
    @JsonProperty("available")
    private Boolean available;

    @Schema(description = "记忆条目数（mem_holographic；其他引擎为0）")
    @JsonProperty("fact_count")
    private Integer factCount;

    @Schema(description = "待审核条目数（mem_holographic；其他引擎为0）")
    @JsonProperty("pending_count")
    private Integer pendingCount;
}

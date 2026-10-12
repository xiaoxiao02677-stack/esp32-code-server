package xiaozhi.modules.memory.vo;

import com.fasterxml.jackson.annotation.JsonProperty;

import io.swagger.v3.oas.annotations.media.Schema;
import lombok.Data;

/**
 * 记忆反馈结果视图对象（信任分变更）
 */
@Data
@Schema(description = "记忆反馈结果")
public class FeedbackVO {

    @Schema(description = "记忆条目ID")
    @JsonProperty("fact_id")
    private Long factId;

    @Schema(description = "反馈前信任分")
    @JsonProperty("old_trust")
    private Double oldTrust;

    @Schema(description = "反馈后信任分")
    @JsonProperty("new_trust")
    private Double newTrust;

    @Schema(description = "被标记有用次数")
    @JsonProperty("helpful_count")
    private Integer helpfulCount;
}

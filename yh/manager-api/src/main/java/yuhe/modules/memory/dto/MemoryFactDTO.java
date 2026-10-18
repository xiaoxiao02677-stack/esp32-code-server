package yuhe.modules.memory.dto;

import java.util.List;

import com.fasterxml.jackson.annotation.JsonProperty;

import io.swagger.v3.oas.annotations.media.Schema;
import lombok.Data;

/**
 * 记忆条目数据传输对象（字段对齐 PRD 4.1；mem0 引擎下无信任分/状态概念，相关字段为空）
 */
@Data
@Schema(description = "记忆条目")
public class MemoryFactDTO {

    @Schema(description = "记忆条目ID（Agent库内主键）")
    @JsonProperty("fact_id")
    private Long factId;

    @Schema(description = "记忆内容")
    @JsonProperty("content")
    private String content;

    @Schema(description = "类型：preference/profile/habit/event/general")
    @JsonProperty("category")
    private String category;

    @Schema(description = "标签，逗号分隔")
    @JsonProperty("tags")
    private String tags;

    @Schema(description = "信任分 0~1")
    @JsonProperty("trust_score")
    private Double trustScore;

    @Schema(description = "状态：active生效 / rejected已驳回（仅holographic）")
    @JsonProperty("status")
    private String status;

    @Schema(description = "所属智能体ID")
    @JsonProperty("agent_id")
    private String agentId;

    @Schema(description = "产生该记忆的设备ID")
    @JsonProperty("device_id")
    private String deviceId;

    @Schema(description = "来源会话ID")
    @JsonProperty("session_id")
    private String sessionId;

    @Schema(description = "检索次数")
    @JsonProperty("retrieval_count")
    private Integer retrievalCount;

    @Schema(description = "被标记有用次数")
    @JsonProperty("helpful_count")
    private Integer helpfulCount;

    @Schema(description = "创建时间，格式 yyyy-MM-dd HH:mm:ss")
    @JsonProperty("created_at")
    private String createdAt;

    @Schema(description = "更新时间，格式 yyyy-MM-dd HH:mm:ss")
    @JsonProperty("updated_time")
    private String updatedTime;

    @Schema(description = "实体列表（详情接口返回）")
    @JsonProperty("entities")
    private List<String> entities;

    @Schema(description = "检索命中的关键词（用于前端高亮）")
    @JsonProperty("matched_terms")
    private List<String> matchedTerms;
}

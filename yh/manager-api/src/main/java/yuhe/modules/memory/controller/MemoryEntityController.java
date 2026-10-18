package yuhe.modules.memory.controller;

import java.util.Map;

import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.Parameter;
import io.swagger.v3.oas.annotations.tags.Tag;
import lombok.AllArgsConstructor;
import yuhe.common.utils.Result;
import yuhe.modules.memory.client.MemoryInternalClient;

/**
 * 实体图谱与时间线管理（代理转发到 yuhe-server :8003）
 */
@AllArgsConstructor
@RestController
@RequestMapping("/memory")
@Tag(name = "实体图谱与时间线管理")
public class MemoryEntityController {

    private final MemoryInternalClient memoryInternalClient;

    @GetMapping("/entities/{agent_id}")
    @Operation(summary = "获取实体列表")
    public Result<Map<String, Object>> listEntities(
            @Parameter(name = "agent_id", description = "智能体ID", required = true)
            @PathVariable("agent_id") String agentId) {
        Map<String, Object> result = memoryInternalClient.get("/" + agentId + "/entities", null);
        return new Result<Map<String, Object>>().ok(result);
    }

    @GetMapping("/entities/{agent_id}/graph")
    @Operation(summary = "获取实体图谱")
    public Result<Map<String, Object>> getEntityGraph(
            @Parameter(name = "agent_id", description = "智能体ID", required = true)
            @PathVariable("agent_id") String agentId) {
        Map<String, Object> result = memoryInternalClient.get("/" + agentId + "/entities/graph", null);
        return new Result<Map<String, Object>>().ok(result);
    }

    @PostMapping("/entities/{agent_id}/extract")
    @Operation(summary = "从对话中提取实体")
    public Result<Map<String, Object>> extractEntities(
            @Parameter(name = "agent_id", description = "智能体ID", required = true)
            @PathVariable("agent_id") String agentId,
            @RequestParam("fact_id") Long factId) {
        Map<String, Object> body = Map.of("fact_id", factId);
        Map<String, Object> result = memoryInternalClient.post("/" + agentId + "/entities/extract", body);
        return new Result<Map<String, Object>>().ok(result);
    }

    @GetMapping("/timeline/{agent_id}")
    @Operation(summary = "获取时间线列表")
    public Result<Map<String, Object>> listTimeline(
            @Parameter(name = "agent_id", description = "智能体ID", required = true)
            @PathVariable("agent_id") String agentId,
            @Parameter(name = "limit", description = "返回条数限制")
            @RequestParam(value = "limit", required = false, defaultValue = "50") Integer limit) {
        Map<String, Object> params = Map.of("limit", limit);
        Map<String, Object> result = memoryInternalClient.get("/" + agentId + "/timeline", params);
        return new Result<Map<String, Object>>().ok(result);
    }

    @GetMapping("/timeline/{agent_id}/chart")
    @Operation(summary = "获取时间线图表数据")
    public Result<Map<String, Object>> getTimelineChart(
            @Parameter(name = "agent_id", description = "智能体ID", required = true)
            @PathVariable("agent_id") String agentId,
            @Parameter(name = "days", description = "天数")
            @RequestParam(value = "days", required = false, defaultValue = "30") Integer days) {
        Map<String, Object> params = Map.of("days", days);
        Map<String, Object> result = memoryInternalClient.get("/" + agentId + "/timeline/chart", params);
        return new Result<Map<String, Object>>().ok(result);
    }

    @PostMapping("/timeline/{agent_id}")
    @Operation(summary = "创建时间线条目")
    public Result<Map<String, Object>> createTimelineEntry(
            @Parameter(name = "agent_id", description = "智能体ID", required = true)
            @PathVariable("agent_id") String agentId,
            Map<String, Object> body) {
        Map<String, Object> result = memoryInternalClient.post("/" + agentId + "/timeline", body);
        return new Result<Map<String, Object>>().ok(result);
    }

    @GetMapping("/timeline/{agent_id}/{entry_id}")
    @Operation(summary = "获取时间线条目详情")
    public Result<Map<String, Object>> getTimelineEntry(
            @Parameter(name = "agent_id", description = "智能体ID", required = true)
            @PathVariable("agent_id") String agentId,
            @Parameter(name = "entry_id", description = "条目ID", required = true)
            @PathVariable("entry_id") Long entryId) {
        Map<String, Object> result = memoryInternalClient.get("/" + agentId + "/timeline/" + entryId, null);
        return new Result<Map<String, Object>>().ok(result);
    }

    @DeleteMapping("/timeline/{agent_id}/{entry_id}")
    @Operation(summary = "删除时间线条目")
    public Result<Void> deleteTimelineEntry(
            @Parameter(name = "agent_id", description = "智能体ID", required = true)
            @PathVariable("agent_id") String agentId,
            @Parameter(name = "entry_id", description = "条目ID", required = true)
            @PathVariable("entry_id") Long entryId) {
        memoryInternalClient.delete("/" + agentId + "/timeline/" + entryId);
        return new Result<>();
    }
}

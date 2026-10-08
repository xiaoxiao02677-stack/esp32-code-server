package xiaozhi.modules.memory.controller;

import java.util.List;
import java.util.Map;

import org.apache.shiro.authz.annotation.RequiresPermissions;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.Parameter;
import io.swagger.v3.oas.annotations.tags.Tag;
import lombok.AllArgsConstructor;
import xiaozhi.common.exception.ErrorCode;
import xiaozhi.common.exception.RenException;
import xiaozhi.common.page.PageData;
import xiaozhi.common.utils.Result;
import xiaozhi.modules.memory.dto.MemoryFactDTO;
import xiaozhi.modules.memory.service.MemoryFactService;
import xiaozhi.modules.memory.vo.FeedbackVO;
import xiaozhi.modules.memory.vo.MemoryAgentVO;
import xiaozhi.modules.security.user.SecurityUser;

/**
 * 记忆管理（/memory/**，由 Shiro 默认链 /**→oauth2 保护）
 */
@AllArgsConstructor
@RestController
@RequestMapping("/memory")
@Tag(name = "记忆管理")
public class MemoryFactController {

    private final MemoryFactService memoryFactService;

    @GetMapping("/agents")
    @Operation(summary = "有记忆数据的智能体列表")
    @RequiresPermissions("sys:role:normal")
    public Result<List<MemoryAgentVO>> listAgents() {
        List<MemoryAgentVO> agents = memoryFactService.listAgents(SecurityUser.getUserId());
        return new Result<List<MemoryAgentVO>>().ok(agents);
    }

    @GetMapping("/facts")
    @Operation(summary = "分页查询记忆条目")
    @RequiresPermissions("sys:role:normal")
    public Result<PageData<MemoryFactDTO>> getFactPage(
            @Parameter(name = "agent_id", description = "智能体ID", required = true) @RequestParam("agent_id") String agentId,
            @Parameter(name = "keyword", description = "关键词（FTS全文检索）") @RequestParam(value = "keyword", required = false) String keyword,
            @Parameter(name = "category", description = "类型：preference/profile/habit/event/general") @RequestParam(value = "category", required = false) String category,
            @Parameter(name = "status", description = "状态：active/rejected") @RequestParam(value = "status", required = false) String status,
            @Parameter(name = "trust_min", description = "信任分下限") @RequestParam(value = "trust_min", required = false) Double trustMin,
            @Parameter(name = "trust_max", description = "信任分上限") @RequestParam(value = "trust_max", required = false) Double trustMax,
            @Parameter(name = "start", description = "创建时间起") @RequestParam(value = "start", required = false) String start,
            @Parameter(name = "end", description = "创建时间止") @RequestParam(value = "end", required = false) String end,
            @Parameter(name = "page", description = "页码，从1开始") @RequestParam(value = "page", required = false, defaultValue = "1") Integer page,
            @Parameter(name = "size", description = "每页条数，默认20，上限100") @RequestParam(value = "size", required = false, defaultValue = "20") Integer size,
            @Parameter(name = "sort_by", description = "排序字段：created创建时间/trust信任分") @RequestParam(value = "sort_by", required = false, defaultValue = "created") String sortBy,
            @Parameter(name = "order", description = "排序方式：asc/desc") @RequestParam(value = "order", required = false, defaultValue = "desc") String order) {
        PageData<MemoryFactDTO> pageData = memoryFactService.getFactPage(agentId, keyword, category, status,
                trustMin, trustMax, start, end, page, size, sortBy, order, SecurityUser.getUserId());
        return new Result<PageData<MemoryFactDTO>>().ok(pageData);
    }

    @GetMapping("/facts/{fact_id}")
    @Operation(summary = "记忆条目详情（含实体列表）")
    @RequiresPermissions("sys:role:normal")
    public Result<MemoryFactDTO> getFact(
            @Parameter(name = "fact_id", description = "记忆条目ID", required = true) @PathVariable("fact_id") Long factId,
            @Parameter(name = "agent_id", description = "智能体ID", required = true) @RequestParam("agent_id") String agentId) {
        MemoryFactDTO fact = memoryFactService.getFact(agentId, factId, SecurityUser.getUserId());
        return new Result<MemoryFactDTO>().ok(fact);
    }

    @PostMapping("/facts")
    @Operation(summary = "新增记忆条目")
    @RequiresPermissions("sys:role:normal")
    public Result<MemoryFactDTO> saveFact(@RequestBody MemoryFactDTO dto) {
        MemoryFactDTO fact = memoryFactService.saveFact(dto, SecurityUser.getUserId());
        return new Result<MemoryFactDTO>().ok(fact);
    }

    @PutMapping("/facts/{fact_id}")
    @Operation(summary = "编辑记忆条目（内容变更触发实体重抽取）")
    @RequiresPermissions("sys:role:normal")
    public Result<MemoryFactDTO> updateFact(
            @Parameter(name = "fact_id", description = "记忆条目ID", required = true) @PathVariable("fact_id") Long factId,
            @RequestBody MemoryFactDTO dto) {
        MemoryFactDTO fact = memoryFactService.updateFact(factId, dto, SecurityUser.getUserId());
        return new Result<MemoryFactDTO>().ok(fact);
    }

    @DeleteMapping("/facts/{fact_id}")
    @Operation(summary = "删除记忆条目（物理删除，不可恢复）")
    @RequiresPermissions("sys:role:normal")
    public Result<Void> deleteFact(
            @Parameter(name = "fact_id", description = "记忆条目ID", required = true) @PathVariable("fact_id") Long factId,
            @Parameter(name = "agent_id", description = "智能体ID", required = true) @RequestParam("agent_id") String agentId) {
        memoryFactService.deleteFact(agentId, factId, SecurityUser.getUserId());
        return new Result<>();
    }

    @PostMapping("/facts/{fact_id}/feedback")
    @Operation(summary = "信任分反馈（有用+0.05/无用-0.10）")
    @RequiresPermissions("sys:role:normal")
    public Result<FeedbackVO> feedback(
            @Parameter(name = "fact_id", description = "记忆条目ID", required = true) @PathVariable("fact_id") Long factId,
            @RequestBody Map<String, Object> body) {
        if (body == null || body.get("agent_id") == null || body.get("helpful") == null) {
            throw new RenException(ErrorCode.PARAMS_GET_ERROR);
        }
        Boolean helpful = Boolean.parseBoolean(body.get("helpful").toString());
        FeedbackVO vo = memoryFactService.feedback(body.get("agent_id").toString(), factId, helpful,
                SecurityUser.getUserId());
        return new Result<FeedbackVO>().ok(vo);
    }

    @PostMapping("/facts/{fact_id}/review")
    @Operation(summary = "记忆审核（approve通过/reject驳回）")
    @RequiresPermissions("sys:role:normal")
    public Result<MemoryFactDTO> review(
            @Parameter(name = "fact_id", description = "记忆条目ID", required = true) @PathVariable("fact_id") Long factId,
            @RequestBody Map<String, Object> body) {
        if (body == null || body.get("agent_id") == null || body.get("action") == null) {
            throw new RenException(ErrorCode.PARAMS_GET_ERROR);
        }
        MemoryFactDTO fact = memoryFactService.review(body.get("agent_id").toString(), factId,
                body.get("action").toString(), SecurityUser.getUserId());
        return new Result<MemoryFactDTO>().ok(fact);
    }
}

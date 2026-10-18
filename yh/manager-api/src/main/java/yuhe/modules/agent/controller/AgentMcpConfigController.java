package yuhe.modules.agent.controller;

import java.util.HashMap;
import java.util.Map;

import org.apache.shiro.authz.annotation.RequiresPermissions;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import lombok.RequiredArgsConstructor;
import yuhe.common.exception.ErrorCode;
import yuhe.common.user.UserDetail;
import yuhe.common.utils.Result;
import yuhe.modules.agent.entity.AgentMcpConfigEntity;
import yuhe.modules.agent.service.AgentMcpConfigService;
import yuhe.modules.agent.service.AgentService;
import yuhe.modules.security.user.SecurityUser;

/**
 * 智能体 MCP Server 配置管理
 *
 * @author yuhe
 */
@Tag(name = "智能体MCP Server配置管理")
@RequiredArgsConstructor
@RestController
@RequestMapping("/agent/mcp/config")
public class AgentMcpConfigController {

    private final AgentMcpConfigService agentMcpConfigService;
    private final AgentService agentService;

    /**
     * 获取智能体的 MCP 配置
     */
    @Operation(summary = "获取智能体的MCP配置")
    @GetMapping("/{agentId}")
    @RequiresPermissions("sys:role:normal")
    public Result<AgentMcpConfigEntity> get(@PathVariable String agentId) {
        UserDetail user = SecurityUser.getUser();
        if (!agentService.checkAgentPermission(agentId, user.getId())) {
            return new Result<AgentMcpConfigEntity>().error(ErrorCode.MCP_ACCESS_POINT_ADDRESS_NO_PERMISSION);
        }
        AgentMcpConfigEntity config = agentMcpConfigService.getByAgentId(agentId);
        return new Result<AgentMcpConfigEntity>().ok(config);
    }

    /**
     * 保存/更新智能体的 MCP 配置（upsert）
     */
    @Operation(summary = "保存MCP配置")
    @PostMapping
    @RequiresPermissions("sys:role:normal")
    public Result<AgentMcpConfigEntity> save(@RequestBody AgentMcpConfigEntity entity) {
        UserDetail user = SecurityUser.getUser();
        if (entity.getAgentId() != null && !agentService.checkAgentPermission(entity.getAgentId(), user.getId())) {
            return new Result<AgentMcpConfigEntity>().error(ErrorCode.MCP_ACCESS_POINT_ADDRESS_NO_PERMISSION);
        }
        try {
            AgentMcpConfigEntity saved = agentMcpConfigService.saveOrUpdate(entity, user.getId());
            return new Result<AgentMcpConfigEntity>().ok(saved);
        } catch (Exception e) {
            return new Result<AgentMcpConfigEntity>().error(ErrorCode.MCP_CONFIG_SAVE_FAILED, e.getMessage());
        }
    }

    /**
     * 删除智能体的 MCP 配置
     */
    @Operation(summary = "删除MCP配置")
    @DeleteMapping("/{agentId}")
    @RequiresPermissions("sys:role:normal")
    public Result<Map<String, Object>> delete(@PathVariable String agentId) {
        UserDetail user = SecurityUser.getUser();
        if (!agentService.checkAgentPermission(agentId, user.getId())) {
            return new Result<Map<String, Object>>().error(ErrorCode.MCP_ACCESS_POINT_ADDRESS_NO_PERMISSION);
        }
        boolean ok = agentMcpConfigService.deleteByAgentId(agentId, user.getId());
        Map<String, Object> result = new HashMap<>();
        result.put("deleted", ok);
        return new Result<Map<String, Object>>().ok(result);
    }

    /**
     * 校验 MCP JSON 格式
     */
    @Operation(summary = "校验MCP JSON格式")
    @PostMapping("/validate")
    @RequiresPermissions("sys:role:normal")
    public Result<Map<String, Object>> validate(@RequestBody Map<String, String> body) {
        String serverJson = body.get("serverJson");
        Map<String, Object> result = agentMcpConfigService.validateJson(serverJson);
        return new Result<Map<String, Object>>().ok(result);
    }
}

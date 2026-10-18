package yuhe.modules.agent.controller;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

import org.apache.shiro.authz.annotation.RequiresPermissions;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;


import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import lombok.RequiredArgsConstructor;
import yuhe.common.exception.ErrorCode;
import yuhe.common.user.UserDetail;
import yuhe.common.utils.Result;
import yuhe.modules.agent.service.AgentMcpAccessPointService;
import yuhe.modules.agent.service.AgentService;
import yuhe.modules.security.user.SecurityUser;

@Tag(name = "智能体Mcp接入点管理")
@RequiredArgsConstructor
@RestController
@RequestMapping("/agent/mcp")
public class AgentMcpAccessPointController {
    private final AgentMcpAccessPointService agentMcpAccessPointService;
    private final AgentService agentService;

    private static final HttpClient HTTP_CLIENT = HttpClient.newBuilder()
            .connectTimeout(Duration.ofSeconds(8))
            .build();

    /**
     * 获取智能体的Mcp接入点地址
     * 
     * @param agentId 智能体id
     * @return 返回错误提醒或者Mcp接入点地址
     */
    @Operation(summary = "获取智能体的Mcp接入点地址")
    @GetMapping("/address/{agentId}")
    @RequiresPermissions("sys:role:normal")
    public Result<String> getAgentMcpAccessAddress(@PathVariable("agentId") String agentId) {
        // 获取当前用户
        UserDetail user = SecurityUser.getUser();

        // 检查权限
        if (!agentService.checkAgentPermission(agentId, user.getId())) {
            return new Result<String>().error(ErrorCode.MCP_ACCESS_POINT_ADDRESS_NO_PERMISSION);
        }
        String agentMcpAccessAddress = agentMcpAccessPointService.getAgentMcpAccessAddress(agentId);
        if (agentMcpAccessAddress == null) {
            return new Result<String>().error(ErrorCode.MCP_ACCESS_POINT_ADDRESS_NOT_CONFIGURED);
        }
        return new Result<String>().ok(agentMcpAccessAddress);
    }

    @Operation(summary = "获取智能体的Mcp工具列表")
    @GetMapping("/tools/{agentId}")
    @RequiresPermissions("sys:role:normal")
    public Result<List<String>> getAgentMcpToolsList(@PathVariable("agentId") String agentId) {
        // 获取当前用户
        UserDetail user = SecurityUser.getUser();

        // 检查权限
        if (!agentService.checkAgentPermission(agentId, user.getId())) {
            return new Result<List<String>>().error(ErrorCode.MCP_ACCESS_POINT_TOOLS_LIST_NO_PERMISSION);
        }
        List<String> agentMcpToolsList = agentMcpAccessPointService.getAgentMcpToolsList(agentId);
        return new Result<List<String>>().ok(agentMcpToolsList);
    }

    /**
     * MCP 接入点一键测试：验证接入点连通性 + 智能体工具列表可拉取。
     * 通过标准 = HTTP 探测接入点可达 且 工具列表非空（链路 + 响应双验证）。
     */
    @Operation(summary = "MCP接入点一键测试（连通性 + 工具列表）")
    @GetMapping("/test/{agentId}")
    @RequiresPermissions("sys:role:normal")
    public Result<Map<String, Object>> testAgentMcpAccessPoint(@PathVariable("agentId") String agentId) {
        UserDetail user = SecurityUser.getUser();
        if (!agentService.checkAgentPermission(agentId, user.getId())) {
            return new Result<Map<String, Object>>().error(ErrorCode.MCP_ACCESS_POINT_ADDRESS_NO_PERMISSION);
        }

        Map<String, Object> report = new HashMap<>();
        long started = System.currentTimeMillis();

        // ① 接入点地址存在性
        String address = agentMcpAccessPointService.getAgentMcpAccessAddress(agentId);
        if (address == null) {
            report.put("ok", false);
            report.put("message", "该智能体未配置 MCP 接入点");
            return new Result<Map<String, Object>>().ok(report);
        }
        report.put("address", address);

        // ② HTTP 连通性探测（GET 接入点根路径，2xx/4xx/405 都算可达——拒绝连接/超时才算不通）
        boolean reachable = false;
        String reachMessage = "";
        try {
            HttpRequest request = HttpRequest.newBuilder()
                    .uri(URI.create(address))
                    .timeout(Duration.ofSeconds(8))
                    .GET()
                    .build();
            HttpResponse<String> response = HTTP_CLIENT.send(request, HttpResponse.BodyHandlers.ofString());
            reachable = true;
            reachMessage = "HTTP " + response.statusCode();
        } catch (Exception e) {
            reachMessage = "连接失败：" + e.getMessage();
        }
        report.put("reachable", reachable);
        report.put("reachableMessage", reachMessage);

        // ③ 工具列表拉取（真实业务链路验证）
        int toolCount = 0;
        String toolsMessage = "";
        try {
            List<String> tools = agentMcpAccessPointService.getAgentMcpToolsList(agentId);
            toolCount = tools == null ? 0 : tools.size();
            toolsMessage = toolCount + " 个工具可用";
        } catch (Exception e) {
            toolsMessage = "工具列表拉取失败：" + e.getMessage();
        }
        report.put("toolCount", toolCount);
        report.put("toolsMessage", toolsMessage);

        boolean ok = reachable && toolCount > 0;
        report.put("ok", ok);
        report.put("message", ok
                ? String.format("接入点可达（%s），%s", reachMessage, toolsMessage)
                : (reachable ? "接入点可达但无工具（" + toolsMessage + "）" : reachMessage));
        report.put("elapsed_ms", System.currentTimeMillis() - started);
        return new Result<Map<String, Object>>().ok(report);
    }
}

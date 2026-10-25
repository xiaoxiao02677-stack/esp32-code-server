package yuhe.modules.sys.controller;

import java.util.Map;

import org.apache.shiro.authz.annotation.Logical;
import org.apache.shiro.authz.annotation.RequiresPermissions;
import org.springframework.http.HttpEntity;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpMethod;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.client.RestTemplate;

import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import yuhe.common.constant.Constant;
import yuhe.modules.sys.service.SysParamsService;

/**
 * Python 服务 API 代理（/api/push/**、/api/wake-word/**）。
 *
 * 背景：这些端点在 yuhe-server(Python:8003) 上，鉴权用 server secret；
 * 浏览器只持有用户 token，无法直连。本代理挂在 manager-api 下（Shiro oauth2 用户鉴权），
 * 转发时注入 server secret，让管理端页面可以统一用用户 token 访问。
 *
 * 权限（模块码由 Oauth2Realm 按展示配置发放）：
 * - wake-word/devices：平台级在线设备 MAC 清单，管理端设备相关页共用
 *   （概览/设备页数据源 /admin/device/all 需 admin:users；唤醒词页 admin:wake-word；推送调度页 admin:push-scheduler）
 * - wake-word/push：唤醒词下发（前端已改走 /agent/wake-word/{agentId}，此代理无页面调用方，保留给管理动作）
 * - push/**：随机推送调度（PushScheduler 页，admin:push-scheduler）
 */
@RestController
@RequestMapping("/api")
@Tag(name = "Python API 代理")
public class PythonApiProxyController {

    private static final String DEFAULT_HTTP_PORT = "8003";
    private static final String PARAM_HTTP_PORT = "server.http_port";

    private final SysParamsService sysParamsService;
    private final RestTemplate restTemplate;

    public PythonApiProxyController(SysParamsService sysParamsService, RestTemplate restTemplate) {
        this.sysParamsService = sysParamsService;
        this.restTemplate = restTemplate;
    }

    @GetMapping("/wake-word/devices")
    @Operation(summary = "在线设备列表（代理 Python）")
    @RequiresPermissions(value = {"sys:role:superAdmin", "admin:users", "admin:wake-word", "admin:push-scheduler"},
            logical = Logical.OR)
    public ResponseEntity<String> wakeWordDevices() {
        return proxyGet("/api/wake-word/devices");
    }

    @PostMapping("/wake-word/push")
    @Operation(summary = "推送唤醒词（代理 Python）")
    @RequiresPermissions(value = {"sys:role:superAdmin", "admin:wake-word"}, logical = Logical.OR)
    public ResponseEntity<String> wakeWordPush(@RequestBody(required = false) Map<String, Object> body) {
        return proxyPost("/api/wake-word/push", body);
    }

    @GetMapping("/push/tasks")
    @Operation(summary = "推送任务列表（代理 Python）")
    @RequiresPermissions(value = {"sys:role:superAdmin", "admin:push-scheduler"}, logical = Logical.OR)
    public ResponseEntity<String> pushTasks() {
        return proxyGet("/api/push/tasks");
    }

    @GetMapping("/push/tasks/{pushId}")
    @Operation(summary = "推送任务详情（代理 Python）")
    @RequiresPermissions(value = {"sys:role:superAdmin", "admin:push-scheduler"}, logical = Logical.OR)
    public ResponseEntity<String> pushTaskDetail(@PathVariable String pushId) {
        return proxyGet("/api/push/tasks/" + pushId);
    }

    @PostMapping("/push/schedule")
    @Operation(summary = "创建推送任务（代理 Python）")
    @RequiresPermissions(value = {"sys:role:superAdmin", "admin:push-scheduler"}, logical = Logical.OR)
    public ResponseEntity<String> pushSchedule(@RequestBody(required = false) Map<String, Object> body) {
        return proxyPost("/api/push/schedule", body);
    }

    // ---------- 内部 ----------
    private String pythonBase() {
        String port = sysParamsService.getValue(PARAM_HTTP_PORT, true);
        if (port == null || port.isBlank()) {
            port = DEFAULT_HTTP_PORT;
        }
        return "http://127.0.0.1:" + port;
    }

    private String serverSecret() {
        return sysParamsService.getValue(Constant.SERVER_SECRET, true);
    }

    private ResponseEntity<String> proxyGet(String path) {
        HttpHeaders headers = new HttpHeaders();
        String secret = serverSecret();
        if (secret != null && !secret.isBlank()) {
            headers.set(HttpHeaders.AUTHORIZATION, "Bearer " + secret);
        }
        try {
            return restTemplate.exchange(pythonBase() + path, HttpMethod.GET, new HttpEntity<>(headers), String.class);
        } catch (org.springframework.web.client.HttpStatusCodeException e) {
            return ResponseEntity.status(e.getStatusCode()).body(e.getResponseBodyAsString());
        } catch (Exception e) {
            return ResponseEntity.status(502).body("{\"code\":502,\"msg\":\"python服务不可达\",\"data\":null}");
        }
    }

    private ResponseEntity<String> proxyPost(String path, Map<String, Object> body) {
        HttpHeaders headers = new HttpHeaders();
        headers.setContentType(MediaType.APPLICATION_JSON);
        String secret = serverSecret();
        if (secret != null && !secret.isBlank()) {
            headers.set(HttpHeaders.AUTHORIZATION, "Bearer " + secret);
        }
        try {
            HttpEntity<Map<String, Object>> entity = new HttpEntity<>(body, headers);
            return restTemplate.exchange(pythonBase() + path, HttpMethod.POST, entity, String.class);
        } catch (org.springframework.web.client.HttpStatusCodeException e) {
            return ResponseEntity.status(e.getStatusCode()).body(e.getResponseBodyAsString());
        } catch (Exception e) {
            return ResponseEntity.status(502).body("{\"code\":502,\"msg\":\"python服务不可达\",\"data\":null}");
        }
    }
}

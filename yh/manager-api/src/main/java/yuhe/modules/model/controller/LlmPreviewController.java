package yuhe.modules.model.controller;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;

import org.apache.shiro.authz.annotation.RequiresPermissions;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import cn.hutool.json.JSONObject;
import cn.hutool.json.JSONUtil;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.Parameter;
import io.swagger.v3.oas.annotations.Parameters;
import io.swagger.v3.oas.annotations.tags.Tag;
import yuhe.common.constant.Constant;
import yuhe.common.exception.ErrorCode;
import yuhe.common.exception.RenException;
import yuhe.common.utils.Result;
import yuhe.modules.model.service.ModelConfigService;
import yuhe.modules.sys.service.SysParamsService;

/**
 * LLM 试聊代理
 * 前端链路模拟器经本端点代理访问 yuhe-server 内部试聊 API（127.0.0.1:8003），
 * 避免浏览器直连与凭据暴露；鉴权 = 管理端登录态（Shiro）+ 服务间 server.secret。
 */
@RestController
@RequestMapping("/models")
@Tag(name = "LLM试聊")
public class LlmPreviewController {

    /** LLM 生成耗时上限高于 TTS（流式回复可能较长） */
    private static final int TIMEOUT_SECONDS = 120;

    private static final String DEFAULT_HTTP_PORT = "8003";

    private static final HttpClient HTTP_CLIENT = HttpClient.newBuilder()
            .connectTimeout(Duration.ofSeconds(10))
            .build();

    private final SysParamsService sysParamsService;
    private final ModelConfigService modelConfigService;

    public LlmPreviewController(SysParamsService sysParamsService,
            ModelConfigService modelConfigService) {
        this.sysParamsService = sysParamsService;
        this.modelConfigService = modelConfigService;
    }

    @GetMapping("/llmPreview")
    @Operation(summary = "试聊指定大模型（代理 yuhe-server /api/llm/preview，返回回复文本与耗时）")
    @Parameters({
            @Parameter(name = "modelId", description = "LLM 模型ID", required = true),
            @Parameter(name = "text", description = "用户输入文本", required = true),
            @Parameter(name = "systemPrompt", description = "系统提示词（可空）"),
    })
    @RequiresPermissions("sys:role:normal")
    public Result<JSONObject> llmPreview(
            @RequestParam String modelId,
            @RequestParam String text,
            @RequestParam(required = false) String systemPrompt) {
        if (modelId == null || modelId.isBlank() || text == null || text.isBlank()) {
            throw new RenException(ErrorCode.PARAMS_GET_ERROR);
        }

        // 读取模型原始配置（含真实凭据，仅服务间转发用，不回传前端）
        String rawConfig = modelConfigService.getRawConfigJson(modelId);
        if (rawConfig == null || rawConfig.isBlank()) {
            RenException exception = new RenException(ErrorCode.RESOURCE_NOT_FOUND);
            exception.setMsg("模型不存在或未配置");
            throw exception;
        }

        String secret = sysParamsService.getValue(Constant.SERVER_SECRET, false);
        if (secret == null || secret.trim().isEmpty()) {
            throw new RenException("服务密钥未配置(server.secret)");
        }
        String port = sysParamsService.getValue("server.http_port", true);
        if (port == null || port.trim().isEmpty() || "null".equals(port)) {
            port = DEFAULT_HTTP_PORT;
        }

        StringBuilder url = new StringBuilder("http://127.0.0.1:").append(port.trim())
                .append("/api/llm/preview?text=")
                .append(java.net.URLEncoder.encode(text, StandardCharsets.UTF_8));
        if (systemPrompt != null && !systemPrompt.isBlank()) {
            url.append("&system_prompt=")
                    .append(java.net.URLEncoder.encode(systemPrompt, StandardCharsets.UTF_8));
        }

        HttpResponse<String> response;
        try {
            HttpRequest request = HttpRequest.newBuilder()
                    .uri(URI.create(url.toString()))
                    .header("Authorization", "Bearer " + secret.trim())
                    .header("Content-Type", "application/json")
                    .timeout(Duration.ofSeconds(TIMEOUT_SECONDS))
                    .POST(HttpRequest.BodyPublishers.ofString(rawConfig, StandardCharsets.UTF_8))
                    .build();
            response = HTTP_CLIENT.send(request, HttpResponse.BodyHandlers.ofString());
        } catch (Exception e) {
            throw new RenException("试聊服务不可用");
        }

        int status = response.statusCode();
        if (status == 401) {
            throw new RenException("服务密钥不一致，请联系管理员");
        }
        if (status == 404) {
            String msg = extractMsg(response.body());
            RenException exception = new RenException(ErrorCode.RESOURCE_NOT_FOUND);
            exception.setMsg(msg != null ? msg : "LLM类型不存在");
            throw exception;
        }
        if (status == 400) {
            String msg = extractMsg(response.body());
            throw new RenException(msg != null ? msg : "试聊参数错误");
        }
        if (status != 200) {
            throw new RenException("试聊失败（状态码 " + status + "）");
        }

        try {
            JSONObject payload = JSONUtil.parseObj(response.body());
            JSONObject data = payload.getJSONObject("data");
            if (data == null || data.getStr("reply") == null) {
                throw new RenException("试聊返回格式异常");
            }
            return new Result<JSONObject>().ok(data);
        } catch (RenException e) {
            throw e;
        } catch (Exception e) {
            throw new RenException("试聊返回解析失败");
        }
    }

    /** 从 Python 端 {code,msg} JSON 错误体提取 msg（宽松解析，失败返回 null） */
    private String extractMsg(String body) {
        if (body == null || body.isBlank()) {
            return null;
        }
        try {
            JSONObject json = JSONUtil.parseObj(body);
            return json.getStr("msg");
        } catch (Exception e) {
            return null;
        }
    }
}

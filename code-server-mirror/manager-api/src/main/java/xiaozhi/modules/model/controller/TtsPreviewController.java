package xiaozhi.modules.model.controller;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;

import org.apache.shiro.authz.annotation.RequiresPermissions;
import org.springframework.http.HttpHeaders;
import org.springframework.http.ResponseEntity;
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
import xiaozhi.common.constant.Constant;
import xiaozhi.common.exception.ErrorCode;
import xiaozhi.common.exception.RenException;
import xiaozhi.modules.model.service.ModelConfigService;
import xiaozhi.modules.sys.service.SysParamsService;

/**
 * TTS 音色试听代理
 * 前端音色选择器经本端点代理访问 xiaozhi-server 内部试听 API（127.0.0.1:8003），
 * 避免浏览器直连与凭据暴露；鉴权 = 管理端登录态（Shiro）+ 服务间 server.secret。
 */
@RestController
@RequestMapping("/models")
@Tag(name = "TTS音色试听")
public class TtsPreviewController {

    /** 请求超时时间（秒） */
    private static final int TIMEOUT_SECONDS = 60;

    private static final String DEFAULT_HTTP_PORT = "8003";

    private static final HttpClient HTTP_CLIENT = HttpClient.newBuilder()
            .connectTimeout(Duration.ofSeconds(10))
            .build();

    private final SysParamsService sysParamsService;
    private final ModelConfigService modelConfigService;

    public TtsPreviewController(SysParamsService sysParamsService,
            ModelConfigService modelConfigService) {
        this.sysParamsService = sysParamsService;
        this.modelConfigService = modelConfigService;
    }

    @GetMapping("/ttsPreview")
    @Operation(summary = "试听指定音色（代理 xiaozhi-server /api/tts/preview，返回音频流）")
    @Parameters({
            @Parameter(name = "modelId", description = "TTS 模型ID", required = true),
            @Parameter(name = "voice", description = "音色 ID（tts_voice）", required = true),
            @Parameter(name = "text", description = "试听文本（可空，默认固定话术）"),
    })
    @RequiresPermissions("sys:role:normal")
    public ResponseEntity<byte[]> ttsPreview(
            @RequestParam String modelId,
            @RequestParam String voice,
            @RequestParam(required = false) String text) {
        if (modelId == null || modelId.isBlank() || voice == null || voice.isBlank()) {
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
                .append("/api/tts/preview?voice=")
                .append(java.net.URLEncoder.encode(voice, StandardCharsets.UTF_8));
        if (text != null && !text.isBlank()) {
            url.append("&text=")
                    .append(java.net.URLEncoder.encode(text, StandardCharsets.UTF_8));
        }

        HttpResponse<byte[]> response = null;
        RuntimeException lastError = null;
        // 上游 TTS 偶发慢/抖动：最多尝试 2 次（首请求 + 1 次重试）
        for (int attempt = 0; attempt < 2; attempt++) {
            try {
                HttpRequest request = HttpRequest.newBuilder()
                        .uri(URI.create(url.toString()))
                        .header("Authorization", "Bearer " + secret.trim())
                        .header("Content-Type", "application/json")
                        .timeout(Duration.ofSeconds(TIMEOUT_SECONDS))
                        .POST(HttpRequest.BodyPublishers.ofString(rawConfig, StandardCharsets.UTF_8))
                        .build();
                response = HTTP_CLIENT.send(request, HttpResponse.BodyHandlers.ofByteArray());
                lastError = null;
                break;
            } catch (Exception e) {
                lastError = new RenException("试听服务超时或不可用，请重试");
            }
        }
        if (lastError != null || response == null) {
            throw lastError != null ? lastError : new RenException("试听服务不可用");
        }

        int status = response.statusCode();
        if (status == 401) {
            throw new RenException("服务密钥不一致，请联系管理员");
        }
        if (status == 404) {
            String msg = extractMsg(response.body());
            RenException exception = new RenException(ErrorCode.RESOURCE_NOT_FOUND);
            exception.setMsg(msg != null ? msg : "TTS类型不存在");
            throw exception;
        }
        if (status == 400) {
            String msg = extractMsg(response.body());
            throw new RenException(msg != null ? msg : "试听参数错误");
        }
        if (status != 200) {
            // 透传 Python 端的具体错误信息（如复刻音色 resource 不匹配的可操作提示）
            String msg = extractMsg(response.body());
            throw new RenException(msg != null ? msg : "试听失败（状态码 " + status + "）");
        }

        byte[] audio = response.body();
        if (audio == null || audio.length == 0) {
            throw new RenException("试听返回空音频");
        }
        String contentType = response.headers().firstValue("Content-Type").orElse("audio/wav");
        return ResponseEntity.ok()
                .header(HttpHeaders.CONTENT_TYPE, contentType)
                .header(HttpHeaders.CACHE_CONTROL, "no-store")
                .body(audio);
    }

    /** 从 Python 端 {code,msg} JSON 错误体提取 msg（宽松解析，失败返回 null） */
    private String extractMsg(byte[] body) {
        if (body == null || body.length == 0) {
            return null;
        }
        try {
            JSONObject json = JSONUtil.parseObj(new String(body, StandardCharsets.UTF_8));
            return json.getStr("msg");
        } catch (Exception e) {
            return null;
        }
    }
}

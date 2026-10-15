package xiaozhi.modules.model.controller;

import java.net.URI;
import java.net.URLEncoder;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;

import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.Parameter;
import xiaozhi.common.constant.Constant;
import xiaozhi.common.exception.ErrorCode;
import xiaozhi.common.exception.RenException;
import xiaozhi.common.utils.SpringContextUtils;
import xiaozhi.modules.sys.service.SysParamsService;
import org.apache.shiro.authz.annotation.RequiresPermissions;

/**
 * ASR 识别代理（cc-console 链路模拟器真实 ASR）。
 *
 * 浏览器录音（webm/opus）经前端 base64 上送 → 本代理原样转发 Python /api/asr/recognize，
 * ASR 模型原始配置（含凭据，仅服务间转发用，不回传前端）经 X-Asr-Config 头传入。
 * 安全模型与 TtsPreviewController 完全一致：回环 + server.secret。
 */
@RestController
@RequestMapping("models")
public class AsrRecognizeController {

    private static final int TIMEOUT_SECONDS = 90;
    private static final String DEFAULT_HTTP_PORT = "8003";

    private static final HttpClient HTTP_CLIENT = HttpClient.newBuilder()
            .connectTimeout(Duration.ofSeconds(10))
            .build();

    private final xiaozhi.modules.model.service.ModelConfigService modelConfigService;
    private final SysParamsService sysParamsService;

    public AsrRecognizeController(
            xiaozhi.modules.model.service.ModelConfigService modelConfigService,
            SysParamsService sysParamsService) {
        this.modelConfigService = modelConfigService;
        this.sysParamsService = sysParamsService;
    }

    @org.springframework.web.bind.annotation.PostMapping("/asrRecognize")
    @Operation(summary = "ASR 语音识别（代理转发，音频二进制 body）")
    @RequiresPermissions("sys:role:normal")
    public ResponseEntity<byte[]> asrRecognize(
            @Parameter(description = "ASR 模型ID") @RequestParam String modelId,
            @org.springframework.web.bind.annotation.RequestBody byte[] audio,
            @org.springframework.web.bind.annotation.RequestHeader(value = "Content-Type", required = false) String contentType) {
        if (modelId == null || modelId.isBlank()) {
            throw new RenException(ErrorCode.PARAMS_GET_ERROR);
        }
        if (audio == null || audio.length == 0) {
            throw new RenException("音频内容为空");
        }
        if (audio.length > 2 * 1024 * 1024) {
            throw new RenException("音频过大（>2MB）");
        }

        String rawConfig = modelConfigService.getRawConfigJson(modelId);
        if (rawConfig == null || rawConfig.isBlank()) {
            RenException e = new RenException(ErrorCode.RESOURCE_NOT_FOUND);
            e.setMsg("ASR 模型不存在或未配置");
            throw e;
        }

        String secret = sysParamsService.getValue(Constant.SERVER_SECRET, false);
        if (secret == null || secret.trim().isEmpty()) {
            throw new RenException("服务密钥未配置(server.secret)");
        }
        String port = sysParamsService.getValue("server.http_port", true);
        if (port == null || port.trim().isEmpty() || "null".equals(port)) {
            port = DEFAULT_HTTP_PORT;
        }

        // X-Asr-Config 头与 rawConfig 均含非 ASCII 凭据时需可打印 ASCII —— rawConfig 的
        // 值全部来自模型配置 JSON（UTF-8）。HttpRequest.header 不允许非法字符，
        // 但实测 api_key 均为 ASCII；含非 ASCII 时降级为 URL 编码传输。
        String safeConfig = rawConfig.matches("\\p{ASCII}*")
                ? rawConfig
                : java.util.Base64.getEncoder().encodeToString(
                        rawConfig.getBytes(StandardCharsets.UTF_8));
        String configHeader = rawConfig.matches("\\p{ASCII}*") ? "X-Asr-Config" : "X-Asr-Config-B64";

        String url = "http://127.0.0.1:" + port.trim() + "/api/asr/recognize?modelId="
                + URLEncoder.encode(modelId, StandardCharsets.UTF_8);

        HttpResponse<byte[]> response;
        try {
            HttpRequest request = HttpRequest.newBuilder()
                    .uri(URI.create(url))
                    .header("Authorization", "Bearer " + secret.trim())
                    .header("Content-Type",
                            (contentType != null && !contentType.isBlank())
                                    ? contentType
                                    : "audio/webm")
                    .header(configHeader, safeConfig)
                    .timeout(Duration.ofSeconds(TIMEOUT_SECONDS))
                    .POST(HttpRequest.BodyPublishers.ofByteArray(audio))
                    .build();
            response = HTTP_CLIENT.send(request, HttpResponse.BodyHandlers.ofByteArray());
        } catch (Exception e) {
            throw new RenException("识别服务超时或不可用，请重试");
        }

        if (response.statusCode() != 200) {
            String msg = extractMsg(response.body());
            throw new RenException(msg != null ? msg : "识别失败（状态码 " + response.statusCode() + "）");
        }

        byte[] body = response.body();
        if (body == null || body.length == 0) {
            throw new RenException("识别返回空响应");
        }
        return ResponseEntity.status(HttpStatus.OK)
                .contentType(MediaType.APPLICATION_JSON)
                .body(body);
    }

    private static String extractMsg(byte[] json) {
        try {
            com.fasterxml.jackson.databind.JsonNode node =
                    new com.fasterxml.jackson.databind.ObjectMapper().readTree(json);
            if (node.hasNonNull("msg")) {
                return node.get("msg").asText();
            }
        } catch (Exception ignored) {
        }
        return null;
    }
}

package yuhe.modules.model.controller;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;
import java.util.ArrayList;
import java.util.List;
import java.util.stream.Collectors;

import org.apache.shiro.authz.annotation.RequiresPermissions;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import cn.hutool.json.JSONArray;
import cn.hutool.json.JSONObject;
import cn.hutool.json.JSONUtil;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.Parameter;
import io.swagger.v3.oas.annotations.tags.Tag;
import yuhe.common.utils.Result;

/**
 * 千问TTS模型列表代理
 * 前端「获取模型列表」按钮通过本端点代理访问千问平台模型列表，避免浏览器跨域
 */
@RestController
@RequestMapping("/models")
@Tag(name = "千问TTS模型")
public class QwenTtsModelController {

    /** 千问平台模型列表端点 */
    private static final String QWEN_MODELS_URL = "https://maas.qianwenaiapi.com/compatible-mode/v1/models";

    /**
     * 千问平台 /v1/models 端点未返回但实测可用的 TTS 模型（走独立端点，静态补充）
     */
    private static final List<String> EXTRA_MODELS = List.of(
            "qwen-audio-3.0-tts-flash",
            "qwen-audio-3.1-tts-flash",
            "qwen-audio-3.0-tts-plus");

    /** 请求超时时间（秒） */
    private static final int TIMEOUT_SECONDS = 10;

    private static final HttpClient HTTP_CLIENT = HttpClient.newBuilder()
            .connectTimeout(Duration.ofSeconds(TIMEOUT_SECONDS))
            .build();

    @GetMapping("/qwenTtsModels")
    @Operation(summary = "获取千问TTS模型列表（代理千问平台 /v1/models，过滤 TTS 相关模型）")
    @Parameter(name = "apiKey", description = "千问平台 API 密钥", required = true)
    @RequiresPermissions("sys:role:normal")
    public Result<List<String>> getQwenTtsModels(@RequestParam String apiKey) {
        if (apiKey == null || apiKey.isBlank()) {
            return new Result<List<String>>().error("API密钥不能为空");
        }

        HttpResponse<String> response;
        try {
            HttpRequest request = HttpRequest.newBuilder()
                    .uri(URI.create(QWEN_MODELS_URL))
                    .header("Authorization", "Bearer " + apiKey)
                    .timeout(Duration.ofSeconds(TIMEOUT_SECONDS))
                    .GET()
                    .build();
            response = HTTP_CLIENT.send(request, HttpResponse.BodyHandlers.ofString());
        } catch (Exception e) {
            return new Result<List<String>>().error("获取模型列表失败：无法访问千问平台，请检查网络或API密钥");
        }

        int statusCode = response.statusCode();
        if (statusCode == 401) {
            return new Result<List<String>>().error("获取模型列表失败：API密钥无效或已过期");
        }
        if (statusCode != 200) {
            return new Result<List<String>>().error("获取模型列表失败：千问平台返回状态码 " + statusCode);
        }

        String body = response.body();
        if (body == null || body.isBlank()) {
            return new Result<List<String>>().error("获取模型列表失败：千问平台返回内容为空");
        }

        List<String> models = new ArrayList<>();
        try {
            JSONObject json = JSONUtil.parseObj(body);
            JSONArray data = json.getJSONArray("data");
            if (data != null) {
                for (int i = 0; i < data.size(); i++) {
                    JSONObject item = data.getJSONObject(i);
                    String id = item.getStr("id");
                    if (id == null) {
                        continue;
                    }
                    // 过滤：id 含 tts（忽略大小写）且不含 realtime（本项目非实时场景）
                    String lowerId = id.toLowerCase();
                    if (lowerId.contains("tts") && !lowerId.contains("realtime")) {
                        models.add(id);
                    }
                }
            }
        } catch (Exception e) {
            return new Result<List<String>>().error("获取模型列表失败：千问平台返回格式异常");
        }

        models.sort(String::compareTo);
        // 追加补充模型（去重，防止平台端点未来收录后重复）
        List<String> extras = EXTRA_MODELS.stream().filter(m -> !models.contains(m)).collect(Collectors.toList());
        models.addAll(extras);

        return new Result<List<String>>().ok(models);
    }
}

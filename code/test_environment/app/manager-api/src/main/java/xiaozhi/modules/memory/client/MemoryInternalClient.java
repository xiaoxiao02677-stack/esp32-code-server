package xiaozhi.modules.memory.client;

import java.nio.charset.StandardCharsets;
import java.util.Collections;
import java.util.Map;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.http.HttpEntity;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpMethod;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.http.client.SimpleClientHttpRequestFactory;
import org.springframework.stereotype.Component;
import org.springframework.web.client.HttpStatusCodeException;
import org.springframework.web.client.RestTemplate;

import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;

import xiaozhi.common.constant.Constant;
import xiaozhi.common.exception.ErrorCode;
import xiaozhi.common.exception.RenException;
import xiaozhi.modules.sys.service.SysParamsService;

/**
 * xiaozhi-server 内部记忆管理 HTTP 客户端
 * 访问 http://127.0.0.1:{server.http_port}/api/memory/**（Bearer server.secret 鉴权，与 /mcp/vision 同机制）
 */
@Component
public class MemoryInternalClient {

    private static final Logger log = LoggerFactory.getLogger(MemoryInternalClient.class);

    /** 内部 API 请求超时（毫秒）：覆盖 SQLite busy_timeout（10s） */
    private static final int TIMEOUT_MILLIS = 10000;

    private static final String DEFAULT_HTTP_PORT = "8003";

    /** server.http_port 系统参数编码（与 /config/server-base 同源） */
    private static final String PARAM_HTTP_PORT = "server.http_port";

    private final RestTemplate restTemplate;
    private final ObjectMapper objectMapper = new ObjectMapper();

    private final SysParamsService sysParamsService;

    public MemoryInternalClient(SysParamsService sysParamsService) {
        this.sysParamsService = sysParamsService;
        SimpleClientHttpRequestFactory factory = new SimpleClientHttpRequestFactory();
        factory.setConnectTimeout(TIMEOUT_MILLIS);
        factory.setReadTimeout(TIMEOUT_MILLIS);
        this.restTemplate = new RestTemplate(factory);
    }

    /**
     * GET 请求（query 参数可为 null）
     */
    public Map<String, Object> get(String path, Map<String, Object> queryParams) {
        return execute(HttpMethod.GET, buildUrl(path, queryParams), null);
    }

    /**
     * POST 请求（JSON body 可为 null）
     */
    public Map<String, Object> post(String path, Object body) {
        return execute(HttpMethod.POST, buildUrl(path, null), body);
    }

    /**
     * PUT 请求
     */
    public Map<String, Object> put(String path, Object body) {
        return execute(HttpMethod.PUT, buildUrl(path, null), body);
    }

    /**
     * DELETE 请求
     */
    public Map<String, Object> delete(String path) {
        return execute(HttpMethod.DELETE, buildUrl(path, null), null);
    }

    private Map<String, Object> execute(HttpMethod method, String url, Object body) {
        ResponseEntity<String> response;
        try {
            HttpHeaders headers = buildHeaders();
            HttpEntity<Object> requestEntity = new HttpEntity<>(body, headers);
            // 传 java.net.URI 而非 String：URI 对象不走 RestTemplate 的模板变量展开（TEMPLATE_AND_VALUES 模式会对 % 再编码为 %25，中文关键词双重编码缺陷）
            response = restTemplate.exchange(java.net.URI.create(url), method, requestEntity, String.class);
        } catch (RenException e) {
            throw e;
        } catch (HttpStatusCodeException hce) {
            // RestTemplate 默认对 4xx/5xx 抛出本异常，按状态码分流
            // （Python 端 401/400/404 均返回真实 HTTP 状态码 + {code,msg} JSON body）
            int status = hce.getStatusCode().value();
            if (status == 401) {
                log.error("记忆内部服务鉴权失败（server.secret 不一致）: url={}", url);
                RenException exception = new RenException(ErrorCode.NO_PERMISSION);
                exception.setMsg("服务密钥不一致，请联系管理员");
                throw exception;
            }
            if (status == 404) {
                log.warn("记忆条目不存在: url={}", url);
                RenException exception = new RenException(ErrorCode.RESOURCE_NOT_FOUND);
                exception.setMsg("记忆条目不存在");
                throw exception;
            }
            if (status == 400) {
                String msg = extractMsg(hce.getResponseBodyAsString());
                log.warn("记忆内部服务参数错误: url={}, msg={}", url, msg);
                throw new RenException(msg);
            }
            log.error("记忆内部服务响应异常: url={}, status={}", url, status);
            throw new RenException("记忆服务不可用");
        } catch (Exception e) {
            log.error("记忆内部服务调用失败: url={}, error={}", url, e.getMessage());
            throw new RenException("记忆服务不可用");
        }

        String responseBody = response.getBody();
        if (responseBody == null || responseBody.isEmpty()) {
            log.error("记忆内部服务响应为空: url={}", url);
            throw new RenException("记忆服务不可用");
        }

        Map<String, Object> resultMap;
        try {
            resultMap = objectMapper.readValue(responseBody, new TypeReference<Map<String, Object>>() {
            });
        } catch (Exception e) {
            log.error("记忆内部服务响应解析失败: url={}, error={}", url, e.getMessage());
            throw new RenException("记忆服务不可用");
        }

        Integer code = (Integer) resultMap.get("code");
        if (code != null && code != 0) {
            String msg = resultMap.get("msg") != null ? resultMap.get("msg").toString() : "记忆服务请求失败";
            log.error("记忆内部服务业务错误: url={}, code={}, msg={}", url, code, msg);
            throw new RenException(msg);
        }
        return resultMap;
    }

    /**
     * 从 4xx 响应体提取 Python 端 {code,msg} 包中的 msg，失败时回落默认提示
     */
    private String extractMsg(String responseBody) {
        if (responseBody == null || responseBody.isEmpty()) {
            return "记忆服务请求失败";
        }
        try {
            Map<String, Object> map = objectMapper.readValue(responseBody, new TypeReference<Map<String, Object>>() {
            });
            if (map.get("msg") != null) {
                return map.get("msg").toString();
            }
        } catch (Exception e) {
            log.warn("记忆内部服务错误响应体解析失败: {}", e.getMessage());
        }
        return "记忆服务请求失败";
    }

    private HttpHeaders buildHeaders() {
        HttpHeaders headers = new HttpHeaders();
        headers.setContentType(MediaType.APPLICATION_JSON);
        headers.setAcceptCharset(Collections.singletonList(StandardCharsets.UTF_8));
        // fromCache=false 直读库（先例 DeviceServiceImpl.generateWebSocketToken），防管理员轮换 secret 后本端持续用缓存旧值 401
        String secret = sysParamsService.getValue(Constant.SERVER_SECRET, false);
        if (secret == null || secret.trim().isEmpty()) {
            throw new RenException("服务密钥未配置(server.secret)");
        }
        headers.setBearerAuth(secret.trim());
        return headers;
    }

    private String buildUrl(String path, Map<String, Object> queryParams) {
        String port = sysParamsService.getValue(PARAM_HTTP_PORT, true);
        if (port == null || port.trim().isEmpty() || "null".equals(port)) {
            port = DEFAULT_HTTP_PORT;
        }
        StringBuilder url = new StringBuilder("http://127.0.0.1:").append(port.trim()).append("/api/memory");
        if (!path.startsWith("/")) {
            url.append("/");
        }
        url.append(path);
        if (queryParams != null && !queryParams.isEmpty()) {
            StringBuilder query = new StringBuilder();
            queryParams.forEach((key, value) -> {
                if (value != null) {
                    if (query.length() > 0) {
                        query.append("&");
                    }
                    query.append(key).append("=").append(urlEncode(value.toString()));
                }
            });
            if (query.length() > 0) {
                url.append("?").append(query);
            }
        }
        return url.toString();
    }

    private String urlEncode(String value) {
        try {
            // 空格编码为 %20 而非 +：query 语义中 + 会被服务端解码为空格，劈开含空格的关键词
            return java.net.URLEncoder.encode(value, StandardCharsets.UTF_8.name()).replace("+", "%20");
        } catch (Exception e) {
            return value;
        }
    }
}

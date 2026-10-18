package yuhe.modules.wallpaper.client;

import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.http.HttpEntity;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpMethod;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.http.client.SimpleClientHttpRequestFactory;
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestTemplate;

import yuhe.common.constant.Constant;
import yuhe.common.utils.JsonUtils;
import yuhe.modules.sys.service.SysParamsService;

/**
 * 壁纸即时下发客户端（P1-3）
 *
 * <p>契约（与 yuhe-server Python 侧 /api/wallpaper/dispatch 对齐）：
 * POST http://127.0.0.1:{server.http_port}/api/wallpaper/dispatch，
 * Bearer server.secret 鉴权，body：
 * {"device_ids":["AA:BB:.."],"wallpaper":{"version":"3","url":"...","md5":"...",
 *  "size":115200,"format":"rgb565"}}；
 * 响应 data：{"sent":["MAC"],"offline":["MAC"]}。
 *
 * <p>地址来源与 MemoryInternalClient 一致（server.http_port，缺省 8003），不新增配置项。
 * 失败只记日志并返回 rejected，由调用方保留 device_config 落库结果（下次启动仍可生效）。
 */
@Component
public class WallpaperDispatchClient {

    private static final Logger log = LoggerFactory.getLogger(WallpaperDispatchClient.class);

    /** 即时推送属尽力而为，超时时间取短值，避免管理端请求被拖住 */
    private static final int TIMEOUT_MILLIS = 5000;

    private static final String DEFAULT_HTTP_PORT = "8003";

    private static final String PARAM_HTTP_PORT = "server.http_port";

    private static final String DISPATCH_PATH = "/api/wallpaper/dispatch";

    private final RestTemplate restTemplate;

    private final SysParamsService sysParamsService;

    public WallpaperDispatchClient(SysParamsService sysParamsService) {
        this.sysParamsService = sysParamsService;
        SimpleClientHttpRequestFactory factory = new SimpleClientHttpRequestFactory();
        factory.setConnectTimeout(TIMEOUT_MILLIS);
        factory.setReadTimeout(TIMEOUT_MILLIS);
        this.restTemplate = new RestTemplate(factory);
    }

    /**
     * 尽力而为地通知 Python 侧向在线设备即时下发壁纸
     *
     * @param macAddresses 目标设备 MAC 列表（Python 侧按 MAC 匹配在线连接）
     * @param wallpaper    壁纸对象（version/url/md5/size/format）
     * @return 受理结果（accepted=false 表示通道不可用，已记日志不抛异常）
     */
    public DispatchResult dispatch(List<String> macAddresses, Map<String, Object> wallpaper) {
        if (macAddresses == null || macAddresses.isEmpty()) {
            return DispatchResult.rejected();
        }
        String secret = sysParamsService.getValue(Constant.SERVER_SECRET, true);
        if (secret == null || secret.isBlank()) {
            log.warn("[wallpaper] server.secret 未配置，跳过即时下发（device_config 已落库，下次启动生效）");
            return DispatchResult.rejected();
        }
        String port = sysParamsService.getValue(PARAM_HTTP_PORT, true);
        if (port == null || port.isBlank() || "null".equals(port)) {
            port = DEFAULT_HTTP_PORT;
        }
        String url = "http://127.0.0.1:" + port.trim() + DISPATCH_PATH;

        HttpHeaders headers = new HttpHeaders();
        headers.setContentType(MediaType.APPLICATION_JSON);
        headers.setBearerAuth(secret.trim());
        Map<String, Object> body = Map.of(
                "device_ids", macAddresses,
                "wallpaper", wallpaper);
        try {
            ResponseEntity<String> response = restTemplate.exchange(
                    java.net.URI.create(url), HttpMethod.POST, new HttpEntity<>(body, headers), String.class);
            if (!response.getStatusCode().is2xxSuccessful()) {
                log.warn("[wallpaper] 即时下发被拒绝 status={} devices={}",
                        response.getStatusCode(), macAddresses.size());
                return DispatchResult.rejected();
            }
            log.info("[wallpaper] 即时下发已受理 devices={}", macAddresses.size());
            return parseResult(response.getBody());
        } catch (Exception e) {
            log.warn("[wallpaper] 即时下发失败（device_config 已落库，下次启动生效）: {}", e.getMessage());
            return DispatchResult.rejected();
        }
    }

    /**
     * 解析 {"code":0,"data":{"sent":[...],"queued":[...],"offline":[...]}}；
     * queued 为旧版 Python 不存在的字段（解析不到视为空集合，兼容回退）；
     * 解析失败按「已受理但未区分」处理
     */
    private DispatchResult parseResult(String responseBody) {
        Set<String> sent = new HashSet<>();
        Set<String> queued = new HashSet<>();
        Set<String> offline = new HashSet<>();
        try {
            Map<String, Object> root = JsonUtils.parseMap(responseBody);
            Object data = root == null ? null : root.get("data");
            if (data instanceof Map<?, ?> dataMap) {
                collectMacs(dataMap.get("sent"), sent);
                collectMacs(dataMap.get("queued"), queued);
                collectMacs(dataMap.get("offline"), offline);
            }
        } catch (Exception e) {
            log.warn("[wallpaper] 即时下发响应解析失败: {}", e.getMessage());
        }
        return new DispatchResult(true, sent, queued, offline);
    }

    private void collectMacs(Object value, Set<String> target) {
        if (value instanceof List<?> list) {
            for (Object item : list) {
                if (item != null) {
                    target.add(item.toString().toLowerCase());
                }
            }
        }
    }

    /** 即时通道受理结果：sent 已推送；queued 已入离线补投队列（设备上线自动下发）；offline 仅落 device_config */
    public static final class DispatchResult {

        private final boolean accepted;
        private final Set<String> sentMacs;
        private final Set<String> queuedMacs;
        private final Set<String> offlineMacs;

        DispatchResult(boolean accepted, Set<String> sentMacs,
                       Set<String> queuedMacs, Set<String> offlineMacs) {
            this.accepted = accepted;
            this.sentMacs = sentMacs;
            this.queuedMacs = queuedMacs;
            this.offlineMacs = offlineMacs;
        }

        static DispatchResult rejected() {
            return new DispatchResult(false, Set.of(), Set.of(), Set.of());
        }

        public boolean isAccepted() {
            return accepted;
        }

        /** mac 是否在已推送列表（大小写不敏感） */
        public boolean isSent(String mac) {
            return mac != null && sentMacs.contains(mac.toLowerCase());
        }

        /** mac 是否已入离线补投队列（设备文本通道上线后自动下发） */
        public boolean isQueued(String mac) {
            return mac != null && queuedMacs.contains(mac.toLowerCase());
        }

        /** mac 是否离线（need_bind / MQTT 网关等无法直投） */
        public boolean isOffline(String mac) {
            return mac != null && offlineMacs.contains(mac.toLowerCase());
        }
    }
}

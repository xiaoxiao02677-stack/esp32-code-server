package xiaozhi.modules.agent.controller;

import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

import org.apache.shiro.authz.annotation.RequiresPermissions;
import org.springframework.http.HttpEntity;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpMethod;
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
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import xiaozhi.common.constant.Constant;
import xiaozhi.common.exception.ErrorCode;
import xiaozhi.common.user.UserDetail;
import xiaozhi.common.utils.Result;
import xiaozhi.modules.agent.entity.AgentEntity;
import xiaozhi.modules.agent.service.AgentService;
import xiaozhi.modules.agent.service.AgentWakeWordService;
import xiaozhi.modules.device.entity.DeviceEntity;
import xiaozhi.modules.device.service.DeviceConfigService;
import xiaozhi.modules.device.service.DeviceService;
import xiaozhi.modules.security.user.SecurityUser;
import xiaozhi.modules.sys.service.SysParamsService;

/**
 * 唤醒词管理
 *
 * @author xiaozhi
 */
@Slf4j
@Tag(name = "唤醒词管理")
@RequiredArgsConstructor
@RestController
@RequestMapping("/agent/wake-word")
public class WakeWordController {

    private static final int MAX_WAKE_WORDS = 10;
    private static final int MAX_WAKE_WORD_LENGTH = 30;
    /**
     * 设备级硬件唤醒词数量上限（MultiNet 引擎契约，与 DeviceConfigServiceImpl/ConfigServiceImpl 同源）；
     * 超出部分不入 ai_device_config，避免整包被 sanitizeWakeWord 丢弃导致同步失效
     */
    private static final int MAX_DEVICE_WAKE_WORDS = 5;
    private static final String DEFAULT_HTTP_PORT = "8003";
    private static final String PARAM_HTTP_PORT = "server.http_port";

    private final AgentService agentService;
    private final AgentWakeWordService agentWakeWordService;
    private final SysParamsService sysParamsService;
    private final RestTemplate restTemplate;
    private final DeviceService deviceService;
    private final DeviceConfigService deviceConfigService;

    /**
     * 获取指定智能体的唤醒词列表
     */
    @Operation(summary = "获取唤醒词列表")
    @GetMapping("/{agentId}")
    @RequiresPermissions("sys:role:normal")
    public Result<List<String>> get(@PathVariable String agentId) {
        UserDetail user = SecurityUser.getUser();
        if (!agentService.checkAgentPermission(agentId, user.getId())) {
            return new Result<List<String>>().error(ErrorCode.WAKE_WORD_AGENT_NOT_FOUND);
        }
        // 从 AgentEntity 读取 wakeWords（分号分隔）
        AgentEntity agent = agentService.getAgentById(agentId);
        if (agent == null) {
            return new Result<List<String>>().error(ErrorCode.WAKE_WORD_AGENT_NOT_FOUND);
        }
        String wakeWordsStr = agent.getWakeWords();
        if (wakeWordsStr == null || wakeWordsStr.isBlank()) {
            return new Result<List<String>>().ok(List.of());
        }
        List<String> wakeWords = List.of(wakeWordsStr.split(";"));
        return new Result<List<String>>().ok(wakeWords);
    }

    /**
     * 设置指定智能体的唤醒词列表
     *
     * <p>请求体 JSON 示例：{"wakeWords": ["你好小智", "Hi XiaoZhi"]}
     */
    @Operation(summary = "设置唤醒词")
    @PostMapping("/{agentId}")
    @RequiresPermissions("sys:role:normal")
    public Result<Void> set(@PathVariable String agentId, @RequestBody WakeWordRequest body) {
        UserDetail user = SecurityUser.getUser();
        if (!agentService.checkAgentPermission(agentId, user.getId())) {
            return new Result<Void>().error(ErrorCode.WAKE_WORD_AGENT_NOT_FOUND);
        }

        List<String> wakeWords = body.getWakeWords();
        if (wakeWords == null || wakeWords.isEmpty()) {
            return new Result<Void>().error(ErrorCode.WAKE_WORD_EMPTY);
        }
        if (wakeWords.size() > MAX_WAKE_WORDS) {
            return new Result<Void>().error(ErrorCode.WAKE_WORD_TOO_MANY);
        }
        for (String word : wakeWords) {
            if (word == null || word.isBlank()) {
                return new Result<Void>().error(ErrorCode.WAKE_WORD_EMPTY);
            }
            if (word.length() > MAX_WAKE_WORD_LENGTH) {
                return new Result<Void>().error(ErrorCode.WAKE_WORD_TOO_LONG);
            }
        }

        // 持久化到 AgentEntity.wakeWords（分号分隔）
        String wakeWordsStr = wakeWords.stream().collect(Collectors.joining(";"));
        agentService.updateAgentWakeWords(agentId, wakeWordsStr, user.getId());

        // 同步设备级硬件唤醒词到 ai_device_config（设备重连时下发的唯一持久源），
        // 须在推送之前完成，保证推送失败/离线设备重连后也能拿到新词
        syncWakeWordsToDeviceConfig(agentId, wakeWords);

        // 推送唤醒词给在线设备
        pushWakeWordsToDevices(agentId, wakeWords);

        return new Result<Void>().ok(null);
    }

    /**
     * 将唤醒词同步写入该智能体下所有设备的云端配置（ai_device_config.wake_word）
     *
     * <p>语义：wake_words 列表 → 设备表 wake_word 键，统一存 List&lt;String&gt;
     * （ConfigServiceImpl 下发时 String/List 均支持）。超过设备侧 5 词上限时截断前 5 个，
     * 避免被 DeviceConfigServiceImpl.sanitizeWakeWord 整体丢弃导致设备重连拿到旧词。
     * 单台设备同步失败只记日志，不阻断其它设备及后续推送。
     */
    private void syncWakeWordsToDeviceConfig(String agentId, List<String> wakeWords) {
        List<DeviceEntity> devices = deviceService.getDevicesByAgentId(agentId);
        if (devices == null || devices.isEmpty()) {
            return;
        }
        List<String> deviceWakeWords = wakeWords.size() > MAX_DEVICE_WAKE_WORDS
                ? wakeWords.subList(0, MAX_DEVICE_WAKE_WORDS)
                : wakeWords;
        Map<String, Object> config = Map.of("wake_word", deviceWakeWords);
        for (DeviceEntity device : devices) {
            try {
                deviceConfigService.upsertByMac(device.getMacAddress(), config);
            } catch (Exception e) {
                log.error("[WakeWord] 同步设备配置失败 agentId={} deviceId={}: {}",
                        agentId, device.getId(), e.getMessage());
            }
        }
    }

    /**
     * 推送唤醒词给指定智能体的所有在线设备
     */
    private void pushWakeWordsToDevices(String agentId, List<String> wakeWords) {
        try {
            String httpPort = sysParamsService.getValue(PARAM_HTTP_PORT, true);
            if (httpPort == null || httpPort.isBlank()) {
                httpPort = DEFAULT_HTTP_PORT;
            }
            String secret = sysParamsService.getValue(Constant.SERVER_SECRET, true);
            if (secret == null || secret.isBlank()) {
                return;
            }
            String url = String.format("http://127.0.0.1:%s/api/wake-word/push", httpPort);
            HttpHeaders headers = new HttpHeaders();
            headers.set(HttpHeaders.AUTHORIZATION, "Bearer " + secret);
            headers.setContentType(org.springframework.http.MediaType.APPLICATION_JSON);
            Map<String, Object> body = Map.of(
                "agent_id", agentId,
                "wake_words", wakeWords
            );
            HttpEntity<Map<String, Object>> request = new HttpEntity<>(body, headers);
            ResponseEntity<String> response = restTemplate.exchange(url, HttpMethod.POST, request, String.class);
            if (response.getStatusCode().is2xxSuccessful()) {
                System.out.println("[WakeWord] 推送成功 agentId=" + agentId);
            } else {
                System.err.println("[WakeWord] 推送失败 agentId=" + agentId + " status=" + response.getStatusCode());
            }
        } catch (Exception e) {
            System.err.println("[WakeWord] 推送异常 agentId=" + agentId + ": " + e.getMessage());
        }
    }

    /**
     * 唤醒词请求体
     */
    public static class WakeWordRequest {
        private List<String> wakeWords;

        public List<String> getWakeWords() {
            return wakeWords;
        }

        public void setWakeWords(List<String> wakeWords) {
            this.wakeWords = wakeWords;
        }
    }
}

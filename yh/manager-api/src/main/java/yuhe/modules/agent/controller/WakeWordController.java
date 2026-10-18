package yuhe.modules.agent.controller;

import java.util.ArrayList;
import java.util.HashMap;
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
import yuhe.common.constant.Constant;
import yuhe.common.exception.ErrorCode;
import yuhe.common.user.UserDetail;
import yuhe.common.utils.Result;
import yuhe.common.utils.WakeWordPinyinUtils;
import yuhe.modules.agent.entity.AgentEntity;
import yuhe.modules.agent.service.AgentService;
import yuhe.modules.agent.service.AgentWakeWordService;
import yuhe.modules.device.entity.DeviceEntity;
import yuhe.modules.device.service.DeviceConfigService;
import yuhe.modules.device.service.DeviceService;
import yuhe.modules.security.user.SecurityUser;
import yuhe.modules.sys.service.SysParamsService;

/**
 * 唤醒词管理
 *
 * @author yuhe
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
     * <p>请求体 JSON 示例：{"wakeWords": ["你好小智", "Hi Yuhe"]}
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
        // 可转换性校验：能存进库不等于能下发到设备。
        // 汉字转拼音后超 60 字符、含英文字母混排、出表音节（m/yiao）都会在
        // syncWakeWordsToDeviceConfig 里被静默跳过 —— 接口返回成功、设备啥也没变，
        // 是最难排查的一类失效。这里提前失败，让用户当场看到问题。
        List<String> effectiveWords = wakeWords.size() > MAX_DEVICE_WAKE_WORDS
                ? wakeWords.subList(0, MAX_DEVICE_WAKE_WORDS) : wakeWords;
        List<String[]> pairs = WakeWordPinyinUtils.toFirmwarePairs(effectiveWords);
        if (pairs.size() < effectiveWords.size()) {
            // 区分"太长"和"含不可转换字符"，报错才看得懂。
            // 8 = 拼音上限 60 / 最坏音节 7（zhuang 6 字母 + 空格）向下取整，
            // 与前端 WakeWord.vue 的 8 汉字校验同源
            boolean tooLong = effectiveWords.stream().anyMatch(w -> w.length() > 8);
            return new Result<Void>().error(tooLong
                    ? ErrorCode.WAKE_WORD_TOO_LONG
                    : ErrorCode.WAKE_WORD_INVALID_CHAR);
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
     * 将唤醒词同步写入该智能体下所有设备的云端配置
     * （ai_device_config 的 wake_word + wake_word_display 双键）
     *
     * <p>语义：设备侧 MultiNet 引擎只认无调拼音（mn7_cn 词表全是拼音音节），
     * 故库里同时存成对的两个数组——{@code wake_word} 存拼音供引擎识别，
     * {@code wake_word_display} 存汉字原文供界面/日志展示。两数组**必须同序等长**，
     * 因此这里用 {@link WakeWordPinyinUtils#toFirmwarePairs} 成对构建，
     * 绝不能用 toPinyinList（它跳过失败项会导致"喊 A 显示 B"）。
     *
     * <p>超过设备侧 5 词上限时截断前 5 个，避免被 DeviceConfigServiceImpl.sanitizeWakeWord
     * 整体丢弃导致设备重连拿到旧词。全部无法转换时直接返回、不下发空数组——
     * 空数组在设备侧含义是"清空唤醒词"，比不下发更糟。
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
        Map<String, Object> config = buildPinyinDisplayConfig(agentId, deviceWakeWords);
        if (config == null) {
            return;
        }
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
     * 成对构建 {wake_word: 拼音列表, wake_word_display: 汉字列表}
     *
     * @return 无可下发词时返回 null（调用方须放弃下发，不能下发空数组）
     */
    private Map<String, Object> buildPinyinDisplayConfig(String agentId, List<String> wakeWords) {
        List<String[]> pairs = WakeWordPinyinUtils.toFirmwarePairs(wakeWords);
        if (pairs.isEmpty()) {
            System.err.println("[WakeWord] 唤醒词全部无法转为固件可用拼音，保留设备原配置 agentId="
                    + agentId + " 原值=" + wakeWords);
            return null;
        }
        if (pairs.size() < wakeWords.size()) {
            log.warn("[WakeWord] {} 个唤醒词中有 {} 个无法转换（含英文字母混排或表外字），已跳过",
                    wakeWords.size(), wakeWords.size() - pairs.size());
        }
        List<String> pinyins = new ArrayList<>(pairs.size());
        List<String> displays = new ArrayList<>(pairs.size());
        for (String[] pair : pairs) {
            pinyins.add(pair[0]);
            displays.add(pair[1]);
        }
        Map<String, Object> config = new HashMap<>();
        config.put("wake_word", pinyins);
        config.put("wake_word_display", displays);
        return config;
    }

    /**
     * 推送唤醒词给指定智能体的所有在线设备
     *
     * <p>body 必须与持久化同源：{@code wake_words} 传拼音、{@code wake_word_display}
     * 传汉字原文，两者同序等长。Python 侧 {@code push_wake_words} 依赖 display
     * 覆盖 {@code conn.config["wakeup_words"]}（该键必须存汉字，listenMessageHandler
     * 用中文 ASR 文本做成员判断，存拼音会让文本唤醒永久失效）。
     */
    private void pushWakeWordsToDevices(String agentId, List<String> wakeWords) {
        try {
            List<String> truncated = wakeWords.size() > MAX_DEVICE_WAKE_WORDS
                    ? wakeWords.subList(0, MAX_DEVICE_WAKE_WORDS)
                    : wakeWords;
            Map<String, Object> config = buildPinyinDisplayConfig(agentId, truncated);
            if (config == null) {
                return;
            }
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
            Map<String, Object> body = new HashMap<>();
            body.put("agent_id", agentId);
            body.put("wake_words", config.get("wake_word"));
            body.put("wake_word_display", config.get("wake_word_display"));
            HttpEntity<Map<String, Object>> request = new HttpEntity<>(body, headers);
            ResponseEntity<String> response = restTemplate.exchange(url, HttpMethod.POST, request, String.class);
            if (response.getStatusCode().is2xxSuccessful()) {
                System.out.println("[WakeWord] 推送成功 agentId=" + agentId
                        + " 拼音=" + config.get("wake_word") + " 展示=" + config.get("wake_word_display"));
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

package xiaozhi.modules.agent.controller;

import java.util.List;
import java.util.stream.Collectors;

import org.apache.shiro.authz.annotation.RequiresPermissions;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import lombok.RequiredArgsConstructor;
import xiaozhi.common.exception.ErrorCode;
import xiaozhi.common.user.UserDetail;
import xiaozhi.common.utils.Result;
import xiaozhi.modules.agent.entity.AgentEntity;
import xiaozhi.modules.agent.service.AgentService;
import xiaozhi.modules.agent.service.AgentWakeWordService;
import xiaozhi.modules.security.user.SecurityUser;

/**
 * 唤醒词管理
 *
 * @author xiaozhi
 */
@Tag(name = "唤醒词管理")
@RequiredArgsConstructor
@RestController
@RequestMapping("/agent/wake-word")
public class WakeWordController {

    private static final int MAX_WAKE_WORDS = 10;
    private static final int MAX_WAKE_WORD_LENGTH = 30;

    private final AgentService agentService;
    private final AgentWakeWordService agentWakeWordService;

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

        // TODO: 推送配置给在线设备（需引入 ConnectionManager）
        // connectionManager.pushWakeWordToAgent(agentId, wakeWords);

        return new Result<Void>().ok(null);
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

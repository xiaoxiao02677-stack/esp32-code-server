package xiaozhi.modules.sys.controller;

import java.util.Map;

import org.apache.shiro.authz.annotation.RequiresPermissions;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.Parameter;
import io.swagger.v3.oas.annotations.tags.Tag;
import lombok.AllArgsConstructor;
import xiaozhi.common.utils.Result;
import xiaozhi.modules.security.user.SecurityUser;
import xiaozhi.modules.sys.service.UserDefaultService;

/**
 * 默认模型/音色配置（管理端 + 用户端生效查询）
 */
@AllArgsConstructor
@RestController
@Tag(name = "默认配置")
public class SysUserDefaultController {
    private final UserDefaultService userDefaultService;

    @GetMapping("/admin/user-default")
    @Operation(summary = "查询某 scope 的默认配置")
    @RequiresPermissions("admin:default:config")
    public Result<Map<String, Object>> getConfig(
            @Parameter(description = "作用域 0平台/1角色/2用户") @RequestParam Integer scopeType,
            @Parameter(description = "角色ID（scopeType=1 必填）") @RequestParam(required = false) Long roleId,
            @Parameter(description = "用户ID（scopeType=2 必填）") @RequestParam(required = false) Long userId) {
        Map<String, Object> data = userDefaultService.getConfig(scopeType, roleId, userId);
        return new Result<Map<String, Object>>().ok(data);
    }

    @PutMapping("/admin/user-default")
    @Operation(summary = "upsert 默认配置（模型/音色 id 校验存在且启用）")
    @RequiresPermissions("admin:default:config")
    public Result<Void> saveConfig(@RequestBody Map<String, Object> body) {
        Integer scopeType = body.get("scopeType") == null ? null : Integer.valueOf(String.valueOf(body.get("scopeType")));
        Long roleId = body.get("roleId") == null ? null : Long.valueOf(String.valueOf(body.get("roleId")));
        Long userId = body.get("userId") == null ? null : Long.valueOf(String.valueOf(body.get("userId")));
        String llmModelId = body.get("llmModelId") == null ? null : String.valueOf(body.get("llmModelId"));
        String ttsModelId = body.get("ttsModelId") == null ? null : String.valueOf(body.get("ttsModelId"));
        String ttsVoiceId = body.get("ttsVoiceId") == null ? null : String.valueOf(body.get("ttsVoiceId"));
        String asrModelId = body.get("asrModelId") == null ? null : String.valueOf(body.get("asrModelId"));
        String paramJson = body.get("paramJson") == null ? null
                : (body.get("paramJson") instanceof String ? String.valueOf(body.get("paramJson"))
                        : xiaozhi.common.utils.JsonUtils.toJsonString(body.get("paramJson")));
        Integer lockPolicy = body.get("lockPolicy") == null ? null
                : Integer.valueOf(String.valueOf(body.get("lockPolicy")));

        userDefaultService.saveConfig(scopeType, roleId, userId, llmModelId, ttsModelId, ttsVoiceId,
                asrModelId, paramJson, lockPolicy);
        return new Result<>();
    }

    @GetMapping("/user/defaults")
    @Operation(summary = "用户端生效默认配置（用户>角色>平台，带 lockPolicy）")
    public Result<Map<String, Object>> myDefaults() {
        Long userId = SecurityUser.getUserId();
        Map<String, Object> data = userDefaultService.getEffectiveForUser(userId);
        return new Result<Map<String, Object>>().ok(data);
    }
}

package xiaozhi.modules.sys.controller;

import java.util.Map;

import org.apache.shiro.authz.annotation.RequiresPermissions;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.Parameter;
import io.swagger.v3.oas.annotations.tags.Tag;
import lombok.AllArgsConstructor;
import xiaozhi.common.utils.Result;
import xiaozhi.modules.sys.service.DisplayConfigService;

/**
 * 展示项配置（管理端 + 用户端生效查询）
 */
@AllArgsConstructor
@RestController
@Tag(name = "展示项配置")
public class SysDisplayConfigController {
    private final DisplayConfigService displayConfigService;

    @GetMapping("/admin/display-config")
    @Operation(summary = "查询某 scope 的展示配置")
    @RequiresPermissions("admin:display:config")
    public Result<Map<String, Object>> getConfig(
            @Parameter(description = "作用域 0系统/1角色/2用户") @RequestParam Integer scopeType,
            @Parameter(description = "角色ID（scopeType=1 必填）") @RequestParam(required = false) Long roleId,
            @Parameter(description = "用户ID（scopeType=2 必填）") @RequestParam(required = false) Long userId) {
        Map<String, Object> data = displayConfigService.getConfig(scopeType, roleId, userId);
        return new Result<Map<String, Object>>().ok(data);
    }

    @PutMapping("/admin/display-config")
    @Operation(summary = "upsert 展示配置")
    @RequiresPermissions("admin:display:config")
    public Result<Void> saveConfig(@RequestBody Map<String, Object> body) {
        Integer scopeType = body.get("scopeType") == null ? null : Integer.valueOf(String.valueOf(body.get("scopeType")));
        Long roleId = body.get("roleId") == null ? null : Long.valueOf(String.valueOf(body.get("roleId")));
        Long userId = body.get("userId") == null ? null : Long.valueOf(String.valueOf(body.get("userId")));
        String configJson = body.get("configJson") == null ? null
                : (body.get("configJson") instanceof String ? String.valueOf(body.get("configJson"))
                        : xiaozhi.common.utils.JsonUtils.toJsonString(body.get("configJson")));
        displayConfigService.saveConfig(scopeType, roleId, userId, configJson);
        return new Result<>();
    }

    @GetMapping("/user/display-config")
    @Operation(summary = "用户端生效展示配置（用户>角色>系统合并）")
    public Result<Map<String, Object>> myDisplayConfig() {
        Long userId = xiaozhi.modules.security.user.SecurityUser.getUserId();
        Map<String, Object> data = displayConfigService.getEffectiveForUser(userId);
        return new Result<Map<String, Object>>().ok(data);
    }
}

package yuhe.modules.sys.controller;

import java.util.Map;

import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.Parameter;
import io.swagger.v3.oas.annotations.Parameters;
import io.swagger.v3.oas.annotations.tags.Tag;

import yuhe.common.constant.Constant;
import yuhe.common.page.PageData;
import yuhe.common.utils.Result;
import yuhe.modules.sys.service.UserResourceService;

/**
 * 用户端资源（console-v2 顾客端）：平台音色聚合 + 本人自定义模型/音色 CRUD。
 * 登录即可访问（oauth2），无 @RequiresPermissions —— 自定义资源仅本人可见可改。
 */
@RestController
@RequestMapping("/user")
@Tag(name = "用户端资源")
public class UserResourceController {

    private final UserResourceService userResourceService;

    public UserResourceController(UserResourceService userResourceService) {
        this.userResourceService = userResourceService;
    }

    // ==================== 资源聚合 ====================

    @GetMapping("/resources")
    @Operation(summary = "我的可用资源（平台全部音色 + 本人审核通过的自定义音色）")
    public Result<Map<String, Object>> myResources() {
        return new Result<Map<String, Object>>().ok(userResourceService.myResources());
    }

    // ==================== 自定义模型 ====================

    @GetMapping("/custom-models")
    @Operation(summary = "我的自定义模型分页（apiKey 仅回掩码）")
    @Parameters({
            @Parameter(name = Constant.PAGE, description = "当前页码，从1开始", required = true),
            @Parameter(name = Constant.LIMIT, description = "每页显示记录数", required = true),
    })
    public Result<PageData<Map<String, Object>>> customModelPage(
            @Parameter(hidden = true) @RequestParam Map<String, Object> params) {
        return new Result<PageData<Map<String, Object>>>().ok(userResourceService.customModelPage(params));
    }

    @PostMapping("/custom-models")
    @Operation(summary = "新建自定义模型（apiKey AES 加密落库，审核通过前不可用）")
    public Result<Map<String, Object>> customModelCreate(@RequestBody Map<String, Object> body) {
        return new Result<Map<String, Object>>().ok(userResourceService.customModelCreate(body));
    }

    @PutMapping("/custom-models/{id}")
    @Operation(summary = "编辑自定义模型（apiKey 留空 = 不修改）")
    public Result<Map<String, Object>> customModelUpdate(@PathVariable String id,
            @RequestBody Map<String, Object> body) {
        return new Result<Map<String, Object>>().ok(userResourceService.customModelUpdate(id, body));
    }

    @DeleteMapping("/custom-models/{id}")
    @Operation(summary = "删除自定义模型")
    public Result<Void> customModelDelete(@PathVariable String id) {
        userResourceService.customModelDelete(id);
        return new Result<Void>();
    }

    @PostMapping("/custom-models/{id}/health")
    @Operation(summary = "连通性探测（GET baseUrl，8s 超时；返回 status/latencyMs/msg）")
    public Result<Map<String, Object>> customModelHealth(@PathVariable String id) {
        return new Result<Map<String, Object>>().ok(userResourceService.customModelHealth(id));
    }

    // ==================== 自定义音色 ====================

    @GetMapping("/custom-voices")
    @Operation(summary = "我的自定义音色分页")
    @Parameters({
            @Parameter(name = Constant.PAGE, description = "当前页码，从1开始", required = true),
            @Parameter(name = Constant.LIMIT, description = "每页显示记录数", required = true),
    })
    public Result<PageData<Map<String, Object>>> customVoicePage(
            @Parameter(hidden = true) @RequestParam Map<String, Object> params) {
        return new Result<PageData<Map<String, Object>>>().ok(userResourceService.customVoicePage(params));
    }

    @PostMapping("/custom-voices")
    @Operation(summary = "新建自定义音色（需管理员审核）")
    public Result<Map<String, Object>> customVoiceCreate(@RequestBody Map<String, Object> body) {
        return new Result<Map<String, Object>>().ok(userResourceService.customVoiceCreate(body));
    }

    @PutMapping("/custom-voices/{id}")
    @Operation(summary = "编辑自定义音色")
    public Result<Map<String, Object>> customVoiceUpdate(@PathVariable String id, @RequestBody Map<String, Object> body) {
        return new Result<Map<String, Object>>().ok(userResourceService.customVoiceUpdate(id, body));
    }

    @DeleteMapping("/custom-voices/{id}")
    @Operation(summary = "删除自定义音色")
    public Result<Void> customVoiceDelete(@PathVariable String id) {
        userResourceService.customVoiceDelete(id);
        return new Result<Void>();
    }
}

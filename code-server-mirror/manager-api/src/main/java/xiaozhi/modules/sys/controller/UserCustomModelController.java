package xiaozhi.modules.sys.controller;

import java.util.List;
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
import io.swagger.v3.oas.annotations.tags.Tag;
import lombok.AllArgsConstructor;
import xiaozhi.common.utils.Result;
import xiaozhi.modules.security.user.SecurityUser;
import xiaozhi.modules.sys.service.UserCustomModelService;

/**
 * 用户自定义模型（用户端，数据自动按当前用户过滤）
 */
@AllArgsConstructor
@RestController
@RequestMapping("/user/custom-models")
@Tag(name = "用户自定义模型")
public class UserCustomModelController {
    private final UserCustomModelService userCustomModelService;

    @GetMapping
    @Operation(summary = "本人自定义模型列表（apiKey 永远掩码）")
    public Result<List<Map<String, Object>>> list(
            @Parameter(description = "模型类型（LLM/ASR/TTS/VAD/Memory）") @RequestParam(required = false) String modelType,
            @Parameter(description = "审核状态（0待审 1通过 2驳回）") @RequestParam(required = false) Integer auditStatus) {
        Long userId = SecurityUser.getUserId();
        List<Map<String, Object>> list = userCustomModelService.myList(userId, modelType, auditStatus);
        return new Result<List<Map<String, Object>>>().ok(list);
    }

    @PostMapping
    @Operation(summary = "新建自定义模型（apiKey AES 加密存储）")
    public Result<Void> create(@RequestBody Map<String, Object> body) {
        Long userId = SecurityUser.getUserId();
        userCustomModelService.create(userId, body);
        return new Result<>();
    }

    @PutMapping("/{id}")
    @Operation(summary = "更新自定义模型（apiKey 空串/不传=不改）")
    public Result<Void> update(@PathVariable String id, @RequestBody Map<String, Object> body) {
        Long userId = SecurityUser.getUserId();
        userCustomModelService.update(userId, id, body);
        return new Result<>();
    }

    @DeleteMapping("/{id}")
    @Operation(summary = "删除自定义模型（仅本人）")
    public Result<Void> delete(@PathVariable String id) {
        Long userId = SecurityUser.getUserId();
        userCustomModelService.delete(userId, id);
        return new Result<>();
    }

    @PostMapping("/{id}/health")
    @Operation(summary = "健康检查（baseUrl HTTP GET 10s 超时）")
    public Result<Map<String, Object>> health(@PathVariable String id) {
        Long userId = SecurityUser.getUserId();
        Map<String, Object> result = userCustomModelService.health(userId, id);
        return new Result<Map<String, Object>>().ok(result);
    }
}

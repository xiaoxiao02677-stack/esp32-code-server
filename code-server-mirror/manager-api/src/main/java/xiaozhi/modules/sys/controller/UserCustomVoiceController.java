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
import xiaozhi.modules.sys.service.UserCustomVoiceService;

/**
 * 用户自定义音色（用户端，数据自动按当前用户过滤）
 */
@AllArgsConstructor
@RestController
@RequestMapping("/user/custom-voices")
@Tag(name = "用户自定义音色")
public class UserCustomVoiceController {
    private final UserCustomVoiceService userCustomVoiceService;

    @GetMapping
    @Operation(summary = "本人自定义音色列表")
    public Result<List<Map<String, Object>>> list(
            @Parameter(description = "审核状态（0待审 1通过 2驳回）") @RequestParam(required = false) Integer auditStatus) {
        Long userId = SecurityUser.getUserId();
        List<Map<String, Object>> list = userCustomVoiceService.myList(userId, auditStatus);
        return new Result<List<Map<String, Object>>>().ok(list);
    }

    @PostMapping
    @Operation(summary = "新建自定义音色")
    public Result<Void> create(@RequestBody Map<String, Object> body) {
        Long userId = SecurityUser.getUserId();
        userCustomVoiceService.create(userId, body);
        return new Result<>();
    }

    @PutMapping("/{id}")
    @Operation(summary = "更新自定义音色（仅本人）")
    public Result<Void> update(@PathVariable String id, @RequestBody Map<String, Object> body) {
        Long userId = SecurityUser.getUserId();
        userCustomVoiceService.update(userId, id, body);
        return new Result<>();
    }

    @DeleteMapping("/{id}")
    @Operation(summary = "删除自定义音色（仅本人）")
    public Result<Void> delete(@PathVariable String id) {
        Long userId = SecurityUser.getUserId();
        userCustomVoiceService.delete(userId, id);
        return new Result<>();
    }
}

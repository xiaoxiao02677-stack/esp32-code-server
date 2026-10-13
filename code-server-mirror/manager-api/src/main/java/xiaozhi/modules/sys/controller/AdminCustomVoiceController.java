package xiaozhi.modules.sys.controller;

import java.util.Map;

import org.apache.shiro.authz.annotation.RequiresPermissions;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.Parameter;
import io.swagger.v3.oas.annotations.Parameters;
import io.swagger.v3.oas.annotations.tags.Tag;
import lombok.AllArgsConstructor;
import xiaozhi.common.constant.Constant;
import xiaozhi.common.utils.Result;
import xiaozhi.modules.sys.service.UserCustomVoiceService;

/**
 * 自定义音色审核（管理端）
 */
@AllArgsConstructor
@RestController
@RequestMapping("/admin/custom-voices")
@Tag(name = "自定义音色审核")
public class AdminCustomVoiceController {
    private final UserCustomVoiceService userCustomVoiceService;

    @GetMapping("/page")
    @Operation(summary = "分页查询自定义音色")
    @RequiresPermissions("admin:custom:audit")
    @Parameters({
            @Parameter(name = "auditStatus", description = "审核状态（0待审 1通过 2驳回）", required = false),
            @Parameter(name = "keyword", description = "名称关键字", required = false),
            @Parameter(name = Constant.PAGE, description = "当前页码，从1开始", required = true),
            @Parameter(name = Constant.LIMIT, description = "每页显示记录数", required = true),
    })
    public Result<Map<String, Object>> page(
            @RequestParam(required = false) Integer auditStatus,
            @RequestParam(required = false) String keyword,
            @RequestParam(defaultValue = "1") long page,
            @RequestParam(defaultValue = "10") long limit) {
        Map<String, Object> data = userCustomVoiceService.adminPage(auditStatus, keyword, page, limit);
        return new Result<Map<String, Object>>().ok(data);
    }

    @PostMapping("/audit")
    @Operation(summary = "审核（通过→1 驳回→2）")
    @RequiresPermissions("admin:custom:audit")
    public Result<Void> audit(@RequestBody Map<String, Object> body) {
        String id = body.get("id") == null ? null : String.valueOf(body.get("id"));
        Boolean pass = body.get("pass") == null ? null : Boolean.valueOf(String.valueOf(body.get("pass")));
        String remark = body.get("remark") == null ? null : String.valueOf(body.get("remark"));
        if (id == null || pass == null) {
            return new Result<Void>().error(10001, "id/pass 不能为空");
        }
        userCustomVoiceService.audit(id, pass, remark);
        return new Result<>();
    }
}

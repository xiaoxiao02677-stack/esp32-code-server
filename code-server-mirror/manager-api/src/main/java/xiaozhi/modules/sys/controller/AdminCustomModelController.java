package xiaozhi.modules.sys.controller;

import java.util.Map;

import org.apache.shiro.authz.annotation.RequiresPermissions;
import org.springframework.web.bind.annotation.GetMapping;
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
import lombok.AllArgsConstructor;
import xiaozhi.common.constant.Constant;
import xiaozhi.common.utils.Result;
import xiaozhi.modules.sys.service.UserCustomModelService;

/**
 * 自定义模型审核（管理端）
 */
@AllArgsConstructor
@RestController
@RequestMapping("/admin/custom-models")
@Tag(name = "自定义模型审核")
public class AdminCustomModelController {
    private final UserCustomModelService userCustomModelService;

    @GetMapping("/page")
    @Operation(summary = "分页查询自定义模型")
    @RequiresPermissions("admin:custom:audit")
    @Parameters({
            @Parameter(name = "auditStatus", description = "审核状态（0待审 1通过 2驳回）", required = false),
            @Parameter(name = "modelType", description = "模型类型", required = false),
            @Parameter(name = "keyword", description = "名称/供应器关键字", required = false),
            @Parameter(name = Constant.PAGE, description = "当前页码，从1开始", required = true),
            @Parameter(name = Constant.LIMIT, description = "每页显示记录数", required = true),
    })
    public Result<Map<String, Object>> page(
            @RequestParam(required = false) Integer auditStatus,
            @RequestParam(required = false) String modelType,
            @RequestParam(required = false) String keyword,
            @RequestParam(defaultValue = "1") long page,
            @RequestParam(defaultValue = "10") long limit) {
        Map<String, Object> data = userCustomModelService.adminPage(auditStatus, modelType, keyword, page, limit);
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
        userCustomModelService.audit(id, pass, remark);
        return new Result<>();
    }

    @PutMapping("/quota")
    @Operation(summary = "设置配额（null=不限）")
    @RequiresPermissions("admin:custom:audit")
    public Result<Void> quota(@RequestBody Map<String, Object> body) {
        String id = body.get("id") == null ? null : String.valueOf(body.get("id"));
        Integer quotaLimit = body.get("quotaLimit") == null || "null".equals(String.valueOf(body.get("quotaLimit")))
                ? null : Integer.valueOf(String.valueOf(body.get("quotaLimit")));
        if (id == null) {
            return new Result<Void>().error(10001, "id 不能为空");
        }
        userCustomModelService.setQuota(id, quotaLimit);
        return new Result<>();
    }
}

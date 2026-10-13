package xiaozhi.modules.sys.controller;

import java.util.List;
import java.util.Map;

import org.apache.shiro.authz.annotation.RequiresPermissions;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.Parameter;
import io.swagger.v3.oas.annotations.Parameters;
import io.swagger.v3.oas.annotations.tags.Tag;
import lombok.AllArgsConstructor;
import xiaozhi.common.constant.Constant;
import xiaozhi.common.page.PageData;
import xiaozhi.common.utils.Result;
import xiaozhi.modules.sys.service.SysAuditLogService;
import xiaozhi.modules.sys.vo.SysAuditLogVO;

/**
 * 审计日志查询（追加只写，无更新/删除端点）
 */
@AllArgsConstructor
@RestController
@RequestMapping("/admin/audit")
@Tag(name = "审计日志")
public class SysAuditLogController {
    private final SysAuditLogService sysAuditLogService;

    @GetMapping("/page")
    @Operation(summary = "分页查询审计日志")
    @RequiresPermissions("admin:audit:list")
    @Parameters({
            @Parameter(name = "userId", description = "操作人ID", required = false),
            @Parameter(name = "module", description = "模块（user/role/custom/security）", required = false),
            @Parameter(name = "operation", description = "操作类型", required = false),
            @Parameter(name = "startDate", description = "起始日期 yyyy-MM-dd", required = false),
            @Parameter(name = "endDate", description = "结束日期 yyyy-MM-dd", required = false),
            @Parameter(name = Constant.PAGE, description = "当前页码，从1开始", required = true),
            @Parameter(name = Constant.LIMIT, description = "每页显示记录数", required = true),
    })
    public Result<PageData<SysAuditLogVO>> page(
            @Parameter(hidden = true) @RequestParam Map<String, Object> params) {
        PageData<SysAuditLogVO> page = sysAuditLogService.page(params);
        return new Result<PageData<SysAuditLogVO>>().ok(page);
    }

    @GetMapping("/modules")
    @Operation(summary = "去重模块列表（筛选用）")
    @RequiresPermissions("admin:audit:list")
    public Result<List<String>> modules() {
        List<String> modules = sysAuditLogService.listModules();
        return new Result<List<String>>().ok(modules);
    }
}

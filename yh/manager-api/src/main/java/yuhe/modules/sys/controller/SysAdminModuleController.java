package yuhe.modules.sys.controller;

import java.util.List;
import java.util.Map;

import org.apache.shiro.authz.annotation.RequiresPermissions;
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
import lombok.AllArgsConstructor;
import yuhe.common.constant.Constant;
import yuhe.common.page.PageData;
import yuhe.common.utils.Result;
import yuhe.modules.sys.dto.AdminCustomAuditDTO;
import yuhe.modules.sys.dto.AdminCustomQuotaDTO;
import yuhe.modules.sys.dto.SysDisplayConfigSaveDTO;
import yuhe.modules.sys.dto.SysRoleSaveDTO;
import yuhe.modules.sys.dto.SysUserDefaultSaveDTO;
import yuhe.modules.sys.service.SysAdminModuleService;
import yuhe.modules.sys.vo.AdminAuditLogVO;
import yuhe.modules.sys.vo.AdminCustomModelVO;
import yuhe.modules.sys.vo.AdminCustomVoiceVO;
import yuhe.modules.sys.vo.AdminRoleVO;

/**
 * 管理端扩展模块控制层（console-v2 五页面契约，SPEC §4）
 * 角色 / 审计日志 / 展示配置 / 默认配置 / 自定义审核
 */
@AllArgsConstructor
@RestController
@RequestMapping("/admin")
@Tag(name = "管理端扩展模块")
public class SysAdminModuleController {

    private final SysAdminModuleService sysAdminModuleService;

    // ==================== 角色（SPEC §4.1） ====================

    @GetMapping("/role/page")
    @Operation(summary = "角色分页（console-v2 Roles.vue）")
    @RequiresPermissions("sys:role:superAdmin")
    @Parameters({
            @Parameter(name = "keyword", description = "角色编码/名称关键词", required = false),
            @Parameter(name = Constant.PAGE, description = "当前页码，从1开始", required = true),
            @Parameter(name = Constant.LIMIT, description = "每页显示记录数", required = true),
    })
    public Result<PageData<AdminRoleVO>> rolePage(
            @Parameter(hidden = true) @RequestParam Map<String, Object> params) {
        return new Result<PageData<AdminRoleVO>>().ok(sysAdminModuleService.rolePage(params));
    }

    @GetMapping("/role/{id}")
    @Operation(summary = "角色详情（permissions 数组）")
    @RequiresPermissions("sys:role:superAdmin")
    public Result<AdminRoleVO> roleDetail(@PathVariable Long id) {
        return new Result<AdminRoleVO>().ok(sysAdminModuleService.roleDetail(id));
    }

    @PostMapping("/role/save")
    @Operation(summary = "新增角色（permissions 数组）")
    @RequiresPermissions("sys:role:superAdmin")
    public Result<Void> roleSave(@RequestBody SysRoleSaveDTO dto) {
        sysAdminModuleService.roleSave(dto);
        return new Result<Void>();
    }

    @PutMapping("/role/update")
    @Operation(summary = "更新角色（内置角色允许改 permissions/remark）")
    @RequiresPermissions("sys:role:superAdmin")
    public Result<Void> roleUpdate(@RequestBody SysRoleSaveDTO dto) {
        sysAdminModuleService.roleUpdate(dto);
        return new Result<Void>();
    }

    @PostMapping("/role/delete")
    @Operation(summary = "批量删除角色（内置拒删 10233、有用户拒删 10234）")
    @RequiresPermissions("sys:role:superAdmin")
    public Result<Void> roleDelete(@RequestBody List<Long> ids) {
        sysAdminModuleService.roleDelete(ids);
        return new Result<Void>();
    }

    // ==================== 审计日志（SPEC §4.5） ====================

    @GetMapping("/audit/page")
    @Operation(summary = "审计日志分页（DB created_at → createdDate）")
    @RequiresPermissions("sys:role:superAdmin")
    @Parameters({
            @Parameter(name = "userId", description = "用户ID", required = false),
            @Parameter(name = "module", description = "模块名", required = false),
            @Parameter(name = "operation", description = "操作名", required = false),
            @Parameter(name = "startDate", description = "起始日期 yyyy-MM-dd", required = false),
            @Parameter(name = "endDate", description = "结束日期 yyyy-MM-dd", required = false),
            @Parameter(name = Constant.PAGE, description = "当前页码，从1开始", required = true),
            @Parameter(name = Constant.LIMIT, description = "每页显示记录数", required = true),
    })
    public Result<PageData<AdminAuditLogVO>> auditPage(
            @Parameter(hidden = true) @RequestParam Map<String, Object> params) {
        return new Result<PageData<AdminAuditLogVO>>().ok(sysAdminModuleService.auditPage(params));
    }

    @GetMapping("/audit/modules")
    @Operation(summary = "审计模块名去重列表（下拉）")
    @RequiresPermissions("sys:role:superAdmin")
    public Result<List<String>> auditModules() {
        return new Result<List<String>>().ok(sysAdminModuleService.auditModules());
    }

    // ==================== 展示配置（SPEC §4.3） ====================

    @GetMapping("/display-config")
    @Operation(summary = "查字段展示配置（无行返回空 fields）")
    @RequiresPermissions("sys:role:superAdmin")
    @Parameters({
            @Parameter(name = "scopeType", description = "0系统 1角色 2用户", required = true),
            @Parameter(name = "roleId", description = "scopeType=1 必填", required = false),
            @Parameter(name = "userId", description = "scopeType=2 必填", required = false),
    })
    public Result<Map<String, Object>> displayConfigGet(
            @RequestParam Integer scopeType,
            @RequestParam(required = false) Long roleId,
            @RequestParam(required = false) Long userId) {
        return new Result<Map<String, Object>>().ok(sysAdminModuleService.displayConfigGet(scopeType, roleId, userId));
    }

    @PutMapping("/display-config")
    @Operation(summary = "保存字段展示配置（upsert；10230 作用域校验）")
    @RequiresPermissions("sys:role:superAdmin")
    public Result<Void> displayConfigSave(@RequestBody SysDisplayConfigSaveDTO dto) {
        sysAdminModuleService.displayConfigSave(dto);
        return new Result<Void>();
    }

    // ==================== 默认配置（SPEC §4.3） ====================

    @GetMapping("/user-default")
    @Operation(summary = "查默认模型配置（无行返回空对象）")
    @RequiresPermissions("sys:role:superAdmin")
    @Parameters({
            @Parameter(name = "scopeType", description = "0系统 1角色 2用户", required = true),
            @Parameter(name = "roleId", description = "scopeType=1 必填", required = false),
            @Parameter(name = "userId", description = "scopeType=2 必填", required = false),
    })
    public Result<Map<String, Object>> userDefaultGet(
            @RequestParam Integer scopeType,
            @RequestParam(required = false) Long roleId,
            @RequestParam(required = false) Long userId) {
        return new Result<Map<String, Object>>().ok(sysAdminModuleService.userDefaultGet(scopeType, roleId, userId));
    }

    @PutMapping("/user-default")
    @Operation(summary = "保存默认模型配置（upsert；null 字段显式落库表示清除）")
    @RequiresPermissions("sys:role:superAdmin")
    public Result<Void> userDefaultSave(@RequestBody SysUserDefaultSaveDTO dto) {
        sysAdminModuleService.userDefaultSave(dto);
        return new Result<Void>();
    }

    // ==================== 自定义审核（SPEC §4.4） ====================

    @GetMapping("/custom-models/page")
    @Operation(summary = "自定义模型审核分页（含 username/apiKeyMasked）")
    @RequiresPermissions("sys:role:superAdmin")
    @Parameters({
            @Parameter(name = "auditStatus", description = "0待审 1过 2驳", required = false),
            @Parameter(name = "keyword", description = "模型名/用户名/供应器", required = false),
            @Parameter(name = Constant.PAGE, description = "当前页码，从1开始", required = true),
            @Parameter(name = Constant.LIMIT, description = "每页显示记录数", required = true),
    })
    public Result<PageData<AdminCustomModelVO>> customModelPage(
            @Parameter(hidden = true) @RequestParam Map<String, Object> params) {
        return new Result<PageData<AdminCustomModelVO>>().ok(sysAdminModuleService.customModelPage(params));
    }

    @PostMapping("/custom-models/audit")
    @Operation(summary = "模型审核（驳回必须 remark 10236）")
    @RequiresPermissions("sys:role:superAdmin")
    public Result<Void> customModelAudit(@RequestBody AdminCustomAuditDTO dto) {
        sysAdminModuleService.customModelAudit(dto);
        return new Result<Void>();
    }

    @PutMapping("/custom-models/quota")
    @Operation(summary = "模型配额（quotaLimit=null 不限）")
    @RequiresPermissions("sys:role:superAdmin")
    public Result<Void> customModelQuota(@RequestBody AdminCustomQuotaDTO dto) {
        sysAdminModuleService.customModelQuota(dto);
        return new Result<Void>();
    }

    @GetMapping("/custom-voices/page")
    @Operation(summary = "自定义音色审核分页（含 username）")
    @RequiresPermissions("sys:role:superAdmin")
    @Parameters({
            @Parameter(name = "auditStatus", description = "0待审 1过 2驳", required = false),
            @Parameter(name = "keyword", description = "音色名/用户名", required = false),
            @Parameter(name = Constant.PAGE, description = "当前页码，从1开始", required = true),
            @Parameter(name = Constant.LIMIT, description = "每页显示记录数", required = true),
    })
    public Result<PageData<AdminCustomVoiceVO>> customVoicePage(
            @Parameter(hidden = true) @RequestParam Map<String, Object> params) {
        return new Result<PageData<AdminCustomVoiceVO>>().ok(sysAdminModuleService.customVoicePage(params));
    }

    @PostMapping("/custom-voices/audit")
    @Operation(summary = "音色审核（驳回必须 remark 10236）")
    @RequiresPermissions("sys:role:superAdmin")
    public Result<Void> customVoiceAudit(@RequestBody AdminCustomAuditDTO dto) {
        sysAdminModuleService.customVoiceAudit(dto);
        return new Result<Void>();
    }
}

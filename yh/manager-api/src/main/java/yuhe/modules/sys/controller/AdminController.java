package yuhe.modules.sys.controller;

import java.io.IOException;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

import org.apache.shiro.authz.annotation.RequiresPermissions;
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
import jakarta.servlet.http.HttpServletResponse;
import lombok.AllArgsConstructor;
import yuhe.common.constant.Constant;
import yuhe.common.page.PageData;
import yuhe.common.utils.Result;
import yuhe.common.validator.ValidatorUtils;
import yuhe.modules.device.dto.DevicePageUserDTO;
import yuhe.modules.device.service.DeviceService;
import yuhe.modules.device.vo.UserShowDeviceListVO;
import yuhe.modules.sys.dto.AdminUserCreateDTO;
import yuhe.modules.sys.dto.AdminUserImportItemDTO;
import yuhe.modules.sys.dto.AdminUserRolesDTO;
import yuhe.modules.sys.entity.SysRoleEntity;
import yuhe.modules.sys.service.SysUserService;
import yuhe.modules.sys.vo.AdminSessionVO;
import yuhe.modules.sys.vo.AdminUserDetailVO;
import yuhe.modules.sys.vo.AdminUserListVO;

/**
 * 管理员控制层
 *
 * @author zjy
 * @since 2025-3-25
 */
@AllArgsConstructor
@RestController
@RequestMapping("/admin")
@Tag(name = "管理员管理")
public class AdminController {
    private final SysUserService sysUserService;

    private final DeviceService deviceService;

    @GetMapping("/users")
    @Operation(summary = "分页查找用户（console-v2 Users.vue：keyword 用户名搜索 + deleted 回收站 + roleNames）")
    @RequiresPermissions("sys:role:superAdmin")
    @Parameters({
            @Parameter(name = "keyword", description = "用户名关键词", required = false),
            @Parameter(name = "deleted", description = "0 正常用户 1 回收站", required = false),
            @Parameter(name = Constant.PAGE, description = "当前页码，从1开始", required = true),
            @Parameter(name = Constant.LIMIT, description = "每页显示记录数", required = true),
    })
    public Result<PageData<AdminUserListVO>> pageUser(
            @Parameter(hidden = true) @RequestParam Map<String, Object> params) {
        PageData<AdminUserListVO> page = sysUserService.adminPage(params);
        return new Result<PageData<AdminUserListVO>>().ok(page);
    }

    @PostMapping("/users")
    @Operation(summary = "新增用户（返回初始密码）")
    @RequiresPermissions("sys:role:superAdmin")
    public Result<String> create(@RequestBody AdminUserCreateDTO dto) {
        String password = sysUserService.adminCreate(dto);
        return new Result<String>().ok(password);
    }

    @GetMapping("/users/{id}")
    @Operation(summary = "用户详情（user + 当前角色）")
    @RequiresPermissions("sys:role:superAdmin")
    public Result<AdminUserDetailVO> detail(@PathVariable Long id) {
        return new Result<AdminUserDetailVO>().ok(sysUserService.detail(id));
    }

    @PutMapping("/users/roles")
    @Operation(summary = "分配角色（全量覆盖）")
    @RequiresPermissions("sys:role:superAdmin")
    public Result<Void> assignRoles(@RequestBody AdminUserRolesDTO dto) {
        sysUserService.assignRoles(dto);
        return new Result<Void>();
    }

    @PutMapping("/users/restore/{id}")
    @Operation(summary = "从回收站恢复用户")
    @RequiresPermissions("sys:role:superAdmin")
    public Result<Void> restore(@PathVariable Long id) {
        sysUserService.restore(id);
        return new Result<Void>();
    }

    @PostMapping("/users/import")
    @Operation(summary = "批量导入用户（部分失败 10225 data 携带明细）")
    @RequiresPermissions("sys:role:superAdmin")
    public Result<Map<String, Object>> importUsers(@RequestBody List<AdminUserImportItemDTO> list) {
        Map<String, Object> result = sysUserService.importUsers(list);
        return new Result<Map<String, Object>>().ok(result);
    }

    @GetMapping("/users/export")
    @Operation(summary = "导出用户 CSV")
    @RequiresPermissions("sys:role:superAdmin")
    public void export(HttpServletResponse response,
            @RequestParam(required = false) String keyword,
            @RequestParam(required = false, defaultValue = "0") Integer deleted) throws IOException {
        // 与列表同源数据（不分页，全量导出当前筛选）
        Map<String, Object> params = new HashMap<>();
        params.put("keyword", keyword);
        params.put("deleted", String.valueOf(deleted));
        params.put(Constant.PAGE, "1");
        params.put(Constant.LIMIT, "100000");
        PageData<AdminUserListVO> page = sysUserService.adminPage(params);

        response.setContentType("text/csv;charset=UTF-8");
        String fileTag = deleted == 1 ? "deleted" : "users";
        response.setHeader("Content-Disposition", "attachment; filename=" + fileTag + ".csv");
        // UTF-8 BOM：Excel 直接双击打开不乱码
        java.io.PrintWriter writer = response.getWriter();
        writer.write('\ufeff');
        writer.println("id,用户名,角色,状态,锁定,设备数,最后登录,注册时间");
        for (AdminUserListVO u : page.getList()) {
            writer.printf("%d,%s,%s,%s,%s,%d,%s,%s%n",
                    u.getId(),
                    csv(u.getUsername()),
                    csv(u.getRoleNames() == null ? "" : String.join(" ", u.getRoleNames())),
                    u.getStatus() != null && u.getStatus() == 1 ? "正常" : "停用",
                    u.getLocked() != null && u.getLocked() == 1 ? "锁定" : "—",
                    u.getDeviceCount() == null ? 0 : u.getDeviceCount(),
                    u.getLastLoginDate() == null ? "" : String.valueOf(u.getLastLoginDate()),
                    u.getCreateDate() == null ? "" : String.valueOf(u.getCreateDate()));
        }
        writer.flush();
    }

    @GetMapping("/users/sessions")
    @Operation(summary = "在线会话分页")
    @RequiresPermissions("sys:role:superAdmin")
    public Result<PageData<AdminSessionVO>> sessions(
            @Parameter(hidden = true) @RequestParam Map<String, Object> params) {
        return new Result<PageData<AdminSessionVO>>().ok(sysUserService.pageSessions(params));
    }

    @PostMapping("/users/forceLogout/{id}")
    @Operation(summary = "强制下线（过期该用户全部 token）")
    @RequiresPermissions("sys:role:superAdmin")
    public Result<Void> forceLogout(@PathVariable Long id) {
        sysUserService.forceLogout(id);
        return new Result<Void>();
    }

    @GetMapping("/role/list")
    @Operation(summary = "角色列表（启用角色，用于分配弹窗）")
    @RequiresPermissions("sys:role:superAdmin")
    public Result<List<SysRoleEntity>> roleList() {
        return new Result<List<SysRoleEntity>>().ok(sysUserService.listRoles());
    }

    @PutMapping("/users/{id}")
    @Operation(summary = "重置密码")
    @RequiresPermissions("sys:role:superAdmin")
    public Result<String> update(
            @PathVariable Long id) {
        String password = sysUserService.resetPassword(id);
        return new Result<String>().ok(password);
    }

    @DeleteMapping("/users/{id}")
    @Operation(summary = "用户删除（软删除，回收站可恢复）")
    @RequiresPermissions("sys:role:superAdmin")
    public Result<Void> delete(@PathVariable Long id) {
        // console-v2 Users.vue 契约：软删除（deleted=1），设备/智能体保留，回收站可恢复
        sysUserService.softDelete(id, yuhe.modules.security.user.SecurityUser.getUserId());
        return new Result<>();
    }

    /** CSV 字段转义：含逗号/引号/换行时整体加引号并把内部引号翻倍 */
    private String csv(String v) {
        if (v == null) return "";
        if (v.contains(",") || v.contains("\"") || v.contains("\n")) {
            return "\"" + v.replace("\"", "\"\"") + "\"";
        }
        return v;
    }

    @PutMapping("/users/changeStatus/{status}")
    @Operation(summary = "批量修改用户状态")
    @RequiresPermissions("sys:role:superAdmin")
    @Parameter(name = "status", description = "用户状态", required = true)
    public Result<Void> changeStatus(@PathVariable Integer status, @RequestBody String[] userIds) {
        sysUserService.changeStatus(status, userIds);
        return new Result<Void>();
    }

    @GetMapping("/device/all")
    @Operation(summary = "分页查找设备")
    @RequiresPermissions("sys:role:superAdmin")
    @Parameters({
            @Parameter(name = "keywords", description = "设备关键词", required = false),
            @Parameter(name = Constant.PAGE, description = "当前页码，从1开始", required = true),
            @Parameter(name = Constant.LIMIT, description = "每页显示记录数", required = true),
    })
    public Result<PageData<UserShowDeviceListVO>> pageDevice(
            @Parameter(hidden = true) @RequestParam Map<String, Object> params) {
        DevicePageUserDTO dto = new DevicePageUserDTO();
        dto.setKeywords((String) params.get("keywords"));
        dto.setLimit((String) params.get(Constant.LIMIT));
        dto.setPage((String) params.get(Constant.PAGE));
        ValidatorUtils.validateEntity(dto);
        PageData<UserShowDeviceListVO> page = deviceService.page(dto);
        return new Result<PageData<UserShowDeviceListVO>>().ok(page);
    }
}

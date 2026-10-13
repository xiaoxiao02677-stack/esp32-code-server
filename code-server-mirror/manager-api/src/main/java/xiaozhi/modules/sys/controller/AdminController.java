package xiaozhi.modules.sys.controller;

import java.io.IOException;
import java.net.URLEncoder;
import java.nio.charset.StandardCharsets;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

import org.apache.shiro.authz.annotation.RequiresPermissions;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
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
import xiaozhi.common.constant.Constant;
import xiaozhi.common.exception.ErrorCode;
import xiaozhi.common.exception.RenException;
import xiaozhi.common.page.PageData;
import xiaozhi.common.utils.Result;
import xiaozhi.common.validator.ValidatorUtils;
import xiaozhi.modules.device.dto.DevicePageUserDTO;
import xiaozhi.modules.device.service.DeviceService;
import xiaozhi.modules.device.vo.UserShowDeviceListVO;
import xiaozhi.modules.sys.dto.AdminPageUserDTO;
import xiaozhi.modules.sys.dto.AdminUserCreateDTO;
import xiaozhi.modules.sys.dto.UserImportDTO;
import xiaozhi.modules.sys.dto.UserRoleAssignDTO;
import xiaozhi.modules.sys.service.SysUserService;
import xiaozhi.modules.sys.vo.AdminPageUserVO;
import xiaozhi.modules.sys.vo.AdminUserDetailVO;
import xiaozhi.modules.sys.vo.AdminUserPageVO;
import xiaozhi.modules.sys.vo.UserImportResultVO;
import xiaozhi.modules.sys.vo.UserSessionVO;

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
    @Operation(summary = "分页查找用户")
    @RequiresPermissions("admin:user:list")
    @Parameters({
            @Parameter(name = "mobile", description = "用户手机号码", required = false),
            @Parameter(name = "keyword", description = "用户名关键字", required = false),
            @Parameter(name = "deleted", description = "0正常 1已删除（默认0）", required = false),
            @Parameter(name = "roleId", description = "角色ID过滤", required = false),
            @Parameter(name = Constant.PAGE, description = "当前页码，从1开始", required = true),
            @Parameter(name = Constant.LIMIT, description = "每页显示记录数", required = true),
    })
    public Result<PageData<AdminUserPageVO>> pageUser(
            @Parameter(hidden = true) @RequestParam Map<String, Object> params) {
        // 兼容旧参数 mobile → keyword
        if (params.get("keyword") == null && params.get("mobile") != null) {
            params.put("keyword", params.get("mobile"));
        }
        PageData<AdminUserPageVO> page = sysUserService.pageUsers(params);
        return new Result<PageData<AdminUserPageVO>>().ok(page);
    }

    @PostMapping("/users")
    @Operation(summary = "新建用户（密码缺省自动生成，mustChangePwd=1）")
    @RequiresPermissions("admin:user:create")
    public Result<String> create(@RequestBody AdminUserCreateDTO dto) {
        ValidatorUtils.validateEntity(dto);
        String password = sysUserService.createUser(dto);
        return new Result<String>().ok(password);
    }

    @GetMapping("/users/{id}")
    @Operation(summary = "用户详情（含角色）")
    @RequiresPermissions("admin:user:list")
    public Result<AdminUserDetailVO> detail(@PathVariable Long id) {
        AdminUserDetailVO vo = sysUserService.getUserDetail(id);
        return new Result<AdminUserDetailVO>().ok(vo);
    }

    @PutMapping("/users/roles")
    @Operation(summary = "分配用户角色")
    @RequiresPermissions("admin:user:assign")
    public Result<Void> assignRoles(@RequestBody UserRoleAssignDTO dto) {
        ValidatorUtils.validateEntity(dto);
        sysUserService.assignRoles(dto.getUserId(), dto.getRoleIds());
        return new Result<>();
    }

    @PutMapping("/users/restore/{id}")
    @Operation(summary = "恢复软删除用户")
    @RequiresPermissions("admin:user:delete")
    public Result<Void> restore(@PathVariable Long id) {
        sysUserService.restore(id);
        return new Result<>();
    }

    @PutMapping("/users/{id}")
    @Operation(summary = "重置密码（mustChangePwd=1）")
    @RequiresPermissions("admin:user:resetPwd")
    public Result<String> update(@PathVariable Long id) {
        String password = sysUserService.resetPassword(id);
        return new Result<String>().ok(password);
    }

    @DeleteMapping("/users/{id}")
    @Operation(summary = "用户软删除（不级联删设备/智能体）")
    @RequiresPermissions("admin:user:delete")
    public Result<Void> delete(@PathVariable Long id) {
        sysUserService.softDelete(id);
        return new Result<>();
    }

    @PutMapping("/users/changeStatus/{status}")
    @Operation(summary = "批量修改用户状态")
    @RequiresPermissions("admin:user:update")
    @Parameter(name = "status", description = "用户状态", required = true)
    public Result<Void> changeStatus(@PathVariable Integer status, @RequestBody String[] userIds) {
        sysUserService.changeStatus(status, userIds);
        return new Result<Void>();
    }

    @PostMapping("/users/import")
    @Operation(summary = "批量导入用户")
    @RequiresPermissions("admin:user:create")
    public Result<UserImportResultVO> importUsers(@RequestBody List<UserImportDTO> list) {
        if (list == null || list.isEmpty()) {
            throw new RenException(ErrorCode.NOT_NULL);
        }
        UserImportResultVO result = sysUserService.importUsers(list);
        if (!result.getFailed().isEmpty()) {
            // 部分失败：code 10225（data 明细无法经 Result 泛型携带时由前端读 msg；
            // 这里仍然返回完整结果，前端按 failed 数组展示）
        }
        return new Result<UserImportResultVO>().ok(result);
    }

    @GetMapping("/users/export")
    @Operation(summary = "导出用户 CSV")
    @RequiresPermissions("admin:user:list")
    @Parameters({
            @Parameter(name = "keyword", description = "用户名关键字", required = false),
            @Parameter(name = "deleted", description = "0正常 1已删除（默认0）", required = false),
    })
    public void export(@RequestParam(required = false) String keyword,
            @RequestParam(required = false) Integer deleted, HttpServletResponse response) throws IOException {
        List<String[]> rows = sysUserService.exportRows(keyword, deleted);

        // CSV BOM 头防 Excel 乱码
        StringBuilder sb = new StringBuilder("\uFEFF");
        for (String[] row : rows) {
            for (int i = 0; i < row.length; i++) {
                if (i > 0) {
                    sb.append(',');
                }
                String cell = row[i] == null ? "" : row[i].replace("\"", "\"\"");
                sb.append('"').append(cell).append('"');
            }
            sb.append("\r\n");
        }

        response.setContentType("text/csv; charset=UTF-8");
        response.setHeader(HttpHeaders.CONTENT_DISPOSITION,
                "attachment; filename=" + URLEncoder.encode("users.csv", StandardCharsets.UTF_8));
        response.getOutputStream().write(sb.toString().getBytes(StandardCharsets.UTF_8));
        response.getOutputStream().flush();
    }

    @GetMapping("/users/sessions")
    @Operation(summary = "在线会话分页")
    @RequiresPermissions("admin:user:list")
    @Parameters({
            @Parameter(name = "keyword", description = "用户名关键字", required = false),
            @Parameter(name = Constant.PAGE, description = "当前页码，从1开始", required = true),
            @Parameter(name = Constant.LIMIT, description = "每页显示记录数", required = true),
    })
    public Result<PageData<UserSessionVO>> sessions(
            @Parameter(hidden = true) @RequestParam Map<String, Object> params) {
        PageData<UserSessionVO> page = sysUserService.pageSessions(params);
        return new Result<PageData<UserSessionVO>>().ok(page);
    }

    @PostMapping("/users/forceLogout/{id}")
    @Operation(summary = "强制下线用户（过期其全部 token）")
    @RequiresPermissions("admin:user:update")
    public Result<Void> forceLogout(@PathVariable Long id) {
        sysUserService.forceLogout(id);
        return new Result<>();
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

package xiaozhi.modules.sys.controller;

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
import xiaozhi.common.constant.Constant;
import xiaozhi.common.page.PageData;
import xiaozhi.common.utils.Result;
import xiaozhi.common.validator.ValidatorUtils;
import xiaozhi.common.validator.group.AddGroup;
import xiaozhi.common.validator.group.DefaultGroup;
import xiaozhi.common.validator.group.UpdateGroup;
import xiaozhi.modules.sys.dto.SysRoleDTO;
import xiaozhi.modules.sys.service.SysRoleService;
import xiaozhi.modules.sys.vo.SysRoleVO;

/**
 * 角色管理
 */
@AllArgsConstructor
@RestController
@RequestMapping("/admin/role")
@Tag(name = "角色管理")
public class SysRoleController {
    private final SysRoleService sysRoleService;

    @GetMapping("/page")
    @Operation(summary = "分页查询角色")
    @RequiresPermissions("admin:role:list")
    @Parameters({ @Parameter(name = "keyword", description = "角色编码/名称关键字"),
            @Parameter(name = Constant.PAGE, description = "当前页码，从1开始", required = true),
            @Parameter(name = Constant.LIMIT, description = "每页显示记录数", required = true) })
    public Result<PageData<SysRoleVO>> page(@Parameter(hidden = true) @RequestParam Map<String, Object> params) {
        PageData<SysRoleVO> page = sysRoleService.page(params);
        return new Result<PageData<SysRoleVO>>().ok(page);
    }

    @GetMapping("/list")
    @Operation(summary = "启用角色下拉列表")
    @RequiresPermissions("admin:role:list")
    public Result<List<SysRoleVO>> list() {
        List<SysRoleVO> list = sysRoleService.listEnabled();
        return new Result<List<SysRoleVO>>().ok(list);
    }

    @GetMapping("/{id}")
    @Operation(summary = "获取角色详情")
    @RequiresPermissions("admin:role:list")
    public Result<SysRoleVO> get(@PathVariable("id") Long id) {
        SysRoleVO vo = sysRoleService.get(id);
        return new Result<SysRoleVO>().ok(vo);
    }

    @PostMapping("/save")
    @Operation(summary = "保存角色")
    @RequiresPermissions("admin:role:save")
    public Result<Void> save(@RequestBody SysRoleDTO dto) {
        ValidatorUtils.validateEntity(dto, AddGroup.class, DefaultGroup.class);
        sysRoleService.save(dto);
        return new Result<>();
    }

    @PutMapping("/update")
    @Operation(summary = "修改角色")
    @RequiresPermissions("admin:role:update")
    public Result<Void> update(@RequestBody SysRoleDTO dto) {
        ValidatorUtils.validateEntity(dto, UpdateGroup.class, DefaultGroup.class);
        sysRoleService.update(dto);
        return new Result<>();
    }

    @PostMapping("/delete")
    @Operation(summary = "删除角色")
    @RequiresPermissions("admin:role:delete")
    @Parameter(name = "ids", description = "ID数组", required = true)
    public Result<Void> delete(@RequestBody Long[] ids) {
        sysRoleService.delete(ids);
        return new Result<>();
    }
}

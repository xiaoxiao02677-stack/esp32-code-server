package yuhe.modules.device.controller;

import java.util.Map;

import org.apache.shiro.authz.annotation.RequiresPermissions;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.Parameter;
import io.swagger.v3.oas.annotations.Parameters;
import io.swagger.v3.oas.annotations.tags.Tag;
import lombok.RequiredArgsConstructor;
import yuhe.common.constant.Constant;
import yuhe.common.page.PageData;
import yuhe.common.utils.Result;
import yuhe.common.validator.ValidatorUtils;
import yuhe.modules.device.entity.DeviceConfigEntity;
import yuhe.modules.device.service.DeviceConfigAdminService;

/**
 * 设备云端配置管理（P1-4：管理后台查看/清库入口）
 * 路由风格对齐同包 OTAMagController（/xxxMag + sys:role:superAdmin）
 */
@Tag(name = "设备云端配置管理", description = "ai_device_config 查看与清理")
@RestController
@RequiredArgsConstructor
@RequestMapping("/deviceConfigMag")
public class DeviceConfigAdminController {
    private final DeviceConfigAdminService deviceConfigAdminService;

    @GetMapping
    @Operation(summary = "分页查询设备云端配置（支持 deviceId 模糊搜索）")
    @Parameters({
            @Parameter(name = Constant.PAGE, description = "当前页码，从1开始", required = true),
            @Parameter(name = Constant.LIMIT, description = "每页显示记录数", required = true)
    })
    @RequiresPermissions("sys:role:superAdmin")
    public Result<PageData<DeviceConfigEntity>> page(@Parameter(hidden = true) @RequestParam Map<String, Object> params) {
        ValidatorUtils.validateEntity(params);
        PageData<DeviceConfigEntity> page = deviceConfigAdminService.page(params);
        return new Result<PageData<DeviceConfigEntity>>().ok(page);
    }

    @GetMapping("/{deviceId}")
    @Operation(summary = "查询单台设备云端配置")
    @RequiresPermissions("sys:role:superAdmin")
    public Result<DeviceConfigEntity> get(@PathVariable("deviceId") String deviceId) {
        return new Result<DeviceConfigEntity>().ok(deviceConfigAdminService.selectById(deviceId));
    }

    @DeleteMapping("/{deviceId}")
    @Operation(summary = "删除单台设备云端配置")
    @RequiresPermissions("sys:role:superAdmin")
    public Result<Void> delete(@PathVariable("deviceId") String deviceId) {
        if (!deviceConfigAdminService.deleteById(deviceId)) {
            return new Result<Void>().error("记录不存在或删除失败: " + deviceId);
        }
        return new Result<Void>();
    }

    @DeleteMapping
    @Operation(summary = "清空全部设备云端配置")
    @RequiresPermissions("sys:role:superAdmin")
    public Result<Integer> deleteAll() {
        int rows = deviceConfigAdminService.deleteAll();
        return new Result<Integer>().ok(rows);
    }
}

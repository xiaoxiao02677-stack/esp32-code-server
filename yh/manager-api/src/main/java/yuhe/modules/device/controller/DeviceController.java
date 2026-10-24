package yuhe.modules.device.controller;

import java.util.List;
import java.util.Map;

import org.apache.commons.lang3.StringUtils;
import org.apache.shiro.authz.annotation.Logical;
import org.apache.shiro.authz.annotation.RequiresPermissions;
import org.springframework.beans.BeanUtils;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import jakarta.validation.Valid;
import yuhe.common.exception.ErrorCode;
import yuhe.common.redis.RedisKeys;
import yuhe.common.redis.RedisUtils;
import yuhe.common.user.UserDetail;
import yuhe.common.utils.Result;
import yuhe.modules.device.dto.DeviceAddressBookAliasDTO;
import yuhe.modules.device.dto.DeviceAddressBookPermissionDTO;
import yuhe.modules.device.dto.DeviceManualAddDTO;
import yuhe.modules.device.dto.DeviceOtaTargetDTO;
import yuhe.modules.device.dto.DeviceRegisterDTO;
import yuhe.modules.device.dto.DeviceToolsCallReqDTO;
import yuhe.modules.device.dto.DeviceUnBindDTO;
import yuhe.modules.device.dto.DeviceUpdateDTO;
import yuhe.modules.device.entity.DeviceEntity;
import yuhe.modules.device.entity.OtaEntity;
import yuhe.modules.device.service.DeviceAddressBookService;
import yuhe.modules.device.service.DeviceService;
import yuhe.modules.device.service.OtaService;
import yuhe.modules.device.vo.UserShowDeviceListVO;
import yuhe.modules.security.user.SecurityUser;
import yuhe.modules.sys.service.SysParamsService;

@Tag(name = "设备管理")
@RestController
@RequestMapping("/device")
public class DeviceController {
    private final DeviceService deviceService;
    private final DeviceAddressBookService deviceAddressBookService;
    private final RedisUtils redisUtils;
    private final SysParamsService sysParamsService;
    private final OtaService otaService;

    public DeviceController(DeviceService deviceService, DeviceAddressBookService deviceAddressBookService,
            RedisUtils redisUtils, SysParamsService sysParamsService, OtaService otaService) {
        this.deviceService = deviceService;
        this.deviceAddressBookService = deviceAddressBookService;
        this.redisUtils = redisUtils;
        this.sysParamsService = sysParamsService;
        this.otaService = otaService;
    }

    @PostMapping("/bind/{agentId}/{deviceCode}")
    @Operation(summary = "绑定设备")
    @RequiresPermissions("sys:role:normal")
    public Result<Void> bindDevice(@PathVariable String agentId, @PathVariable String deviceCode) {
        deviceService.deviceActivation(agentId, deviceCode);
        return new Result<>();
    }

    @PostMapping("/register")
    @Operation(summary = "注册设备")
    public Result<String> registerDevice(@RequestBody DeviceRegisterDTO deviceRegisterDTO) {
        String macAddress = deviceRegisterDTO.getMacAddress();
        if (StringUtils.isBlank(macAddress)) {
            return new Result<String>().error(ErrorCode.MCA_NOT_NULL);
        }
        // 生成六位验证码
        String code;
        String key;
        String existsMac = null;
        do {
            code = String.valueOf(Math.random()).substring(2, 8);
            key = RedisKeys.getDeviceCaptchaKey(code);
            existsMac = (String) redisUtils.get(key);
        } while (StringUtils.isNotBlank(existsMac));

        redisUtils.set(key, macAddress);
        return new Result<String>().ok(code);
    }

    @GetMapping("/bind/{agentId}")
    @Operation(summary = "获取已绑定设备")
    @RequiresPermissions("sys:role:normal")
    public Result<List<UserShowDeviceListVO>> getUserDevices(@PathVariable String agentId) {
        UserDetail user = SecurityUser.getUser();
        List<UserShowDeviceListVO> devices = deviceService.getUserDeviceList(user.getId(), agentId);
        return new Result<List<UserShowDeviceListVO>>().ok(devices);
    }

    @PostMapping("/bind/{agentId}")
    @Operation(summary = "设备在线接口")
    @RequiresPermissions("sys:role:normal")
    public Result<String> forwardToMqttGateway(@PathVariable String agentId, @RequestBody String requestBody) {
        try {
            return new Result<String>().ok(deviceService.getDeviceOnlineData(agentId));
        } catch (Exception e) {
            return new Result<String>().error("转发请求失败: " + e.getMessage());
        }
    }

    @PostMapping("/unbind")
    @Operation(summary = "解绑设备")
    @RequiresPermissions("sys:role:normal")
    public Result<Void> unbindDevice(@RequestBody DeviceUnBindDTO unDeviveBind) {
        UserDetail user = SecurityUser.getUser();
        deviceService.unbindDevice(user, unDeviveBind.getDeviceId());
        return new Result<Void>();
    }

    @PutMapping("/update/{id}")
    @Operation(summary = "更新设备信息")
    @RequiresPermissions("sys:role:normal")
    public Result<Void> updateDeviceInfo(@PathVariable String id, @Valid @RequestBody DeviceUpdateDTO deviceUpdateDTO) {
        DeviceEntity entity = deviceService.selectById(id);
        if (entity == null) {
            return new Result<Void>().error("设备不存在");
        }
        UserDetail user = SecurityUser.getUser();
        // 属主 / 超管 / 智能体共享授权用户（共享用户看共享智能体如同自建，可改）
        boolean allowed = entity.getUserId().equals(user.getId())
                || (user.getSuperAdmin() != null && user.getSuperAdmin() == 1)
                || (entity.getAgentId() != null && deviceService.isAgentSharedToUser(entity.getAgentId(), user.getId()));
        if (!allowed) {
            return new Result<Void>().error("设备不存在");
        }
        BeanUtils.copyProperties(deviceUpdateDTO, entity);
        if (!deviceService.updateById(entity)) {
            return new Result<Void>().error(ErrorCode.UPDATE_DATA_FAILED);
        }
        return new Result<Void>();
    }

    @PostMapping("/manual-add")
    @Operation(summary = "手动添加设备")
    @RequiresPermissions("sys:role:normal")
    public Result<Void> manualAddDevice(@RequestBody @Valid DeviceManualAddDTO dto) {
        UserDetail user = SecurityUser.getUser();
        deviceService.manualAddDevice(user.getId(), dto);
        return new Result<>();
    }

    @PutMapping("/ota-target/{id}")
    @Operation(summary = "设置设备 OTA 定向配置（单台指定固件 / 主题轨道）")
    @RequiresPermissions(value = {"sys:role:superAdmin", "admin:devices"}, logical = Logical.OR)
    public Result<Void> setDeviceOtaTarget(@PathVariable String id,
            @Valid @RequestBody DeviceOtaTargetDTO dto) {
        DeviceEntity entity = deviceService.selectById(id);
        if (entity == null) {
            return new Result<Void>().error("设备不存在");
        }
        // 只更新出现的字段：null 跳过（部分更新语义），空串 = 显式清除
        // 注意：MyBatis-Plus updateById 跳过 null 字段，清空必须写空串（DB 落 NULL 靠列语义）
        if (dto.getTargetOtaId() != null) {
            if (dto.getTargetOtaId().isEmpty()) {
                entity.setTargetOtaId("");
            } else {
                // 指定的固件必须真实存在，防止 pin 一个幽灵 id 让设备永远空转
                OtaEntity ota = otaService.selectById(dto.getTargetOtaId());
                if (ota == null) {
                    return new Result<Void>().error("指定的固件记录不存在");
                }
                entity.setTargetOtaId(dto.getTargetOtaId());
            }
        }
        if (dto.getOtaType() != null) {
            // 非空轨道必须已有固件注册，否则轨道无固件可推，切过去就回不来了
            if (dto.getOtaType().isEmpty()) {
                entity.setOtaType("");
            } else {
                if (otaService.getLatestOta(dto.getOtaType()) == null) {
                    return new Result<Void>().error("该主题轨道下没有已注册的固件: " + dto.getOtaType());
                }
                entity.setOtaType(dto.getOtaType());
            }
        }
        if (!deviceService.updateById(entity)) {
            return new Result<Void>().error(ErrorCode.UPDATE_DATA_FAILED);
        }
        return new Result<Void>();
    }

    @PostMapping("/tools/list/{deviceId}")
    @Operation(summary = "获取设备工具列表")
    @RequiresPermissions("sys:role:normal")
    public Result<Object> getDeviceTools(@PathVariable String deviceId) {
        Object toolsData = deviceService.getDeviceTools(deviceId);
        if (toolsData == null) {
            return new Result<Object>().error(ErrorCode.DEVICE_NOT_EXIST);
        }

        return new Result<Object>().ok(toolsData);
    }

    @PostMapping("/tools/call/{deviceId}")
    @Operation(summary = "调用设备工具")
    @RequiresPermissions("sys:role:normal")
    public Result<Object> callDeviceTool(@PathVariable String deviceId,
            @Valid @RequestBody DeviceToolsCallReqDTO request) {
        String toolName = request.getName();
        Map<String, Object> arguments = request.getArguments();

        Object result = deviceService.callDeviceTool(deviceId, toolName, arguments);
        if (result == null) {
            return new Result<Object>().error(ErrorCode.DEVICE_NOT_EXIST);
        }

        Result<Object> response = new Result<Object>();
        response.setMsg("Tools called successfully");
        return response.ok(result);
    }

    @GetMapping("/address-book/{macAddress}")
    @Operation(summary = "获取设备通讯录")
    @RequiresPermissions("sys:role:normal")
    public Result<Object> getAddressBook(@PathVariable String macAddress) {
        return new Result<Object>().ok(deviceAddressBookService.getAddressBookList(macAddress));
    }

    @GetMapping("/address-book/call")
    @Operation(summary = "根据昵称发起呼叫")
    public Result<Map<String, Object>> callByNickname(String callerMac, String nickname,
            @RequestParam(required = false, defaultValue = "false") boolean answer) {
        Map<String, Object> result = deviceAddressBookService.callByNickname(callerMac, nickname, answer);
        if (result == null) {
            return new Result<Map<String, Object>>().error("未找到对应设备");
        }
        return new Result<Map<String, Object>>().ok(result);
    }

    @PutMapping("/address-book/alias")
    @Operation(summary = "更新设备通讯录别名")
    @RequiresPermissions("sys:role:normal")
    public Result<Void> updateAlias(@Valid @RequestBody DeviceAddressBookAliasDTO dto) {
        UserDetail user = SecurityUser.getUser();
        DeviceEntity callerDevice = deviceService.getDeviceByMacAddress(dto.getMacAddress());
        if (callerDevice == null || !callerDevice.getUserId().equals(user.getId())) {
            return new Result<Void>().error("无权限操作该设备");
        }
        deviceAddressBookService.saveOrUpdate(dto.getMacAddress(), dto.getTargetMac(), dto.getAlias(), null);
        return new Result<Void>();
    }

    @PutMapping("/address-book/permission")
    @Operation(summary = "更新设备通讯录权限")
    @RequiresPermissions("sys:role:normal")
    public Result<Void> updatePermission(@Valid @RequestBody DeviceAddressBookPermissionDTO dto) {
        UserDetail user = SecurityUser.getUser();
        DeviceEntity callerDevice = deviceService.getDeviceByMacAddress(dto.getMacAddress());
        if (callerDevice == null || !callerDevice.getUserId().equals(user.getId())) {
            return new Result<Void>().error("无权限操作该设备");
        }
        deviceAddressBookService.saveOrUpdate(dto.getMacAddress(), dto.getTargetMac(), null, dto.getHasPermission());
        return new Result<Void>();
    }
}

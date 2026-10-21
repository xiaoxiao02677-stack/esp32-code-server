package yuhe.modules.device.controller;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.mockStatic;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.mockito.MockedStatic;

import yuhe.common.exception.ErrorCode;
import yuhe.common.redis.RedisUtils;
import yuhe.common.user.UserDetail;
import yuhe.common.utils.MessageUtils;
import yuhe.common.utils.Result;
import yuhe.modules.device.dto.DeviceUpdateDTO;
import yuhe.modules.device.entity.DeviceEntity;
import yuhe.modules.device.service.DeviceAddressBookService;
import yuhe.modules.device.service.DeviceService;
import yuhe.modules.device.service.OtaService;
import yuhe.modules.security.user.SecurityUser;
import yuhe.modules.sys.service.SysParamsService;

@DisplayName("设备更新接口回归测试")
class DeviceControllerTest {

    private static final String DEVICE_ID = "device-id";
    private static final long USER_ID = 1L;

    @Test
    @DisplayName("数据库未更新时不误报自动升级状态修改成功")
    void updateFailureIsReturnedToCaller() {
        DeviceService deviceService = mock(DeviceService.class);
        DeviceEntity entity = ownedDevice();
        when(deviceService.selectById(DEVICE_ID)).thenReturn(entity);
        when(deviceService.updateById(entity)).thenReturn(false);
        DeviceController controller = controller(deviceService);

        DeviceUpdateDTO update = new DeviceUpdateDTO();
        update.setAutoUpdate(0);

        try (MockedStatic<SecurityUser> securityUser = mockStatic(SecurityUser.class);
                MockedStatic<MessageUtils> messageUtils = mockStatic(MessageUtils.class)) {
            securityUser.when(SecurityUser::getUser).thenReturn(currentUser());
            messageUtils.when(() -> MessageUtils.getMessage(ErrorCode.UPDATE_DATA_FAILED))
                    .thenReturn("Failed to update data");

            Result<Void> result = controller.updateDeviceInfo(DEVICE_ID, update);

            assertEquals(ErrorCode.UPDATE_DATA_FAILED, result.getCode());
            assertEquals(0, entity.getAutoUpdate());
            verify(deviceService).updateById(entity);
        }
    }

    private DeviceController controller(DeviceService deviceService) {
        return new DeviceController(
                deviceService,
                mock(DeviceAddressBookService.class),
                mock(RedisUtils.class),
                mock(SysParamsService.class),
                mock(OtaService.class));
    }

    private DeviceEntity ownedDevice() {
        DeviceEntity entity = new DeviceEntity();
        entity.setId(DEVICE_ID);
        entity.setUserId(USER_ID);
        entity.setAutoUpdate(1);
        return entity;
    }

    private UserDetail currentUser() {
        UserDetail user = new UserDetail();
        user.setId(USER_ID);
        return user;
    }
}

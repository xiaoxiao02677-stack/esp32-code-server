package xiaozhi.modules.device.service;

import java.util.Map;

import xiaozhi.common.page.PageData;
import xiaozhi.common.service.BaseService;
import xiaozhi.modules.device.entity.DeviceConfigEntity;

/**
 * 设备云端配置管理侧服务（P1-4：管理后台查看/清库入口）
 * <p>
 * 与 DeviceConfigService（B 线原子 upsert 写入链，并行改造中）解耦：
 * 本服务只提供管理端的 分页查询 / 全表清库；单条查询/删除走 BaseService 的
 * selectById / deleteById（device_id 为 ai_device_config 主键）。
 */
public interface DeviceConfigAdminService extends BaseService<DeviceConfigEntity> {

    /**
     * 分页查询设备云端配置（可选按 deviceId 模糊匹配）
     *
     * @param params 分页与查询参数（page/limit/deviceId/orderField/order）
     */
    PageData<DeviceConfigEntity> page(Map<String, Object> params);

    /**
     * 清空全部设备云端配置
     * <p>
     * 采用分批按主键删除，规避 BlockAttackInnerInterceptor 对无条件全表 DELETE 的拦截
     *
     * @return 删除的记录数
     */
    int deleteAll();
}

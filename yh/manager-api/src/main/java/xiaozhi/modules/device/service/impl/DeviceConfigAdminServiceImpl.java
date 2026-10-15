package xiaozhi.modules.device.service.impl;

import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

import org.apache.commons.lang3.StringUtils;
import org.springframework.stereotype.Service;

import com.baomidou.mybatisplus.core.conditions.query.QueryWrapper;
import com.baomidou.mybatisplus.core.metadata.IPage;
import com.baomidou.mybatisplus.core.toolkit.CollectionUtils;

import xiaozhi.common.page.PageData;
import xiaozhi.common.service.impl.BaseServiceImpl;
import xiaozhi.modules.device.dao.DeviceConfigDao;
import xiaozhi.modules.device.entity.DeviceConfigEntity;
import xiaozhi.modules.device.service.DeviceConfigAdminService;

/**
 * 设备云端配置管理侧实现（P1-4）
 * <p>
 * 只读 + 删除，不修改 DeviceConfigServiceImpl / DeviceConfigDao / DeviceConfigEntity
 * 的既有写入链（原子 upsert 并行改造中）。
 */
@Service
public class DeviceConfigAdminServiceImpl extends BaseServiceImpl<DeviceConfigDao, DeviceConfigEntity>
        implements DeviceConfigAdminService {

    /** 清库分批大小：IN 子句过长会顶爆 max_allowed_packet / 慢锁，500 一批稳妥 */
    private static final int DELETE_BATCH_SIZE = 500;

    @Override
    public PageData<DeviceConfigEntity> page(Map<String, Object> params) {
        IPage<DeviceConfigEntity> page = baseDao.selectPage(
                getPage(params, "update_date", false),
                getWrapper(params));

        return new PageData<>(page.getRecords(), page.getTotal());
    }

    @Override
    public int deleteAll() {
        List<DeviceConfigEntity> entities = baseDao.selectList(null);
        if (CollectionUtils.isEmpty(entities)) {
            return 0;
        }

        List<String> ids = entities.stream()
                .map(DeviceConfigEntity::getDeviceId)
                .collect(Collectors.toList());

        int count = 0;
        for (int i = 0; i < ids.size(); i += DELETE_BATCH_SIZE) {
            List<String> batch = ids.subList(i, Math.min(i + DELETE_BATCH_SIZE, ids.size()));
            count += baseDao.deleteByIds(batch);
        }
        return count;
    }

    private QueryWrapper<DeviceConfigEntity> getWrapper(Map<String, Object> params) {
        String deviceId = (String) params.get("deviceId");

        QueryWrapper<DeviceConfigEntity> wrapper = new QueryWrapper<>();
        wrapper.like(StringUtils.isNotBlank(deviceId), "device_id", deviceId);

        return wrapper;
    }
}

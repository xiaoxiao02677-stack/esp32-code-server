package yuhe.modules.device.dao;

import java.util.Date;

import org.apache.ibatis.annotations.Insert;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;

import com.baomidou.mybatisplus.core.mapper.BaseMapper;

import yuhe.modules.device.entity.DeviceConfigEntity;

@Mapper
public interface DeviceConfigDao extends BaseMapper<DeviceConfigEntity> {

    /**
     * 原子 upsert（P1-6）：单条 SQL 完成「不存在则插入，存在则 JSON 增量合并」，
     * 取代原非原子「读-改-写 LWW」。MySQL 8 JSON_MERGE_PATCH(old, delta) 语义：
     * delta 键覆盖旧值，其余旧键保留；同值重复写天然幂等不产生 diff。
     * creator/createDate 仅在插入分支写入（注解 SQL 不走 MetaObjectHandler 自动填充，
     * 审计值由调用方传入，无操作人上下文时传 null）；冲突更新分支只刷新
     * config_json/updater/update_date，不覆盖创建信息。
     *
     * @param deviceId   设备ID（主键）
     * @param configJson 本次合法增量 JSON 串（白名单键已校验）
     * @param creator    创建人（仅插入分支生效，可空）
     * @param createDate 创建时间（仅插入分支生效，可空）
     * @param updater    更新人（插入/更新分支均生效，可空）
     * @param updateDate 更新时间
     */
    @Insert("INSERT INTO ai_device_config(device_id, config_json, creator, create_date, updater, update_date) " +
            "VALUES(#{deviceId}, CAST(#{configJson} AS JSON), #{creator}, #{createDate}, #{updater}, #{updateDate}) " +
            "ON DUPLICATE KEY UPDATE " +
            "config_json = JSON_MERGE_PATCH(config_json, VALUES(config_json)), " +
            "updater = #{updater}, update_date = #{updateDate}")
    void upsertMergePatch(@Param("deviceId") String deviceId,
                          @Param("configJson") String configJson,
                          @Param("creator") Long creator,
                          @Param("createDate") Date createDate,
                          @Param("updater") Long updater,
                          @Param("updateDate") Date updateDate);
}

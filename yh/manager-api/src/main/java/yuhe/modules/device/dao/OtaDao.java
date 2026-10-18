package yuhe.modules.device.dao;

import org.apache.ibatis.annotations.Mapper;

import com.baomidou.mybatisplus.core.mapper.BaseMapper;

import yuhe.modules.device.entity.OtaEntity;

/**
 * OTA固件管理
 */
@Mapper
public interface OtaDao extends BaseMapper<OtaEntity> {
    
}
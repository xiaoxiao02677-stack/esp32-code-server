package yuhe.modules.sys.dao;

import org.apache.ibatis.annotations.Mapper;

import yuhe.common.dao.BaseDao;
import yuhe.modules.sys.entity.SysUserDefaultEntity;

/**
 * 用户默认模型配置
 */
@Mapper
public interface SysUserDefaultDao extends BaseDao<SysUserDefaultEntity> {

}

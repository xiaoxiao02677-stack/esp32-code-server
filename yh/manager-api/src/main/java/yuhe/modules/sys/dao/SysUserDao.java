package yuhe.modules.sys.dao;

import org.apache.ibatis.annotations.Mapper;

import yuhe.common.dao.BaseDao;
import yuhe.modules.sys.entity.SysUserEntity;

/**
 * 系统用户
 */
@Mapper
public interface SysUserDao extends BaseDao<SysUserEntity> {

}
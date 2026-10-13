package xiaozhi.modules.sys.dao;

import org.apache.ibatis.annotations.Mapper;

import xiaozhi.common.dao.BaseDao;
import xiaozhi.modules.sys.entity.SysUserRoleEntity;

/**
 * 用户角色关联
 */
@Mapper
public interface SysUserRoleDao extends BaseDao<SysUserRoleEntity> {

}

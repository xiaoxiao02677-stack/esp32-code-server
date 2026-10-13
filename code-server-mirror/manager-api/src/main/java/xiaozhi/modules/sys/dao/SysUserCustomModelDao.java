package xiaozhi.modules.sys.dao;

import org.apache.ibatis.annotations.Mapper;

import xiaozhi.common.dao.BaseDao;
import xiaozhi.modules.sys.entity.SysUserCustomModelEntity;

/**
 * 用户自定义模型
 */
@Mapper
public interface SysUserCustomModelDao extends BaseDao<SysUserCustomModelEntity> {

}

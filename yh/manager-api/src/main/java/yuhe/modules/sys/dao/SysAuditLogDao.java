package yuhe.modules.sys.dao;

import org.apache.ibatis.annotations.Mapper;

import yuhe.common.dao.BaseDao;
import yuhe.modules.sys.entity.SysAuditLogEntity;

/**
 * 审计日志
 */
@Mapper
public interface SysAuditLogDao extends BaseDao<SysAuditLogEntity> {

}

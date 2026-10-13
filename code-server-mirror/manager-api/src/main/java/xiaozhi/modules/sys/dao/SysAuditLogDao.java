package xiaozhi.modules.sys.dao;

import java.util.List;

import org.apache.ibatis.annotations.Mapper;

import xiaozhi.common.dao.BaseDao;
import xiaozhi.modules.sys.entity.SysAuditLogEntity;

/**
 * 安全审计日志
 */
@Mapper
public interface SysAuditLogDao extends BaseDao<SysAuditLogEntity> {

    /** 去重 module 列表（筛选用） */
    List<String> selectDistinctModules();
}

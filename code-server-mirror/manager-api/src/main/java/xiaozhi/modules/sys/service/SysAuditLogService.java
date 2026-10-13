package xiaozhi.modules.sys.service;

import java.util.Map;

import xiaozhi.common.page.PageData;
import xiaozhi.modules.sys.vo.SysAuditLogVO;

/**
 * 审计日志查询服务（查询端点用；写入口见 AuditService）
 */
public interface SysAuditLogService {

    /** 分页查询（userId/module/operation/startDate/endDate 过滤） */
    PageData<SysAuditLogVO> page(Map<String, Object> params);

    /** 去重 module 列表（筛选用） */
    java.util.List<String> listModules();
}

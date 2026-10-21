package yuhe.modules.sys.entity;

import java.io.Serializable;
import java.util.Date;

import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;

import lombok.Data;

/**
 * 审计日志（表 sys_audit_log 双环境已存在；写入由 AuditLogAspect 负责，本实体只做读取侧映射）
 */
@Data
@TableName("sys_audit_log")
public class SysAuditLogEntity implements Serializable {
    @TableId(type = IdType.AUTO)
    private Long id;
    private Long userId;
    private String username;
    private String module;
    private String operation;
    private String targetType;
    private String targetId;
    private String requestUri;
    private String requestMethod;
    /** JSON 字符串透传（前端自行 parse 展示） */
    private String params;
    /** 1 成功 0 失败 */
    private Integer result;
    private String errorMsg;
    private String ip;
    private String userAgent;
    /** 耗时 ms */
    private Integer duration;
    private Date createdAt;
}

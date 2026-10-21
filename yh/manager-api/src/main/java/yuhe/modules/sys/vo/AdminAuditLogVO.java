package yuhe.modules.sys.vo;

import lombok.Data;

/**
 * 审计日志 VO（console-v2 AuditLog.vue 契约：DB created_at → 前端 createdDate）
 */
@Data
public class AdminAuditLogVO {
    private Long id;
    private Long userId;
    private String username;
    private String module;
    private String operation;
    private String targetType;
    private String targetId;
    private String requestUri;
    private String requestMethod;
    /** JSON 字符串透传，前端自行 parse */
    private String params;
    /** 1 成功 0 失败 */
    private Integer result;
    private String errorMsg;
    private String ip;
    private String userAgent;
    /** 耗时 ms */
    private Integer duration;
    /** 对应 DB created_at（前端期望字段名） */
    private String createdDate;
}

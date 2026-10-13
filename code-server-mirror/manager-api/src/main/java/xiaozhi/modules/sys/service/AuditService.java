package xiaozhi.modules.sys.service;

/**
 * 审计日志服务（用户管理模块）。
 *
 * 由 audit agent 提供实现（SysAuditLogServiceImpl + LogOperationAspect）；
 * user-mgmt / rbac / custom 等业务 agent 在敏感操作处调用本接口落审计。
 *
 * 实现要求：
 * - 异步落库（@Async 或线程池），不得阻塞业务请求
 * - 操作人 user_id/username 从 SecurityUser 获取（无登录上下文时置 null，如 anon 接口）
 * - params 做脱敏：递归移除 key 为 password/apiKey/secret/token（忽略大小写）的字段
 * - request_uri/method/ip/user_agent 由实现方从 RequestContextHolder 取
 */
public interface AuditService {

    /**
     * 记录审计日志。
     *
     * @param module     模块：user / role / custom / security
     * @param operation  操作：login/logout/create/update/delete/disable/enable/
     *                   restore/resetPwd/assignRoles/import/export/forceLogout/audit/forbidden
     * @param targetType 目标对象类型（如 sys_user / sys_role / custom_model）
     * @param targetId   目标对象 ID（字符串化）
     * @param params     请求参数（会被脱敏后 JSON 存储；传 null 跳过）
     * @param success    结果（true 成功 / false 失败）
     * @param errorMsg   失败原因（成功传 null）
     */
    void log(String module, String operation, String targetType, String targetId,
             Object params, boolean success, String errorMsg);
}

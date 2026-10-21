package yuhe.modules.sys.vo;

import lombok.Data;

/**
 * 自定义模型审核列表 VO（console-v2 CustomReview.vue 契约：
 * 附加 username（join sys_user）与 apiKeyMasked（密钥掩码，绝不回传明文/密文））
 */
@Data
public class AdminCustomModelVO {
    private String id;
    private Long userId;
    private String username;
    private String modelType;
    private String modelName;
    private String providerCode;
    private String baseUrl;
    /** 掩码后的 API Key（如 sk-a****xyz） */
    private String apiKeyMasked;
    /** 0 待审核 1 已通过 2 已驳回 */
    private Integer auditStatus;
    private String auditRemark;
    private Long auditor;
    private String auditDate;
    private Integer status;
    private Integer healthStatus;
    private Integer quotaLimit;
    private Long usedCount;
    private String remark;
    private String createDate;
}

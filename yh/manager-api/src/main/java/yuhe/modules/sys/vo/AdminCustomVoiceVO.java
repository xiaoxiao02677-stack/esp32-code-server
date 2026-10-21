package yuhe.modules.sys.vo;

import lombok.Data;

/**
 * 自定义音色审核列表 VO（console-v2 CustomReview.vue 音色 tab 契约：
 * 附加 username；voice 无配额字段，其余同构）
 */
@Data
public class AdminCustomVoiceVO {
    private String id;
    private Long userId;
    private String username;
    private String name;
    private String ttsModelId;
    private String ttsVoice;
    private String languages;
    private String referenceText;
    /** 0 待审核 1 已通过 2 已驳回 */
    private Integer auditStatus;
    private String auditRemark;
    private Long auditor;
    private String auditDate;
    private Integer status;
    private String remark;
    private String createDate;
}

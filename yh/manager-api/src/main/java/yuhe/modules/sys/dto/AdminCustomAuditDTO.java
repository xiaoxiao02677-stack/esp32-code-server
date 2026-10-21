package yuhe.modules.sys.dto;

import lombok.Data;

/**
 * 自定义模型/音色审核 DTO（console-v2 CustomReview.vue 契约：{id, pass, remark}）
 */
@Data
public class AdminCustomAuditDTO {
    private String id;
    private Boolean pass;
    private String remark;
}

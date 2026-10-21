package yuhe.modules.sys.dto;

import lombok.Data;

/**
 * 自定义模型配额 DTO（console-v2 CustomReview.vue 契约：{id, quotaLimit}，quotaLimit=null 表示不限）
 */
@Data
public class AdminCustomQuotaDTO {
    private String id;
    private Integer quotaLimit;
}

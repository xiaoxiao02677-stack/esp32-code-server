package yuhe.modules.sys.dto;

import lombok.Data;

/**
 * 默认配置保存 DTO（console-v2 UserDefaults.vue 契约：paramJson 前端已 stringify，其余字段可 null 表示清除）
 */
@Data
public class SysUserDefaultSaveDTO {
    /** 0 系统 1 角色 2 用户 */
    private Integer scopeType;
    private Long roleId;
    private Long userId;
    private String llmModelId;
    private String ttsModelId;
    private String ttsVoiceId;
    private String asrModelId;
    private String paramJson;
    private Boolean lockPolicy;
}

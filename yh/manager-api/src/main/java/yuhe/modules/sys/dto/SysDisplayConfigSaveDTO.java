package yuhe.modules.sys.dto;

import lombok.Data;

/**
 * 展示配置保存 DTO（console-v2 DisplayConfig.vue 契约：configJson 是对象 {fields:{key:{visible,editable}}}，
 * DB 存 JSON 字符串，服务层负责 stringify）
 */
@Data
public class SysDisplayConfigSaveDTO {
    /** 0 系统 1 角色 2 用户 */
    private Integer scopeType;
    private Long roleId;
    private Long userId;
    private Object configJson;
}

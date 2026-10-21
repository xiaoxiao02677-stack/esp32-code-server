package yuhe.modules.sys.dto;

import java.util.List;

import lombok.Data;

/**
 * 角色保存/更新 DTO（console-v2 Roles.vue 契约：permissions 是数组，DB 存 JSON 字符串）
 */
@Data
public class SysRoleSaveDTO {
    /** 更新时必填 */
    private Long id;
    private String roleCode;
    private String roleName;
    private List<String> permissions;
    private String remark;
    private Integer sort;
    private Integer status;
}

package yuhe.modules.sys.vo;

import java.util.List;

import lombok.Data;

/**
 * 管理端角色列表/详情 VO（console-v2 Roles.vue normalizeRole 消费字段：
 * id/roleCode/roleName/remark/status/isBuiltIn/userCount/creatorName/createDate/permissions[]）
 */
@Data
public class AdminRoleVO {
    private Long id;
    private String roleCode;
    private String roleName;
    private String remark;
    private Integer status;
    private Integer isBuiltIn;
    private Long userCount;
    private String creatorName;
    private String createDate;
    /** 权限点数组（DB JSON 字符串 parse 后返回） */
    private List<String> permissions;
    private Integer sort;
}

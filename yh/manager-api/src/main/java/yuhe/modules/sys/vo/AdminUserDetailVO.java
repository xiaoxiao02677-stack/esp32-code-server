package yuhe.modules.sys.vo;

import java.util.ArrayList;
import java.util.List;

import io.swagger.v3.oas.annotations.media.Schema;
import lombok.Data;

/**
 * 管理端用户详情 VO（console-v2 openRoles 消费 data={user, roles}，
 * roles 元素至少含 id；这里给全量角色字段）
 */
@Data
public class AdminUserDetailVO {
    @Schema(description = "用户信息")
    private AdminUserListVO user = new AdminUserListVO();

    @Schema(description = "当前角色（含 id/roleCode/roleName）")
    private List<RoleItem> roles = new ArrayList<>();

    @Data
    public static class RoleItem {
        private Long id;
        private String roleCode;
        private String roleName;
    }
}

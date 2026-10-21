package yuhe.modules.sys.dto;

import java.util.List;

import io.swagger.v3.oas.annotations.media.Schema;
import jakarta.validation.constraints.NotNull;
import lombok.Data;

/**
 * 管理端分配角色（console-v2 rolesEditor：{userId, roleIds}）
 */
@Data
public class AdminUserRolesDTO {
    @NotNull(message = "用户ID不能为空")
    @Schema(description = "用户ID")
    private Long userId;

    @Schema(description = "角色ID列表（空数组=清空角色）")
    private List<Long> roleIds;
}

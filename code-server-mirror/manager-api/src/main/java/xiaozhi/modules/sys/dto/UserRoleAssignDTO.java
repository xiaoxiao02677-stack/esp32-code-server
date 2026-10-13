package xiaozhi.modules.sys.dto;

import java.io.Serializable;
import java.util.List;

import io.swagger.v3.oas.annotations.media.Schema;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotEmpty;
import jakarta.validation.constraints.NotNull;
import lombok.Data;

/**
 * 用户角色分配
 */
@Data
@Schema(description = "用户角色分配")
public class UserRoleAssignDTO implements Serializable {

    @Schema(description = "用户ID")
    @NotNull(message = "{sysuser.id.require}")
    private Long userId;

    @Schema(description = "角色ID列表（空数组=清空角色）")
    @NotEmpty(message = "{sysuser.roleids.require}")
    private List<Long> roleIds;
}

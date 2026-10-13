package xiaozhi.modules.sys.dto;

import java.io.Serializable;
import java.util.List;

import io.swagger.v3.oas.annotations.media.Schema;
import jakarta.validation.constraints.NotBlank;
import lombok.Data;

/**
 * 管理员新建用户
 */
@Data
@Schema(description = "管理员新建用户")
public class AdminUserCreateDTO implements Serializable {

    @Schema(description = "用户名")
    @NotBlank(message = "{sysuser.username.require}")
    private String username;

    @Schema(description = "初始密码（缺省自动生成12位）")
    private String password;

    @Schema(description = "角色ID列表")
    private List<Long> roleIds;
}

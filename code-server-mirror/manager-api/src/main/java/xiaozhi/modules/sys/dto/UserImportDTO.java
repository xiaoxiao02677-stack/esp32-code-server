package xiaozhi.modules.sys.dto;

import java.io.Serializable;

import io.swagger.v3.oas.annotations.media.Schema;
import jakarta.validation.constraints.NotBlank;
import lombok.Data;

/**
 * 批量导入用户项（POST /admin/users/import body 数组元素）
 */
@Data
@Schema(description = "批量导入用户项")
public class UserImportDTO implements Serializable {

    @Schema(description = "用户名")
    @NotBlank(message = "{sysuser.username.require}")
    private String username;

    @Schema(description = "初始密码（缺省自动生成）")
    private String password;

    @Schema(description = "角色编码（如 user/readonly；缺省不分配角色）")
    private String roleCode;
}

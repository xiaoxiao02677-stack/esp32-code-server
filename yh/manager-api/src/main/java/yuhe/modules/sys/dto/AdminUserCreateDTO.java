package yuhe.modules.sys.dto;

import java.util.List;

import io.swagger.v3.oas.annotations.media.Schema;
import jakarta.validation.constraints.NotBlank;
import lombok.Data;

/**
 * 管理端新增用户（console-v2 creator：{username, password?, roleIds?}）
 */
@Data
public class AdminUserCreateDTO {
    @NotBlank(message = "用户名不能为空")
    @Schema(description = "用户名")
    private String username;

    @Schema(description = "初始密码，缺省自动生成")
    private String password;

    @Schema(description = "角色ID列表")
    private List<Long> roleIds;
}

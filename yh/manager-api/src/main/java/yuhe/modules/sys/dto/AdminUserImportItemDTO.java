package yuhe.modules.sys.dto;

import io.swagger.v3.oas.annotations.media.Schema;
import jakarta.validation.constraints.NotBlank;
import lombok.Data;

/**
 * 批量导入用户单项（console-v2 importer：[{username, password?}]）
 */
@Data
public class AdminUserImportItemDTO {
    @NotBlank(message = "用户名不能为空")
    @Schema(description = "用户名")
    private String username;

    @Schema(description = "初始密码，缺省自动生成")
    private String password;
}

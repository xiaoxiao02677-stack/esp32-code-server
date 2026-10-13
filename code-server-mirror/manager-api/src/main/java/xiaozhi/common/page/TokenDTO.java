package xiaozhi.common.page;

import java.io.Serializable;

import io.swagger.v3.oas.annotations.media.Schema;
import lombok.Data;

/**
 * 令牌信息
 *
 * @author Jack
 */
@Data
@Schema(description = "令牌信息")
public class TokenDTO implements Serializable {

    @Schema(description = "密码")
    private String token;

    @Schema(description = "过期时间")
    private int expire;

    @Schema(description = "客户端指纹")
    private String clientHash;

    @Schema(description = "用户名")
    private String username;

    @Schema(description = "超级管理员（0否 1是）")
    private Integer superAdmin;

    @Schema(description = "角色编码列表")
    private java.util.List<String> roles;

    @Schema(description = "是否需要强制修改密码")
    private Boolean mustChangePwd;
}

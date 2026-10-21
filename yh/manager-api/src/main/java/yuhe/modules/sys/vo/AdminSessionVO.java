package yuhe.modules.sys.vo;

import java.util.Date;

import io.swagger.v3.oas.annotations.media.Schema;
import lombok.Data;

/**
 * 管理端在线会话 VO（console-v2 Users.vue 会话弹窗消费
 * userId/username/token/expireDate/createDate；token 做前8位掩码）
 */
@Data
public class AdminSessionVO {
    @Schema(description = "用户ID")
    private Long userId;

    @Schema(description = "用户名")
    private String username;

    @Schema(description = "token（前8位掩码）")
    private String token;

    @Schema(description = "过期时间")
    private Date expireDate;

    @Schema(description = "创建时间")
    private Date createDate;
}

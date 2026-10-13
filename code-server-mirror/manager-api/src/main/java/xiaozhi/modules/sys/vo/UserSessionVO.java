package xiaozhi.modules.sys.vo;

import java.io.Serializable;
import java.util.Date;

import com.fasterxml.jackson.annotation.JsonFormat;

import io.swagger.v3.oas.annotations.media.Schema;
import lombok.Data;
import xiaozhi.common.utils.DateUtils;

/**
 * 在线会话（sys_user_token JOIN sys_user）
 */
@Data
@Schema(description = "在线会话")
public class UserSessionVO implements Serializable {

    @Schema(description = "token 记录ID")
    private Long id;

    @Schema(description = "用户ID")
    private Long userId;

    @Schema(description = "用户名")
    private String username;

    @Schema(description = "token 前8位掩码（如 abcd12****）")
    private String tokenMasked;

    @Schema(description = "过期时间")
    @JsonFormat(pattern = DateUtils.DATE_TIME_PATTERN)
    private Date expireDate;

    @Schema(description = "创建时间")
    @JsonFormat(pattern = DateUtils.DATE_TIME_PATTERN)
    private Date createDate;
}

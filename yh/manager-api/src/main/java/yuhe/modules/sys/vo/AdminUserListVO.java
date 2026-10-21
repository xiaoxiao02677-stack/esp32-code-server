package yuhe.modules.sys.vo;

import java.util.Date;
import java.util.List;

import io.swagger.v3.oas.annotations.media.Schema;
import lombok.Data;

/**
 * 管理端用户列表 VO（对齐 console-v2 Users.vue normalizeUser 消费的字段：
 * id/username/roleNames[]/status/locked/deleted/lastLoginDate/createDate）
 */
@Data
public class AdminUserListVO {
    @Schema(description = "用户ID")
    private Long id;

    @Schema(description = "用户名")
    private String username;

    @Schema(description = "角色名列表")
    private List<String> roleNames;

    @Schema(description = "状态 0停用 1正常")
    private Integer status;

    @Schema(description = "锁定 0未锁 1锁定")
    private Integer locked;

    @Schema(description = "删除 0正常 1已删除")
    private Integer deleted;

    @Schema(description = "设备数")
    private Long deviceCount;

    @Schema(description = "最后登录时间")
    private Date lastLoginDate;

    @Schema(description = "注册时间")
    private Date createDate;
}

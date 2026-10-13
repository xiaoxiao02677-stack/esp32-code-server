package xiaozhi.modules.sys.vo;

import java.io.Serializable;
import java.util.Date;
import java.util.List;

import com.fasterxml.jackson.annotation.JsonFormat;

import io.swagger.v3.oas.annotations.media.Schema;
import lombok.Data;
import xiaozhi.common.utils.DateUtils;

/**
 * 用户详情（管理端）—— {user, roles, defaults, displayConfig} 中的 user 部分 + 角色信息
 */
@Data
@Schema(description = "用户详情")
public class AdminUserDetailVO implements Serializable {

    @Schema(description = "用户ID")
    private Long id;

    @Schema(description = "用户名")
    private String username;

    @Schema(description = "超级管理员（0否 1是）")
    private Integer superAdmin;

    @Schema(description = "状态（0停用 1正常）")
    private Integer status;

    @Schema(description = "软删除（0否 1是）")
    private Integer deleted;

    @Schema(description = "锁定（0否 1是）")
    private Integer locked;

    @Schema(description = "强制改密（0否 1是）")
    private Integer mustChangePwd;

    @Schema(description = "最后登录时间")
    @JsonFormat(pattern = DateUtils.DATE_TIME_PATTERN)
    private Date lastLoginDate;

    @Schema(description = "密码最后修改时间")
    @JsonFormat(pattern = DateUtils.DATE_TIME_PATTERN)
    private Date pwdUpdateDate;

    @Schema(description = "删除时间")
    @JsonFormat(pattern = DateUtils.DATE_TIME_PATTERN)
    private Date deletedDate;

    @Schema(description = "创建时间")
    @JsonFormat(pattern = DateUtils.DATE_TIME_PATTERN)
    private Date createDate;

    @Schema(description = "角色ID列表")
    private List<Long> roleIds;

    @Schema(description = "角色名称列表")
    private List<String> roleNames;
}

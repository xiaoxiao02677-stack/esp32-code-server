package xiaozhi.modules.sys.vo;

import java.io.Serializable;
import java.util.Date;
import java.util.List;

import com.fasterxml.jackson.annotation.JsonFormat;

import io.swagger.v3.oas.annotations.media.Schema;
import lombok.Data;
import xiaozhi.common.utils.DateUtils;

/**
 * 管理端用户分页 VO（新增 roleNames/deleted/locked/lastLoginDate 等字段）
 */
@Data
@Schema(description = "管理端用户分页")
public class AdminUserPageVO implements Serializable {

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

    @Schema(description = "创建时间")
    @JsonFormat(pattern = DateUtils.DATE_TIME_PATTERN)
    private Date createDate;

    @Schema(description = "角色名称列表")
    private List<String> roleNames;
}

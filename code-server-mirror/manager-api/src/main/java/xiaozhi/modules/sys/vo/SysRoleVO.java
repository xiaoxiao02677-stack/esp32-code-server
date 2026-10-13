package xiaozhi.modules.sys.vo;

import java.io.Serializable;
import java.util.Date;
import java.util.List;

import com.fasterxml.jackson.annotation.JsonFormat;

import io.swagger.v3.oas.annotations.media.Schema;
import lombok.Data;
import lombok.EqualsAndHashCode;
import xiaozhi.common.utils.DateUtils;

/**
 * 角色 VO
 */
@Data
@EqualsAndHashCode(callSuper = false)
@Schema(description = "角色")
public class SysRoleVO implements Serializable {

    @Schema(description = "id")
    private Long id;

    @Schema(description = "角色编码")
    private String roleCode;

    @Schema(description = "角色名称")
    private String roleName;

    @Schema(description = "权限点列表")
    private List<String> permissions;

    @Schema(description = "备注")
    private String remark;

    @Schema(description = "状态（0停用 1正常）")
    private Integer status;

    @Schema(description = "内置角色（0否 1是）")
    private Integer isBuiltin;

    @Schema(description = "排序")
    private Integer sort;

    @Schema(description = "创建者ID")
    private Long creator;

    @Schema(description = "创建者用户名")
    private String creatorName;

    @Schema(description = "创建时间")
    @JsonFormat(pattern = DateUtils.DATE_TIME_PATTERN)
    private Date createDate;

    @Schema(description = "更新者ID")
    private Long updater;

    @Schema(description = "更新者用户名")
    private String updaterName;

    @Schema(description = "更新时间")
    @JsonFormat(pattern = DateUtils.DATE_TIME_PATTERN)
    private Date updateDate;

    @Schema(description = "关联用户数（含已删除用户）")
    private Long userCount;
}

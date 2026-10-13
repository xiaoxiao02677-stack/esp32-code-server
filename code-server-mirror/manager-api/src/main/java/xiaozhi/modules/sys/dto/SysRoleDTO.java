package xiaozhi.modules.sys.dto;

import java.io.Serializable;
import java.util.Date;
import java.util.List;

import com.fasterxml.jackson.annotation.JsonFormat;
import com.fasterxml.jackson.annotation.JsonProperty;

import io.swagger.v3.oas.annotations.media.Schema;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Null;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;
import lombok.Data;
import xiaozhi.common.utils.DateUtils;
import xiaozhi.common.validator.group.AddGroup;
import xiaozhi.common.validator.group.DefaultGroup;
import xiaozhi.common.validator.group.UpdateGroup;

/**
 * 角色
 */
@Data
@Schema(description = "角色")
public class SysRoleDTO implements Serializable {

    @Schema(description = "id")
    @Null(message = "{id.null}", groups = AddGroup.class)
    @NotNull(message = "{id.require}", groups = UpdateGroup.class)
    private Long id;

    @Schema(description = "角色编码（唯一）")
    @NotBlank(message = "{sysrole.code.require}", groups = DefaultGroup.class)
    @Pattern(regexp = "^[a-zA-Z][a-zA-Z0-9_]{1,49}$", message = "{sysrole.code.pattern}", groups = DefaultGroup.class)
    private String roleCode;

    @Schema(description = "角色名称")
    @NotBlank(message = "{sysrole.name.require}", groups = DefaultGroup.class)
    @Size(max = 50, message = "{sysrole.name.size}", groups = DefaultGroup.class)
    private String roleName;

    @Schema(description = "权限点列表")
    private List<String> permissions;

    @Schema(description = "备注")
    @Size(max = 200, message = "{sysrole.remark.size}", groups = DefaultGroup.class)
    private String remark;

    @Schema(description = "状态（0停用 1正常）")
    @NotNull(message = "{sysrole.status.require}", groups = { AddGroup.class, UpdateGroup.class })
    private Integer status;

    @Schema(description = "排序")
    @Min(value = 0, message = "{sort.number}", groups = DefaultGroup.class)
    private Integer sort;

    @Schema(description = "创建时间")
    @JsonProperty(access = JsonProperty.Access.READ_ONLY)
    @JsonFormat(pattern = DateUtils.DATE_TIME_PATTERN)
    private Date createDate;

    @Schema(description = "更新时间")
    @JsonProperty(access = JsonProperty.Access.READ_ONLY)
    @JsonFormat(pattern = DateUtils.DATE_TIME_PATTERN)
    private Date updateDate;
}

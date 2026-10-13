package xiaozhi.modules.sys.vo;

import java.io.Serializable;
import java.util.Date;

import com.fasterxml.jackson.annotation.JsonFormat;

import io.swagger.v3.oas.annotations.media.Schema;
import lombok.Data;
import xiaozhi.common.utils.DateUtils;

/**
 * 审计日志 VO
 */
@Data
@Schema(description = "审计日志")
public class SysAuditLogVO implements Serializable {

    @Schema(description = "主键ID")
    private Long id;

    @Schema(description = "操作人ID")
    private Long userId;

    @Schema(description = "操作人用户名")
    private String username;

    @Schema(description = "模块")
    private String module;

    @Schema(description = "操作类型")
    private String operation;

    @Schema(description = "目标对象类型")
    private String targetType;

    @Schema(description = "目标对象ID")
    private String targetId;

    @Schema(description = "请求URI")
    private String requestUri;

    @Schema(description = "HTTP方法")
    private String requestMethod;

    @Schema(description = "请求参数（脱敏后）")
    private Object params;

    @Schema(description = "结果（0失败 1成功）")
    private Integer result;

    @Schema(description = "错误信息")
    private String errorMsg;

    @Schema(description = "操作IP")
    private String ip;

    @Schema(description = "UA")
    private String userAgent;

    @Schema(description = "耗时(ms)")
    private Integer duration;

    @Schema(description = "创建时间")
    @JsonFormat(pattern = DateUtils.DATE_TIME_PATTERN)
    private Date createdAt;
}

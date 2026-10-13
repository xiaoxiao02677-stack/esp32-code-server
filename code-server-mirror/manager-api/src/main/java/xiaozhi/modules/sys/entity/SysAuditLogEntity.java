package xiaozhi.modules.sys.entity;

import java.io.Serializable;
import java.util.Date;

import com.baomidou.mybatisplus.annotation.FieldFill;
import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableField;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;

import lombok.Data;

/**
 * 安全审计日志（追加只写，不提供更新/删除接口）
 */
@Data
@TableName("sys_audit_log")
public class SysAuditLogEntity implements Serializable {

    /**
     * 主键ID（AUTO_INCREMENT）
     */
    @TableId(type = IdType.AUTO)
    private Long id;

    /**
     * 操作人ID
     */
    private Long userId;

    /**
     * 操作人用户名（冗余）
     */
    private String username;

    /**
     * 模块（user/role/custom/security）
     */
    private String module;

    /**
     * 操作类型（login/logout/create/update/delete/...）
     */
    private String operation;

    /**
     * 目标对象类型
     */
    private String targetType;

    /**
     * 目标对象ID
     */
    private String targetId;

    /**
     * 请求URI
     */
    private String requestUri;

    /**
     * HTTP方法
     */
    private String requestMethod;

    /**
     * 请求参数（脱敏后 JSON 字符串）
     */
    private String params;

    /**
     * 结果（0失败 1成功）
     */
    private Integer result;

    /**
     * 错误信息
     */
    private String errorMsg;

    /**
     * 操作IP
     */
    private String ip;

    /**
     * UA
     */
    private String userAgent;

    /**
     * 耗时(ms)
     */
    private Integer duration;

    /**
     * 创建时间
     */
    @TableField(fill = FieldFill.INSERT)
    private Date createdAt;
}

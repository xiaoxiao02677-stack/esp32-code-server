package yuhe.modules.sys.entity;

import java.io.Serializable;
import java.util.Date;

import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;

import lombok.Data;

/**
 * 用户自定义模型（表 sys_user_custom_model；id 为 32 位短串非雪花）
 */
@Data
@TableName("sys_user_custom_model")
public class SysUserCustomModelEntity implements Serializable {
    @TableId
    private String id;
    private Long userId;
    private String modelType;
    private String modelName;
    private String providerCode;
    private String configJson;
    private String apiKeyCipher;
    private String baseUrl;
    /** 0 待审核 1 已通过 2 已驳回 */
    private Integer auditStatus;
    private String auditRemark;
    private Long auditor;
    private Date auditDate;
    private Integer status;
    private Integer healthStatus;
    private Integer quotaLimit;
    private Long usedCount;
    private String remark;
    private Integer sort;
    private Long creator;
    private Date createDate;
    private Long updater;
    private Date updateDate;
}

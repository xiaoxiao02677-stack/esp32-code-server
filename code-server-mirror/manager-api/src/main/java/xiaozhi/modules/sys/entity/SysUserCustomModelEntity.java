package xiaozhi.modules.sys.entity;

import java.util.Date;

import com.baomidou.mybatisplus.annotation.FieldFill;
import com.baomidou.mybatisplus.annotation.TableField;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;

import lombok.Data;

/**
 * 用户自定义模型（仅本人可见，密钥加密，审核后可用）
 */
@Data
@TableName("sys_user_custom_model")
public class SysUserCustomModelEntity {

    /**
     * 主键（UUID）
     */
    @TableId
    private String id;

    /**
     * 所属用户ID
     */
    private Long userId;

    /**
     * 模型类型（LLM/ASR/TTS/VAD/Memory，统一大写）
     */
    private String modelType;

    /**
     * 模型名称
     */
    private String modelName;

    /**
     * 供应器编码
     */
    private String providerCode;

    /**
     * 模型配置 JSON
     */
    private String configJson;

    /**
     * API密钥密文（AES-256-GCM，接口永不明文返回）
     */
    private String apiKeyCipher;

    /**
     * 接口地址
     */
    private String baseUrl;

    /**
     * 审核状态（0待审核 1通过 2驳回）
     */
    private Integer auditStatus;

    /**
     * 审核意见
     */
    private String auditRemark;

    /**
     * 审核人
     */
    private Long auditor;

    /**
     * 审核时间
     */
    private Date auditDate;

    /**
     * 状态（0停用 1正常 2维护 3下线）
     */
    private Integer status;

    /**
     * 健康检查（0未知 1正常 2异常）
     */
    private Integer healthStatus;

    /**
     * 调用配额（次/日，NULL不限）
     */
    private Integer quotaLimit;

    /**
     * 已用次数
     */
    private Long usedCount;

    /**
     * 备注
     */
    private String remark;

    /**
     * 排序
     */
    private Integer sort;

    /**
     * 创建者
     */
    @TableField(fill = FieldFill.INSERT)
    private Long creator;

    /**
     * 创建时间
     */
    @TableField(fill = FieldFill.INSERT)
    private Date createDate;

    /**
     * 更新者
     */
    @TableField(fill = FieldFill.INSERT_UPDATE)
    private Long updater;

    /**
     * 更新时间
     */
    @TableField(fill = FieldFill.INSERT_UPDATE)
    private Date updateDate;
}

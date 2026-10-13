package xiaozhi.modules.sys.entity;

import java.util.Date;

import com.baomidou.mybatisplus.annotation.FieldFill;
import com.baomidou.mybatisplus.annotation.TableField;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;

import lombok.Data;

/**
 * 用户自定义音色（仅本人可见，审核后可用）
 */
@Data
@TableName("sys_user_custom_voice")
public class SysUserCustomVoiceEntity {

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
     * 音色名称
     */
    private String name;

    /**
     * 对应TTS模型（ai_model_config.id）
     */
    private String ttsModelId;

    /**
     * 音色编码
     */
    private String ttsVoice;

    /**
     * 语言
     */
    private String languages;

    /**
     * 参考音频路径
     */
    private String referenceAudio;

    /**
     * 参考文本
     */
    private String referenceText;

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
     * 状态（0停用 1正常）
     */
    private Integer status;

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

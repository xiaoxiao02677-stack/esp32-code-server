package yuhe.modules.sys.entity;

import java.io.Serializable;
import java.util.Date;

import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;

import lombok.Data;

/**
 * 用户自定义音色（表 sys_user_custom_voice；id 为 32 位短串非雪花）
 */
@Data
@TableName("sys_user_custom_voice")
public class SysUserCustomVoiceEntity implements Serializable {
    @TableId
    private String id;
    private Long userId;
    private String name;
    private String ttsModelId;
    private String ttsVoice;
    private String languages;
    private String referenceAudio;
    private String referenceText;
    /** 0 待审核 1 已通过 2 已驳回 */
    private Integer auditStatus;
    private String auditRemark;
    private Long auditor;
    private Date auditDate;
    private Integer status;
    private String remark;
    private Integer sort;
    private Long creator;
    private Date createDate;
    private Long updater;
    private Date updateDate;
}

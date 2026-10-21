package yuhe.modules.sys.entity;

import java.io.Serializable;
import java.util.Date;

import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;

import lombok.Data;

/**
 * 用户默认模型配置（表 sys_user_default；scope_type 0系统 1角色 2用户）
 */
@Data
@TableName("sys_user_default")
public class SysUserDefaultEntity implements Serializable {
    @TableId(type = IdType.ASSIGN_ID)
    private Long id;
    private Integer scopeType;
    private Long roleId;
    private Long userId;
    private String llmModelId;
    private String ttsModelId;
    private String ttsVoiceId;
    private String asrModelId;
    /** JSON 字符串透传（前端 save 时已 stringify）：{temperature,topP} */
    private String paramJson;
    /** 0 不锁定 1 锁定（用户不可自行修改）；前端发 boolean，Boolean 便于 Jackson/MyBatis 自动转换 */
    private Boolean lockPolicy;
    private Long creator;
    private Date createDate;
    private Long updater;
    private Date updateDate;
}

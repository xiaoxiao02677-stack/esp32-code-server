package xiaozhi.modules.sys.entity;

import com.baomidou.mybatisplus.annotation.TableName;

import lombok.Data;
import lombok.EqualsAndHashCode;
import xiaozhi.common.entity.BaseEntity;

/**
 * 默认模型/音色/参数配置（平台→角色→用户三级，冲突按 lock_policy）
 */
@Data
@EqualsAndHashCode(callSuper = false)
@TableName("sys_user_default")
public class SysUserDefaultEntity extends BaseEntity {
    /**
     * 作用域（0平台 1角色 2用户）
     */
    private Integer scopeType;
    /**
     * 角色ID（scope_type=1 有效，其余 0）
     */
    private Long roleId;
    /**
     * 用户ID（scope_type=2 有效，其余 0）
     */
    private Long userId;
    /**
     * 默认LLM（ai_model_config.id）
     */
    private String llmModelId;
    /**
     * 默认TTS模型（ai_model_config.id）
     */
    private String ttsModelId;
    /**
     * 默认音色（ai_tts_voice.id）
     */
    private String ttsVoiceId;
    /**
     * 默认ASR（ai_model_config.id）
     */
    private String asrModelId;
    /**
     * 参数模板 JSON（如 {"temperature":0.7,"top_p":0.9}）
     */
    private String paramJson;
    /**
     * 冲突策略（0可被下级覆盖 1锁定）
     */
    private Integer lockPolicy;
}

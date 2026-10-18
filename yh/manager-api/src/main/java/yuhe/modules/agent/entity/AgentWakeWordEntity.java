package yuhe.modules.agent.entity;

import java.util.Date;

import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;

import io.swagger.v3.oas.annotations.media.Schema;
import lombok.Data;

/**
 * 智能体唤醒词实体
 *
 * @author yuhe
 */
@Data
@TableName("ai_agent_wake_word")
@Schema(description = "智能体唤醒词配置")
public class AgentWakeWordEntity {

    @TableId(type = IdType.ASSIGN_UUID)
    @Schema(description = "主键")
    private String id;

    @Schema(description = "智能体ID（关联 ai_agent.id）")
    private String agentId;

    @Schema(description = "唤醒词列表 JSON，格式：{\"words\": [\"小智小智\", \"你好小智\"]}")
    private String wakeWords;

    @Schema(description = "创建者")
    private Long creator;

    @Schema(description = "创建时间")
    private Date createDate;

    @Schema(description = "更新者")
    private Long updater;

    @Schema(description = "更新时间")
    private Date updateDate;
}

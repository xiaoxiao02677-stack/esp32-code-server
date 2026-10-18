package yuhe.modules.agent.vo;

import io.swagger.v3.oas.annotations.media.Schema;
import lombok.Data;
import lombok.EqualsAndHashCode;
import yuhe.modules.agent.dto.ContextProviderDTO;
import yuhe.modules.agent.entity.AgentEntity;
import yuhe.modules.agent.entity.AgentPluginMapping;

import java.util.List;

/**
 * Agent信息返回体VO
 * 这里直接extend了Agent实体类AgentEntity，后续需要规范返回字段可以copy字段出来
 */
@EqualsAndHashCode(callSuper = true)
@Data
public class AgentInfoVO extends AgentEntity
{
    @Schema(description = "插件列表Id")
    private List<AgentPluginMapping> functions;

    @Schema(description = "上下文源配置")
    private List<ContextProviderDTO> contextProviders;

    @Schema(description = "替换词文件ID列表")
    private List<String> correctWordFileIds;

    @Schema(description = "当前配置版本号")
    private Integer currentVersionNo;

    @Schema(description = "唤醒词阈值（0~100，0=最灵敏）；取自绑定设备的 ai_device_config，无绑定设备/未设置时为 null")
    private Integer wakeWordThreshold;

    @Schema(description = "实时打断灵敏度（0~100，0=最灵敏/最容易打断）；取自绑定设备的 ai_device_config，未设置时为 null")
    private Integer interruptThreshold;

    @Schema(description = "实时打断一键开关（true=开启服务端打断，false=关闭）；取自绑定设备的 ai_device_config，未设置时为 null（默认开启）")
    private Boolean interruptEnabled;
}

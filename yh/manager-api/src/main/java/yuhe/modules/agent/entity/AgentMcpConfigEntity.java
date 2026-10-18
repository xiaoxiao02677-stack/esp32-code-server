package yuhe.modules.agent.entity;

import java.util.Date;

import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;

import io.swagger.v3.oas.annotations.media.Schema;
import lombok.Data;

/**
 * 智能体 MCP Server 配置实体
 *
 * @author yuhe
 */
@Data
@TableName("ai_agent_mcp_config")
@Schema(description = "智能体 MCP Server 配置")
public class AgentMcpConfigEntity {

    @TableId(type = IdType.ASSIGN_UUID)
    @Schema(description = "主键")
    private String id;

    @Schema(description = "智能体ID（关联 ai_agent.id）")
    private String agentId;

    @Schema(description = "配置别名（如 '搜索工具'）")
    private String name;

    /**
     * MCP server 配置 JSON，结构对齐 MCP spec：
     * {
     *   "mcpServers": {
     *     "server-name": {
     *       "command": "npx",
     *       "args": ["-y", "@modelcontextprotocol/server-filesystem", "/path"],
     *       "env": { "KEY": "VALUE" }
     *     }
     *   }
     * }
     */
    @Schema(description = "MCP server 配置 JSON")
    private String serverJson;

    @Schema(description = "是否启用（0=禁用，1=启用）")
    private Integer enabled;

    @Schema(description = "创建者")
    private Long creator;

    @Schema(description = "创建时间")
    private Date createDate;

    @Schema(description = "更新者")
    private Long updater;

    @Schema(description = "更新时间")
    private Date updateDate;
}

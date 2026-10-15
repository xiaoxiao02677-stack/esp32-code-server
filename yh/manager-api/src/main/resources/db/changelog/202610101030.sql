-- 智能体级 MCP Server 配置表
-- 背景：原 MCP 接入点是全局单点（sys_params.server.mcp_endpoint），无法满足多智能体各自挂载不同 MCP server 的需求。
--       本表 per-agent 存一份 JSON，由 AgentMcpConfigController 提供 CRUD，
--       AgentMcpAccessPointService 在生成接入点 URL 时优先读取本表（若存在则注入到 token 的 JSON 载荷中）。
CREATE TABLE IF NOT EXISTS `ai_agent_mcp_config` (
    `id`          VARCHAR(32)  NOT NULL COMMENT '主键（UUID）',
    `agent_id`    VARCHAR(32)  NOT NULL COMMENT '关联 ai_agent.id',
    `name`        VARCHAR(128) NOT NULL DEFAULT '' COMMENT '配置别名（如 "搜索工具""日历助手"）',
    `server_json` JSON         NOT NULL COMMENT 'MCP server 配置 JSON（与 MCP spec servers 字段对齐）',
    `enabled`     TINYINT(1)   NOT NULL DEFAULT 1 COMMENT '是否启用（0=禁用，1=启用）',
    `creator`     BIGINT       DEFAULT NULL COMMENT '创建者',
    `create_date` DATETIME     DEFAULT NULL COMMENT '创建时间',
    `updater`     BIGINT       DEFAULT NULL COMMENT '更新者',
    `update_date` DATETIME     DEFAULT NULL COMMENT '更新时间',
    PRIMARY KEY (`id`),
    UNIQUE KEY `uk_agent` (`agent_id`),
    KEY `idx_enabled` (`enabled`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='智能体 MCP Server 配置（per-agent JSON）';

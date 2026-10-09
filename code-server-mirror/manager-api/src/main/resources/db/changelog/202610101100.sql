-- 智能体级唤醒词配置表
-- 背景：支持为每个智能体自定义唤醒词（如"小智小智""你好小智"等），
--       唤醒词以 JSON 数组形式存储，由 AgentWakeWordController 提供 CRUD。
CREATE TABLE IF NOT EXISTS `ai_agent_wake_word` (
    `id`          VARCHAR(32)  NOT NULL COMMENT '主键（UUID）',
    `agent_id`    VARCHAR(32)  NOT NULL COMMENT '关联 ai_agent.id',
    `wake_words`  JSON         NOT NULL COMMENT '唤醒词列表 JSON，格式：{"words": ["小智小智", "你好小智"]}',
    `creator`     BIGINT       DEFAULT NULL COMMENT '创建者',
    `create_date` DATETIME     DEFAULT NULL COMMENT '创建时间',
    `updater`     BIGINT       DEFAULT NULL COMMENT '更新者',
    `update_date` DATETIME     DEFAULT NULL COMMENT '更新时间',
    PRIMARY KEY (`id`),
    UNIQUE KEY `uk_agent` (`agent_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='智能体唤醒词配置（per-agent）';

-- 智能体共享授权（ai_agent_share）
-- 说明：
--   1. 超级管理员在 /#/admin/agents 页面为某个智能体配置"谁能看到/使用"：
--      按用户共享（target_type=user）或按角色组共享（target_type=role）；
--   2. 生效范围：共享用户在顾客端可见该智能体及其绑定设备（只读使用，
--      不转移归属，编辑/删除仍归属主）；
--   3. 角色组复用 sys_role / sys_user_role 体系，不新建组概念。
CREATE TABLE IF NOT EXISTS `ai_agent_share` (
    `id`          BIGINT       NOT NULL AUTO_INCREMENT COMMENT '主键',
    `agent_id`    VARCHAR(32)  NOT NULL COMMENT '智能体ID（ai_agent.id）',
    `target_type` VARCHAR(16)  NOT NULL COMMENT '共享目标类型：user/role',
    `target_id`   BIGINT       NOT NULL COMMENT '目标ID：sys_user.id 或 sys_role.id',
    `creator`     BIGINT       DEFAULT NULL COMMENT '创建者',
    `create_date` DATETIME     DEFAULT NULL COMMENT '创建时间',
    PRIMARY KEY (`id`),
    UNIQUE KEY `uk_agent_target` (`agent_id`, `target_type`, `target_id`),
    KEY `idx_share_target` (`target_type`, `target_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='智能体共享授权表';

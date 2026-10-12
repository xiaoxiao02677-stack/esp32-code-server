-- 唤醒词自定义：ai_agent 增加 agent 级唤醒词列
-- 背景：全局唤醒词列表来自 sys_params 310 wakeup_words（分号分隔，经
--       ConfigServiceImpl.buildConfig 下发给 Python wakeup 加速链路）。
--       需求新增：允许用户在智能体上自定义唤醒词（默认「你好」），
--       下发时与全局列表合并（agent 词在前），故需要 per-agent 落库列。
-- 幂等：由 db.changelog-master.yaml 中本 changeSet 的 preConditions 保证 ——
--       MySQL 无 ADD COLUMN IF NOT EXISTS，若列已存在（如手工 ALTER 加过），
--       onFail=MARK_RAN 跳过，避免 Duplicate column 让 Spring Boot 启动失败。
--       写法参考 202610090130.sql。

ALTER TABLE `ai_agent`
ADD COLUMN `wake_words` VARCHAR(255) DEFAULT NULL COMMENT '智能体自定义唤醒词，分号分隔；为空则使用全局 wakeup_words' AFTER `summary_memory`;

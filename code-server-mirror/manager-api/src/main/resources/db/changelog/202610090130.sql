-- 音色「动态语气指令」落库字段
-- 背景：TimbreEntity.java:48,51 已声明 dynamicInstruction / instructionLlmId，
--       TimbreDataDTO / TimbreDetailsVO / VoiceDTO 也都有对应字段，
--       ConfigServiceImpl.java:559-563 还会把 dynamic_instruction / instruction_llm_id
--       下发给 Python；但 ai_tts_voice 表此前从未建这两列（202610070300.sql 只加了
--       voice_instruction）。
-- 后果：MyBatis-Plus 的 selectById / selectList 按实体字段拼 SELECT，
--       会抛 SQLSyntaxErrorException: Unknown column 'dynamic_instruction'，
--       使音色查询整条链路失败 —— 连带导致同一次查询里的 voice_instruction
--       （音色级语气指令）也取不到，表现为「指令不起作用/音色列表异常」。
-- 幂等：Liquibase changeSet 只执行一次。若目标库已手工建过这两列，
--       部署前请删除本文件或注释掉对应 ADD COLUMN 行（MySQL 无 ADD COLUMN IF NOT EXISTS）。

ALTER TABLE `ai_tts_voice`
ADD COLUMN `dynamic_instruction` TINYINT(1) DEFAULT 0 COMMENT '动态语气指令开关：开启后由LLM按聊天记录定制指令' AFTER `voice_instruction`,
ADD COLUMN `instruction_llm_id` VARCHAR(32) DEFAULT NULL COMMENT '动态指令生成LLM模型ID（为空则跟随智能体主LLM）' AFTER `dynamic_instruction`;

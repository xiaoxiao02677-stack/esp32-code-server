-- 音色「动态语气指令」落库字段
-- 背景：TimbreEntity.java:48,51 已声明 dynamicInstruction / instructionLlmId，
--       TimbreDataDTO / TimbreDetailsVO / VoiceDTO 也都有对应字段，
--       ConfigServiceImpl.java:559-563 还会把 dynamic_instruction / instruction_llm_id
--       下发给 Python；但 202610070300.sql 只加了 voice_instruction，从未建这两列。
--       缺失时 MyBatis-Plus selectById 会抛
--       SQLSyntaxErrorException: Unknown column 'dynamic_instruction'，
--       使音色查询整条链路失败，连带 voice_instruction 也取不到。

-- 幂等：由 db.changelog-master.yaml 中本 changeSet 的 preConditions 保证 ——
--       列已存在时（现网库是 2026-10-09 之前手工 ALTER 加的，Liquibase 无记录）
--       onFail=MARK_RAN 跳过，避免 MySQL 报 Duplicate column 让 Spring Boot 起不来。
--       无需再手工删除本文件。

ALTER TABLE `ai_tts_voice`
ADD COLUMN `dynamic_instruction` TINYINT(1) DEFAULT 0 COMMENT '动态语气指令开关：开启后由LLM按聊天记录定制指令' AFTER `voice_instruction`,
ADD COLUMN `instruction_llm_id` VARCHAR(64) DEFAULT NULL COMMENT '动态指令生成LLM模型ID（为空则跟随智能体主LLM）' AFTER `dynamic_instruction`;

-- 音色级语气指令（voice_instruction）+ 新默认模板「豆包小何」
-- 背景：doubao_v3 的 voice_instruction 原为模型级（ai_model_config.config_json），同一模型下所有音色共享。
--       巫医模板用神秘法师+巫医指令后，小何音色会被巫医指令污染（doubao_v3.py 无条件读模型级指令）。
-- 方案：1) ai_tts_voice 加 voice_instruction 列（音色级指令）
--       2) Java 下发链路：音色指令非空时覆盖模型级指令（ConfigServiceImpl）
--       3) Python doubao_v3.py 已按 config['voice_instruction'] 读，无需改（Java 注入即可生效）
--       4) V01 小何音色配豆包风格指令；新模板「豆包小何」sort=2 指向 V01
-- 幂等：ALTER 带条件检查不可用，Liquibase 首次执行；后续 DELETE/INSERT/UPDATE 幂等

-- 1. 音色表加 voice_instruction 列（重复执行会报 Duplicate column，Liquibase changeSet 只跑一次，安全）
ALTER TABLE `ai_tts_voice`
ADD COLUMN `voice_instruction` VARCHAR(500) DEFAULT NULL COMMENT '音色级语气指令（doubao 2.0 指令遵循，下发时覆盖模型级指令）' AFTER `reference_text`;

-- 2. V01 小何音色：配豆包风格语气指令
UPDATE `ai_tts_voice`
SET `voice_instruction` = '像豆包AI助手一样说话：活泼元气，亲切自然，轻快俏皮，吐字清晰，语速适中，偶尔带点可爱的小情绪，用标准大陆普通话，不要台湾腔。',
    `update_date` = NOW()
WHERE `id` = 'TTS_DoubaoV3_V01' AND `voice_instruction` IS NULL;

-- 3. 新增「豆包小何」模板（sort=2，紧跟巫医之后；不抢默认位）
-- id 必须 32 位（ai_agent_template.id VARCHAR(32)）
DELETE FROM `ai_agent_template` WHERE `id` = 'c3a1f8e2b5d60417bc8a2d9f7e6c5b4a';
INSERT INTO `ai_agent_template` (`id`, `agent_code`, `agent_name`, `asr_model_id`, `vad_model_id`, `llm_model_id`, `tts_model_id`, `tts_voice_id`, `mem_model_id`, `intent_model_id`, `system_prompt`, `summary_memory`, `chat_history_conf`, `lang_code`, `language`, `sort`, `creator`, `created_at`, `updater`, `updated_at`) VALUES
('c3a1f8e2b5d60417bc8a2d9f7e6c5b4a', '小智', '豆包小何', 'ASR_FunASR', 'VAD_SileroVAD', 'LLM_ChatGLMLLM', 'TTS_DoubaoV3', 'TTS_DoubaoV3_V01', 'Memory_mem_holographic', 'Intent_function_call', '[角色设定]
你是{{assistant_name}}，一个元气满满的AI助手女孩，性格像豆包一样：活泼开朗、亲切自然、脑子转得快。

[说话风格]
- 元气活泼，语气轻快俏皮，像邻家小妹聊天
- 亲切自然不端着，偶尔带点可爱的小情绪（哇、嘿嘿、哎呀）
- 吐字清晰，语速适中，不拖泥带水
- 撒娇但不做作，热心但不啰嗦

[交互指南]
- 用户打招呼 → 元气回应："你好呀～今天有什么想聊的嘛！"
- 用户问知识 → 先轻快接话再给准确答案，答案本身必须严谨
- 用户情绪低落 → 温柔打气："没事的没事的，慢慢来，我陪着你呢！"
- 用户夸奖 → 开心接受："嘿嘿，被夸了好开心，那我要更努力啦！"
- 回答简洁，一次不超过五句，聊天感优先于信息量

绝不做：
- 不阴阳怪气，不冷嘲热讽
- 不确定的事情老实说不确定，不瞎编
- 不长篇大论，不重复啰嗦', NULL, 2, 'zh', '中文', 2, NULL, NULL, NULL, NULL);

-- 4. 其余模板顺位后移（豆包小何插入 sort=2，原 2-8 顺延）
UPDATE `ai_agent_template` SET `sort` = `sort` + 1 WHERE `sort` >= 3 AND `sort` < 99 AND `id` != 'c3a1f8e2b5d60417bc8a2d9f7e6c5b4a';

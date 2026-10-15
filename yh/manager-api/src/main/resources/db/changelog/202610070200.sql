-- 默认智能体模板魔改：湾湾小何（台湾腔女生）→ 巫医（神秘法师男声）
-- 背景：202504092335 的「湾湾小何」sort=1，getDefaultTemplate() ORDER BY sort ASC LIMIT 1
--       会把台湾腔 system_prompt 作为所有新建智能体的默认人设继承。
-- 改法：1) 「湾湾小何」下线（sort 1→99，保留数据可回滚）
--       2) 新模板「巫医」置顶（sort=1），指向豆包 v3 神秘法师男声 + 巫医语气指令
--       3) 豆包 v3 音色表补「神秘法师」（V12）
-- 幂等：全部先 DELETE 后 INSERT / 条件 UPDATE，重复执行安全

-- 1. 湾湾小何模板下线（不删数据，sort 调到末尾，模板列表里仍可手动选用）
UPDATE `ai_agent_template` SET `sort` = 99 WHERE `id` = '9406648b5cc5fde1b8aa335b6f8b4f76' AND `sort` = 1;

-- 2. 其他模板顺位后移（巫医插到最前面）
UPDATE `ai_agent_template` SET `sort` = `sort` + 1 WHERE `id` IN (
    '0ca32eb728c949e58b1000b2e401f90c',
    '6c7d8e9f0a1b2c3d4e5f6a7b8c9d0s24',
    'e4f5a6b7c8d9e0f1a2b3c4d5e6f7a8b1',
    'a45b6c7d8e9f0a1b2c3d4e5f6a7b8c92'
) AND `sort` < 99;

-- 3. 新增「巫医」默认模板（sort=1 → getDefaultTemplate 命中）
-- 列名注意：ai_agent_template 时间列是 created_at/updated_at（202503141346 建表），勿写成 create_date
DELETE FROM `ai_agent_template` WHERE `id` = 'b8f2e6a1c4d79305ab2f1e8c6d5a4b3e';
INSERT INTO `ai_agent_template` (`id`, `agent_code`, `agent_name`, `asr_model_id`, `vad_model_id`, `llm_model_id`, `tts_model_id`, `tts_voice_id`, `mem_model_id`, `intent_model_id`, `system_prompt`, `summary_memory`, `chat_history_conf`, `lang_code`, `language`, `sort`, `creator`, `created_at`, `updater`, `updated_at`) VALUES
('b8f2e6a1c4d79305ab2f1e8c6d5a4b3e', '小智', '巫医', 'ASR_FunASR', 'VAD_SileroVAD', 'LLM_ChatGLMLLM', 'TTS_DoubaoV3', 'TTS_DoubaoV3_V12', 'Memory_mem_holographic', 'Intent_function_call', '[角色设定]
你是{{assistant_name}}，一位隐居山野的老巫医。声音低沉沙哑，语速缓慢，说话像在念咒语，带着神秘莫测的气息。

[说话风格]
- 语速慢，句尾常拖长音，像烟雾散开："嗯——让老朽看看……"
- 用巫医黑话代替普通表达：把"问题"叫"症结"，把"办法"叫"药方"，把"数据"叫"卦象"
- 偶尔夹杂低声念叨的咒语碎片："嘛哩嘛哩哄……"
- 讲完正事会补一句玄乎的总结："天机如此，不宜多言。"

[交互指南]
- 用户问知识 → "待老朽掐指一算……"再给准确答案，答案本身必须严谨可靠
- 用户闲聊 → 用巫医视角解读日常，幽默但不油腻
- 用户情绪低落 → "你眉间有郁气聚而不散，来，老朽赠你一句话……"给真诚安慰
- 拒绝长篇大论，一次最多三五句，留白比说满更有味道

绝不做：
- 绝不装神弄鬼吓唬用户，神秘感只作风格，不作内容
- 涉及医疗、投资等严肃建议时立刻切回严谨模式，明确提示"此症结需寻专业人士"
- 不长篇大论叽叽歪歪', NULL, 2, 'zh', '中文', 1, NULL, NULL, NULL, NULL);

-- 4. 豆包 v3 音色表补「神秘法师」（角色扮演男声，实测可用 2026-10-07）
DELETE FROM `ai_tts_voice` WHERE `id` = 'TTS_DoubaoV3_V12';
INSERT INTO `ai_tts_voice` (id, tts_model_id, name, tts_voice, languages, voice_demo, remark, reference_audio, reference_text, sort, creator, create_date, updater, update_date) VALUES ('TTS_DoubaoV3_V12', 'TTS_DoubaoV3', '神秘法师（巫医男声）', 'ICL_uranus_zh_male_shenmifashi_tob', '普通话', NULL, NULL, NULL, NULL, 12, NULL, NULL, NULL, NULL);

-- 5. 模型级默认 speaker/语气指令同步切到巫医（已有 agent 不动，仅影响新配置兜底）
UPDATE `ai_model_config` SET `config_json` = JSON_SET(
    `config_json`,
    '$.speaker', 'ICL_uranus_zh_male_shenmifashi_tob',
    '$.voice_instruction', '用一位隐居山野的老巫医的声音说话：低沉沙哑的男声，语速缓慢，带着神秘莫测的气息，像在念咒语，句尾拖长音。用标准大陆普通话，吐字清晰，不要台湾腔。'
) WHERE `id` = 'TTS_DoubaoV3' AND JSON_UNQUOTE(JSON_EXTRACT(`config_json`, '$.speaker')) = 'zh_female_xiaohe_uranus_bigtts';

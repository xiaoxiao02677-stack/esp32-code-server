-- 新增千问TTS供应器（provider_code=qwen_tts，对应 Python core/providers/tts/qwen_tts.py）
-- 幂等写法：先删后插，重复执行安全
DELETE FROM `ai_model_provider` WHERE `id` = 'SYSTEM_TTS_qwen_tts';
INSERT INTO `ai_model_provider` (`id`, `model_type`, `provider_code`, `name`, `fields`, `sort`, `creator`, `create_date`, `updater`, `update_date`)
VALUES ('SYSTEM_TTS_qwen_tts', 'TTS', 'qwen_tts', '千问TTS', '[{"key":"api_key","label":"API密钥","type":"password"},{"key":"model","label":"模型","type":"string"},{"key":"voice","label":"音色","type":"string"},{"key":"format","label":"音频格式","type":"string"},{"key":"sample_rate","label":"采样率","type":"number"},{"key":"instructions","label":"指令(可选)","type":"string"},{"key":"output_dir","label":"输出目录","type":"string"}]', 21, 1, NOW(), 1, NOW());

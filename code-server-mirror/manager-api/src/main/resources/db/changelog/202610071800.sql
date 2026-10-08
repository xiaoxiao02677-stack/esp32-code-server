-- 千问ASR接入修正（用户授权 key，2026-10-07 实测 qwen-audio-3.1-asr-flash 同步端点可用）
-- 背景：ASR_Qwen3Flash 种子（202509091633）指向旧 dashscope SDK 形态 + qwen3-asr-flash 模型，
--   该形态在 maas.qianwenaiapi.com 平台实测 400（messages 结构不被接受）。
--   Python provider core/providers/asr/qwen3_asr_flash.py 已重写为 REST 同步端点
--   （/services/aigc/multimodal-generation/generation，input.messages + input_audio base64 内联）。
-- 本文件把既有 ASR_Qwen3Flash 行的 config_json 修正为实测可用参数并写入真实 key。
-- 幂等：按 id 全量 REPLACE。

DELETE FROM `ai_model_config` WHERE `id` = 'ASR_Qwen3Flash';
INSERT INTO `ai_model_config` (`id`, `model_type`, `model_code`, `model_name`, `is_default`, `is_enabled`, `config_json`, `doc_link`, `remark`, `sort`, `creator`, `create_date`, `updater`, `update_date`)
VALUES ('ASR_Qwen3Flash', 'ASR', 'QwenAudioASR', '千问语音识别(多语种)', 0, 1,
'{"type": "qwen3_asr_flash", "api_key": "sk-ws-H.PEMIMYH.3cGK.MEYCIQCw6BBYZA2dDt3njtSBqRPdACjCo3cL6wj-nbbPv3MIEgIhAPgFWG9ewJg1rsJ1e3qC50RAI_he0bK1Wa2WuRlUW9rk", "model_name": "qwen-audio-3.1-asr-flash", "format": "wav", "sample_rate": 16000, "output_dir": "tmp/"}',
'https://platform.qianwenai.com/docs/developer-guides/speech/asr',
'千问平台同步ASR端点，支持多语种/中英混说，音频≤5分钟；模型可换 qwen-audio-3.0-asr-flash',
21, NULL, NULL, NULL, NULL);

-- 供应器 fields 补充 format/sample_rate/timeout（保持与 provider 读取一致）
DELETE FROM `ai_model_provider` WHERE `id` = 'SYSTEM_ASR_Qwen3Flash';
INSERT INTO `ai_model_provider` (`id`, `model_type`, `provider_code`, `name`, `fields`, `sort`, `creator`, `create_date`, `updater`, `update_date`)
VALUES ('SYSTEM_ASR_Qwen3Flash', 'ASR', 'qwen3_asr_flash', '千问语音识别', '[{"key":"api_key","label":"API密钥","type":"password"},{"key":"model_name","label":"模型名称","type":"string"},{"key":"format","label":"音频格式","type":"string"},{"key":"sample_rate","label":"采样率","type":"number"},{"key":"timeout","label":"超时秒数","type":"number"},{"key":"output_dir","label":"输出目录","type":"string"}]', 17, 1, NOW(), 1, NOW());

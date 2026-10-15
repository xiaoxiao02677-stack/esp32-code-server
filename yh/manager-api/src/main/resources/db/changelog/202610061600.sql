-- 预置千问TTS模型配置（对应 Python core/providers/tts/qwen_tts.py，provider 种子见 202610061500.sql 的 qwen_tts）
-- config_json 中 type=qwen_tts 为 Python 侧加载入口（core/utils/tts.py create_instance）按 type 匹配 provider 文件
-- is_default=0：不抢占用户现有默认TTS；api_key 为中文占位，用户在控制台点编辑即可填入
-- sort 取值：现库 TTS 最大 sort=23（TTS_XunFeiStreamTTS，202509191545），新条目顺延 24~27
-- 幂等写法：每条先 DELETE 再 INSERT，重复执行安全

-- 1. 千问TTS-Flash：qwen3-tts-flash，48音色，推荐默认
DELETE FROM `ai_model_config` WHERE `id` = 'TTS_QwenTTS_Flash';
INSERT INTO `ai_model_config` (`id`, `model_type`, `model_code`, `model_name`, `is_default`, `is_enabled`, `config_json`, `doc_link`, `remark`, `sort`, `creator`, `create_date`, `updater`, `update_date`)
VALUES ('TTS_QwenTTS_Flash', 'TTS', 'QwenTTSFlash', '千问TTS-Flash(48音色)', 0, 1, '{"type": "qwen_tts", "api_key": "请填入千问API密钥", "model": "qwen3-tts-flash", "voice": "Cherry", "format": "wav", "sample_rate": 24000, "output_dir": "tmp/"}', 'https://platform.qianwenai.com/docs/developer-guides/speech/tts', NULL, 24, NULL, NULL, NULL, NULL);

-- 2. 千问TTS-Instruct：qwen3-tts-instruct-flash，24音色，支持 instructions 指令控制
DELETE FROM `ai_model_config` WHERE `id` = 'TTS_QwenTTS_Instruct';
INSERT INTO `ai_model_config` (`id`, `model_type`, `model_code`, `model_name`, `is_default`, `is_enabled`, `config_json`, `doc_link`, `remark`, `sort`, `creator`, `create_date`, `updater`, `update_date`)
VALUES ('TTS_QwenTTS_Instruct', 'TTS', 'QwenTTSInstruct', '千问TTS-Instruct(24音色+指令)', 0, 1, '{"type": "qwen_tts", "api_key": "请填入千问API密钥", "model": "qwen3-tts-instruct-flash", "voice": "Cherry", "format": "wav", "sample_rate": 24000, "output_dir": "tmp/"}', 'https://platform.qianwenai.com/docs/developer-guides/speech/tts', NULL, 25, NULL, NULL, NULL, NULL);

-- 3. 千问Audio-Flash：qwen-audio-3.0-tts-flash，12音色
DELETE FROM `ai_model_config` WHERE `id` = 'TTS_QwenAudio_Flash';
INSERT INTO `ai_model_config` (`id`, `model_type`, `model_code`, `model_name`, `is_default`, `is_enabled`, `config_json`, `doc_link`, `remark`, `sort`, `creator`, `create_date`, `updater`, `update_date`)
VALUES ('TTS_QwenAudio_Flash', 'TTS', 'QwenAudioFlash', '千问Audio-Flash(12音色)', 0, 1, '{"type": "qwen_tts", "api_key": "请填入千问API密钥", "model": "qwen-audio-3.0-tts-flash", "voice": "longanhuan_v3.6", "format": "wav", "sample_rate": 24000, "output_dir": "tmp/"}', 'https://platform.qianwenai.com/docs/developer-guides/speech/tts', NULL, 26, NULL, NULL, NULL, NULL);

-- 4. 千问Audio-Plus：qwen-audio-3.0-tts-plus，旗舰14音色
DELETE FROM `ai_model_config` WHERE `id` = 'TTS_QwenAudio_Plus';
INSERT INTO `ai_model_config` (`id`, `model_type`, `model_code`, `model_name`, `is_default`, `is_enabled`, `config_json`, `doc_link`, `remark`, `sort`, `creator`, `create_date`, `updater`, `update_date`)
VALUES ('TTS_QwenAudio_Plus', 'TTS', 'QwenAudioPlus', '千问Audio-Plus(旗舰)', 0, 1, '{"type": "qwen_tts", "api_key": "请填入千问API密钥", "model": "qwen-audio-3.0-tts-plus", "voice": "longanlingxin", "format": "wav", "sample_rate": 24000, "output_dir": "tmp/"}', 'https://platform.qianwenai.com/docs/developer-guides/speech/tts', NULL, 27, NULL, NULL, NULL, NULL);

-- 千问TTS预置配置写入真实API密钥（用户授权 key，4 组合实测可用 2026-10-06：qwen3-tts-flash+Cherry / instruct-flash+Cherry / qwen-audio-3.0-tts-flash+longanhuan_v3.6 / plus+longanlingxin）
-- 本文件是 202610061600.sql 的增量：1600 已在生产执行（checksum 锁定不可改），故用 UPDATE 把占位符替换为真实 key
-- 幂等写法：JSON_SET 局部替换，重复执行结果一致

-- 1. 千问TTS-Flash
UPDATE `ai_model_config`
SET `config_json` = JSON_SET(`config_json`, '$.api_key', 'sk-ws-H.PRYRHYR.61vN.MEUCIQCjPmFSRlwpG99RpGCPG0B0KPWVLDEYlPaPtCgyVF5xJQIgVvM9rKWQFScZkGE9TIlpryvhXXkZIdjtNUSVocT91As'),
    `update_date` = NOW()
WHERE `id` = 'TTS_QwenTTS_Flash' AND JSON_UNQUOTE(JSON_EXTRACT(`config_json`, '$.api_key')) = '请填入千问API密钥';

-- 2. 千问TTS-Instruct
UPDATE `ai_model_config`
SET `config_json` = JSON_SET(`config_json`, '$.api_key', 'sk-ws-H.PRYRHYR.61vN.MEUCIQCjPmFSRlwpG99RpGCPG0B0KPWVLDEYlPaPtCgyVF5xJQIgVvM9rKWQFScZkGE9TIlpryvhXXkZIdjtNUSVocT91As'),
    `update_date` = NOW()
WHERE `id` = 'TTS_QwenTTS_Instruct' AND JSON_UNQUOTE(JSON_EXTRACT(`config_json`, '$.api_key')) = '请填入千问API密钥';

-- 3. 千问Audio-Flash
UPDATE `ai_model_config`
SET `config_json` = JSON_SET(`config_json`, '$.api_key', 'sk-ws-H.PRYRHYR.61vN.MEUCIQCjPmFSRlwpG99RpGCPG0B0KPWVLDEYlPaPtCgyVF5xJQIgVvM9rKWQFScZkGE9TIlpryvhXXkZIdjtNUSVocT91As'),
    `update_date` = NOW()
WHERE `id` = 'TTS_QwenAudio_Flash' AND JSON_UNQUOTE(JSON_EXTRACT(`config_json`, '$.api_key')) = '请填入千问API密钥';

-- 4. 千问Audio-Plus
UPDATE `ai_model_config`
SET `config_json` = JSON_SET(`config_json`, '$.api_key', 'sk-ws-H.PRYRHYR.61vN.MEUCIQCjPmFSRlwpG99RpGCPG0B0KPWVLDEYlPaPtCgyVF5xJQIgVvM9rKWQFScZkGE9TIlpryvhXXkZIdjtNUSVocT91As'),
    `update_date` = NOW()
WHERE `id` = 'TTS_QwenAudio_Plus' AND JSON_UNQUOTE(JSON_EXTRACT(`config_json`, '$.api_key')) = '请填入千问API密钥';

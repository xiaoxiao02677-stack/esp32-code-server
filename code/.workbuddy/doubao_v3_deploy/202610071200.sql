-- 豆包语音合成大模型 v3 HTTP 一次性合成（provider_code=doubao_v3，对应 Python core/providers/tts/doubao_v3.py）
-- 端点 POST /api/v3/tts/unidirectional；旧版控制台双头鉴权（appid+access_token），api_key 备用（新版单头）
-- 凭据 2026-10-06 实测可用（curl 200 + 12/12 契约单测 + 真机合成验证）
-- 幂等：全部先 DELETE 后 INSERT / 条件 UPDATE，重复执行安全

DELETE FROM `ai_model_provider` WHERE `id` = 'SYSTEM_TTS_doubao_v3';
INSERT INTO `ai_model_provider` (`id`, `model_type`, `provider_code`, `name`, `fields`, `sort`, `creator`, `create_date`, `updater`, `update_date`) VALUES
('SYSTEM_TTS_doubao_v3', 'TTS', 'doubao_v3', '豆包语音合成v3', '[{"key":"appid","label":"应用ID","type":"string"},{"key":"access_token","label":"访问令牌","type":"password"},{"key":"api_key","label":"API Key(新版备用)","type":"password"},{"key":"resource_id","label":"资源ID","type":"string"},{"key":"api_url","label":"服务地址","type":"string"},{"key":"speaker","label":"默认音色","type":"string"},{"key":"format","label":"音频格式","type":"string"},{"key":"sample_rate","label":"采样率","type":"number"},{"key":"speech_rate","label":"语速(-50~100)","type":"number"},{"key":"loudness_rate","label":"音量(-50~100)","type":"number"},{"key":"output_dir","label":"输出目录","type":"string"}]', 22, 1, NOW(), 1, NOW());

DELETE FROM `ai_model_config` WHERE `id` = 'TTS_DoubaoV3';
INSERT INTO `ai_model_config` (`id`, `model_type`, `model_code`, `model_name`, `is_default`, `is_enabled`, `config_json`, `doc_link`, `remark`, `sort`, `creator`, `create_date`, `updater`, `update_date`) VALUES
('TTS_DoubaoV3', 'TTS', 'DoubaoV3', '豆包语音合成v3(HTTP)', 0, 1, '{"type": "doubao_v3", "appid": "2717008086", "access_token": "W6P9P9w4FNK9qtTWHTQlokkmFRm-GZCa", "api_key": "d9f77dba-01ca-47fa-a4d3-7002adf6b6a4", "resource_id": "seed-tts-2.0", "api_url": "https://openspeech.bytedance.com/api/v3/tts/unidirectional", "speaker": "zh_female_xiaohe_uranus_bigtts", "format": "wav", "sample_rate": 24000, "speech_rate": 0, "loudness_rate": 0, "output_dir": "tmp/"}', 'https://www.volcengine.com/docs/6561/1329505', '豆包语音合成大模型 v3 HTTP 一次性合成端点。\n1. 鉴权默认走旧版双头（应用ID+访问令牌），api_key 为新版控制台备用\n2. SecretKey 仅用于控制台签名场景，本端点无需填写\n3. 音色在音色管理中选择，语速/音量范围[-50,100]', 28, NULL, NULL, NULL, NULL);

-- 默认音色（豆包 2.0 精选，音色管理弹窗可选）
DELETE FROM `ai_tts_voice` WHERE `tts_model_id` = 'TTS_DoubaoV3';
INSERT INTO `ai_tts_voice` (id, tts_model_id, name, tts_voice, languages, voice_demo, remark, reference_audio, reference_text, sort, creator, create_date, updater, update_date) VALUES ('TTS_DoubaoV3_V01', 'TTS_DoubaoV3', '小何（温柔女声）', 'zh_female_xiaohe_uranus_bigtts', '普通话', NULL, NULL, NULL, NULL, 1, NULL, NULL, NULL, NULL);
INSERT INTO `ai_tts_voice` (id, tts_model_id, name, tts_voice, languages, voice_demo, remark, reference_audio, reference_text, sort, creator, create_date, updater, update_date) VALUES ('TTS_DoubaoV3_V02', 'TTS_DoubaoV3', '高冷御姐（御姐女声）', 'zh_female_gaolengyujie_uranus_bigtts', '普通话', NULL, NULL, NULL, NULL, 2, NULL, NULL, NULL, NULL);
INSERT INTO `ai_tts_voice` (id, tts_model_id, name, tts_voice, languages, voice_demo, remark, reference_audio, reference_text, sort, creator, create_date, updater, update_date) VALUES ('TTS_DoubaoV3_V03', 'TTS_DoubaoV3', 'VV（多方言女声）', 'zh_female_vv_uranus_bigtts', '方言', NULL, NULL, NULL, NULL, 3, NULL, NULL, NULL, NULL);
INSERT INTO `ai_tts_voice` (id, tts_model_id, name, tts_voice, languages, voice_demo, remark, reference_audio, reference_text, sort, creator, create_date, updater, update_date) VALUES ('TTS_DoubaoV3_V04', 'TTS_DoubaoV3', '少儿故事（讲故事女声）', 'zh_female_shaoergushi_uranus_bigtts', '普通话', NULL, NULL, NULL, NULL, 4, NULL, NULL, NULL, NULL);
INSERT INTO `ai_tts_voice` (id, tts_model_id, name, tts_voice, languages, voice_demo, remark, reference_audio, reference_text, sort, creator, create_date, updater, update_date) VALUES ('TTS_DoubaoV3_V05', 'TTS_DoubaoV3', '魅力女友（甜美女声）', 'zh_female_meilinvyou_uranus_bigtts', '普通话', NULL, NULL, NULL, NULL, 5, NULL, NULL, NULL, NULL);

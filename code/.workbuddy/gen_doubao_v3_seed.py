#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""生成豆包 v3 TTS 种子 changelog SQL（程序化生成，避免手工笔误）。

数据来源：
- Provider 契约：core/providers/tts/doubao_v3.py（端点/鉴权/参数）
- 音色：豆包语音合成大模型 2.0 常用音色表（volcengine docs 6561/1257544）
- 凭据：用户提供（appid/access_token/api_key，2026-10-06 实测可用）
"""
import io

# 豆包音色（voice_code, 名称, 语种）
# 2026-10-06 用户提供账号实际音色清单（控制台音色库），11 个全部实测可用（seed-tts-2.0）；
# 含 3 个 ICL 声音复刻音色（_tob 后缀），同走 seed-tts-2.0 资源
DOUBAO_V3_VOICES = [
    ("zh_female_xiaohe_uranus_bigtts", "小何（温柔女声）", "普通话"),
    ("zh_female_sophie_uranus_bigtts", "Sophie（知性女声）", "普通话"),
    ("zh_female_peiqi_uranus_bigtts", "佩琪（甜美女声）", "普通话"),
    ("zh_female_jitangmei_uranus_bigtts", "鸡汤妹（治愈女声）", "普通话"),
    ("zh_female_wenjingmaomao_uranus_bigtts", "文静毛毛（轻柔女声）", "普通话"),
    ("zh_female_qinqienv_uranus_bigtts", "亲情女（温暖女声）", "普通话"),
    ("zh_female_zhishuaiyingzi_uranus_bigtts", "智帅影子（干练女声）", "普通话"),
    ("zh_female_nvleishen_uranus_bigtts", "女雷神（霸气女声）", "普通话"),
    ("ICL_uranus_zh_female_chunzhenshaonv_tob", "纯真少女（复刻音色）", "普通话"),
    ("ICL_uranus_zh_female_chengshujiejie_tob", "成熟姐姐（复刻音色）", "普通话"),
    ("ICL_uranus_zh_female_bingjiaojiejie_tob", "病娇姐姐（复刻音色）", "普通话"),
]

MODEL_ID = "TTS_DoubaoV3"
PROVIDER_ID = "SYSTEM_TTS_doubao_v3"
PROVIDER_CODE = "doubao_v3"

DEFAULT_VOICE_INSTRUCTION = (
    "像豆包AI助手一样说话，活泼元气，亲切自然，轻快俏皮，"
    "吐字清晰，用标准大陆普通话，不要台湾腔"
)

APPID = "2717008086"
ACCESS_TOKEN = "W6P9P9w4FNK9qtTWHTQlokkmFRm-GZCa"
API_KEY = "d9f77dba-01ca-47fa-a4d3-7002adf6b6a4"
DEFAULT_SPEAKER = "zh_female_xiaohe_uranus_bigtts"


def sql_quote(value):
    if value is None:
        return "NULL"
    escaped = str(value).replace("\\", "\\\\").replace("'", "''")
    return f"'{escaped}'"


def main():
    out = io.StringIO()
    w = out.write
    w("-- 豆包语音合成大模型 v3 HTTP 一次性合成（provider_code=doubao_v3，对应 Python core/providers/tts/doubao_v3.py）\n")
    w("-- 端点 POST /api/v3/tts/unidirectional；旧版控制台双头鉴权（appid+access_token），api_key 备用（新版单头）\n")
    w("-- 凭据 2026-10-06 实测可用（curl 200 + 12/12 契约单测 + 真机合成验证）\n")
    w("-- 幂等：全部先 DELETE 后 INSERT / 条件 UPDATE，重复执行安全\n\n")

    # provider
    fields = (
        '[{"key":"appid","label":"应用ID","type":"string"},'
        '{"key":"access_token","label":"访问令牌","type":"password"},'
        '{"key":"api_key","label":"API Key(新版备用)","type":"password"},'
        '{"key":"resource_id","label":"资源ID","type":"string"},'
        '{"key":"api_url","label":"服务地址","type":"string"},'
        '{"key":"speaker","label":"默认音色","type":"string"},'
        '{"key":"voice_instruction","label":"语气指令(2.0音色)","type":"string"},'
        '{"key":"format","label":"音频格式","type":"string"},'
        '{"key":"sample_rate","label":"采样率","type":"number"},'
        '{"key":"speech_rate","label":"语速(-50~100)","type":"number"},'
        '{"key":"loudness_rate","label":"音量(-50~100)","type":"number"},'
        '{"key":"output_dir","label":"输出目录","type":"string"}]'
    )
    w(f"DELETE FROM `ai_model_provider` WHERE `id` = '{PROVIDER_ID}';\n")
    w(f"INSERT INTO `ai_model_provider` (`id`, `model_type`, `provider_code`, `name`, `fields`, `sort`, `creator`, `create_date`, `updater`, `update_date`) VALUES\n")
    w(f"('{PROVIDER_ID}', 'TTS', '{PROVIDER_CODE}', '豆包语音合成v3', {sql_quote(fields)}, 22, 1, NOW(), 1, NOW());\n\n")

    # model config（api_key 留空 → 走旧版双头鉴权，与实测一致；secret_key 备注记录）
    # voice_instruction：2.0 音色指令遵循（用户验收 B 方案），消除默认演绎的软萌腔
    config_json = (
        '{"type": "doubao_v3", "appid": "' + APPID + '", '
        '"access_token": "' + ACCESS_TOKEN + '", '
        '"api_key": "' + API_KEY + '", '
        '"resource_id": "seed-tts-2.0", '
        '"api_url": "https://openspeech.bytedance.com/api/v3/tts/unidirectional", '
        '"speaker": "' + DEFAULT_SPEAKER + '", '
        '"voice_instruction": "' + DEFAULT_VOICE_INSTRUCTION + '", '
        '"format": "wav", "sample_rate": 24000, '
        '"speech_rate": 0, "loudness_rate": 0, "output_dir": "tmp/"}'
    )
    w(f"DELETE FROM `ai_model_config` WHERE `id` = '{MODEL_ID}';\n")
    w(f"INSERT INTO `ai_model_config` (`id`, `model_type`, `model_code`, `model_name`, `is_default`, `is_enabled`, `config_json`, `doc_link`, `remark`, `sort`, `creator`, `create_date`, `updater`, `update_date`) VALUES\n")
    w(f"('{MODEL_ID}', 'TTS', 'DoubaoV3', '豆包语音合成v3(HTTP)', 0, 1, {sql_quote(config_json)}, 'https://www.volcengine.com/docs/6561/1329505', ")
    w("'豆包语音合成大模型 v3 HTTP 一次性合成端点。\\n"
      "1. 鉴权默认走旧版双头（应用ID+访问令牌），api_key 为新版控制台备用\\n"
      "2. SecretKey 仅用于控制台签名场景，本端点无需填写\\n"
      "3. 音色在音色管理中选择，语速/音量范围[-50,100]', ")
    w("28, NULL, NULL, NULL, NULL);\n\n")

    # voices
    w("-- 默认音色（豆包 2.0 精选，音色管理弹窗可选）\n")
    w(f"DELETE FROM `ai_tts_voice` WHERE `tts_model_id` = '{MODEL_ID}';\n")
    cols = ("id, tts_model_id, name, tts_voice, languages, voice_demo, "
            "remark, reference_audio, reference_text, sort, creator, "
            "create_date, updater, update_date")
    for idx, (code, name, lang) in enumerate(DOUBAO_V3_VOICES, start=1):
        row_id = f"{MODEL_ID}_V{idx:02d}"
        vals = ", ".join([
            sql_quote(row_id), sql_quote(MODEL_ID), sql_quote(name),
            sql_quote(code), sql_quote(lang), "NULL", "NULL", "NULL",
            "NULL", str(idx), "NULL", "NULL", "NULL", "NULL",
        ])
        w(f"INSERT INTO `ai_tts_voice` ({cols}) VALUES ({vals});\n")

    path = ("G:/demo/21_xiaozhi/code-server-mirror/manager-api/src/main/resources/"
            "db/changelog/202610071200.sql")
    with io.open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(out.getvalue())
    print(f"written: {path}")
    print(f"voices: {len(DOUBAO_V3_VOICES)}")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""生成千问TTS默认音色 changelog SQL（程序化生成，避免手工笔误）。

音色数据来源（两处已对齐，本脚本为唯一生成源）：
- Python  core/providers/tts/qwen_tts.py  QWEN_TTS_VOICES
- 前端    manager-web/src/constants/qwenTtsVoices.js
"""
import io

BASE_URL = "https://maas.qianwenaiapi.com/compatible-mode/v1"
# (voice_code, 中文名/标签, 语种分组)
FLASH_VOICES = [
    ("Cherry", "Cherry（芊悦）", "普通话"),
    ("Serena", "Serena（苏瑶）", "普通话"),
    ("Ethan", "Ethan（晨煦）", "普通话"),
    ("Chelsie", "Chelsie（千雪）", "普通话"),
    ("Momo", "Momo（茉兔）", "普通话"),
    ("Vivian", "Vivian（十三）", "普通话"),
    ("Moon", "Moon（月白）", "普通话"),
    ("Maia", "Maia（四月）", "普通话"),
    ("Kai", "Kai（凯）", "普通话"),
    ("Nofish", "Nofish（不吃鱼）", "普通话"),
    ("Bella", "Bella（萌宝）", "普通话"),
    ("Jennifer", "Jennifer（詹妮弗）", "国际音色"),
    ("Ryan", "Ryan（甜茶）", "国际音色"),
    ("Katerina", "Katerina（卡捷琳娜）", "国际音色"),
    ("Aiden", "Aiden（艾登）", "国际音色"),
    ("Eldric Sage", "Eldric Sage（沧明子）", "普通话"),
    ("Mia", "Mia（乖小妹）", "普通话"),
    ("Mochi", "Mochi（沙小弥）", "普通话"),
    ("Bellona", "Bellona（燕铮莺）", "普通话"),
    ("Vincent", "Vincent（田叔）", "普通话"),
    ("Bunny", "Bunny（萌小姬）", "普通话"),
    ("Neil", "Neil（阿闻）", "普通话"),
    ("Elias", "Elias（墨讲师）", "普通话"),
    ("Arthur", "Arthur（徐大爷）", "普通话"),
    ("Nini", "Nini（邻家妹妹）", "普通话"),
    ("Seren", "Seren（小婉）", "普通话"),
    ("Pip", "Pip（顽屁小孩）", "普通话"),
    ("Stella", "Stella（少女阿月）", "普通话"),
    ("Bodega", "Bodega", "国际音色"),
    ("Sonrisa", "Sonrisa", "国际音色"),
    ("Alek", "Alek", "国际音色"),
    ("Dolce", "Dolce", "国际音色"),
    ("Sohee", "Sohee", "国际音色"),
    ("Ono Anna", "Ono Anna", "国际音色"),
    ("Lenn", "Lenn", "国际音色"),
    ("Emilien", "Emilien", "国际音色"),
    ("Andre", "Andre", "国际音色"),
    ("Radio Gol", "Radio Gol", "国际音色"),
    ("Jada", "Jada（上海-阿珍）", "方言"),
    ("Dylan", "Dylan（北京-晓东）", "方言"),
    ("Li", "Li", "方言"),
    ("Marcus", "Marcus", "方言"),
    ("Roy", "Roy", "方言"),
    ("Peter", "Peter", "方言"),
    ("Sunny", "Sunny（四川-晴儿）", "方言"),
    ("Eric", "Eric", "方言"),
    ("Rocky", "Rocky", "方言"),
    ("Kiki", "Kiki", "方言"),
]

# qwen-audio 系列音色（12 基础 + plus 追加 2）
AUDIO_VOICES = [
    "longanhuan_v3.6", "longanfengyue", "longanyuanfei", "longanlingxi",
    "longanxiaoxin", "longjielidou_v3.6", "longpaopao_v3.6", "longhuohuo_v3.6",
    "longchuanshu_v3.6", "loongmary", "loongeva_v3.6", "loongjohn",
]
AUDIO_PLUS_EXTRA = ["longanlingxin", "longanlufeng"]

# 模型 → 音色集合映射
MODELS = {
    "TTS_QwenTTS_Flash": ("qwen3-tts-flash", FLASH_VOICES),
    "TTS_QwenTTS_Instruct": ("qwen3-tts-instruct-flash", [
        (v, n, g) for (v, n, g) in FLASH_VOICES[:24]
    ]),
    "TTS_QwenAudio_Flash": ("qwen-audio-3.0-tts-flash", [
        (v, v, "普通话") for v in AUDIO_VOICES
    ]),
    "TTS_QwenAudio_Plus": ("qwen-audio-3.0-tts-plus", [
        (v, v, "普通话") for v in AUDIO_VOICES + AUDIO_PLUS_EXTRA
    ]),
}


def sql_quote(value):
    if value is None:
        return "NULL"
    escaped = str(value).replace("\\", "\\\\").replace("'", "''")
    return f"'{escaped}'"


def voice_row(row_id, model_id, name, code, languages, sort):
    cols = ("id, tts_model_id, name, tts_voice, languages, voice_demo, "
            "remark, reference_audio, reference_text, sort, creator, "
            "create_date, updater, update_date")
    vals = ", ".join([
        sql_quote(row_id), sql_quote(model_id), sql_quote(name),
        sql_quote(code), sql_quote(languages), "NULL", "NULL", "NULL",
        "NULL", str(sort), "NULL", "NULL", "NULL", "NULL",
    ])
    return f"INSERT INTO `ai_tts_voice` ({cols}) VALUES ({vals});"


def main():
    out = io.StringIO()
    w = out.write
    w("-- 千问TTS预置 base_url 默认值 + 默认音色注入（音色管理弹窗数据源 ai_tts_voice）\n")
    w("-- 生成脚本：.workbuddy/gen_qwen_tts_seed.py（程序化生成，禁止手工改本文件数值）\n")
    w("-- base_url 实测 2026-10-06：compatible-mode/v1 拉模型列表 200；apps/anthropic 为 Anthropic 协议端点（LLM 用）\n")
    w("-- Python qwen_tts.py 合成走 maas.qianwenaiapi.com 原生端点，base_url 供控制台展示参考\n")
    w("-- 幂等：UPDATE 仅在 base_url 缺失时补；音色先 DELETE 后 INSERT\n\n")

    w("-- ===== provider 表单增加 base_url 字段（编辑对话框可见可改） =====\n")
    w("-- 仅追加缺失字段：先移除已存在的 base_url 条目再整体重写 fields，幂等\n")
    w("UPDATE `ai_model_provider`\n")
    w(f"SET `fields` = '[{{\"key\":\"api_key\",\"label\":\"API密钥\",\"type\":\"password\"}},"
      f"{{\"key\":\"base_url\",\"label\":\"服务地址\",\"type\":\"string\"}},"
      f"{{\"key\":\"model\",\"label\":\"模型\",\"type\":\"string\"}},"
      f"{{\"key\":\"voice\",\"label\":\"音色\",\"type\":\"string\"}},"
      f"{{\"key\":\"format\",\"label\":\"音频格式\",\"type\":\"string\"}},"
      f"{{\"key\":\"sample_rate\",\"label\":\"采样率\",\"type\":\"number\"}},"
      f"{{\"key\":\"instructions\",\"label\":\"指令(可选)\",\"type\":\"string\"}},"
      f"{{\"key\":\"output_dir\",\"label\":\"输出目录\",\"type\":\"string\"}}]',\n")
    w("    `update_date` = NOW()\n")
    w("WHERE `id` = 'SYSTEM_TTS_qwen_tts'\n")
    w("  AND JSON_EXTRACT(`fields`, '$') NOT LIKE '%base_url%';\n\n")

    w("-- ===== base_url 补默认值（仅缺失时） =====\n")
    for model_id in MODELS:
        w(f"UPDATE `ai_model_config`\n")
        w(f"SET `config_json` = JSON_SET(`config_json`, '$.base_url', '{BASE_URL}'),\n")
        w(f"    `update_date` = NOW()\n")
        w(f"WHERE `id` = '{model_id}'\n")
        w(f"  AND JSON_EXTRACT(`config_json`, '$.base_url') IS NULL;\n\n")

    w("-- ===== 默认音色注入 =====\n")
    for model_id, (model_name, voices) in MODELS.items():
        w(f"-- {model_id}（{model_name}，{len(voices)} 音色）\n")
        w(f"DELETE FROM `ai_tts_voice` WHERE `tts_model_id` = '{model_id}';\n")
        for idx, (code, name, lang) in enumerate(voices, start=1):
            row_id = f"{model_id}_V{idx:02d}"
            w(voice_row(row_id, model_id, name, code, lang, idx) + "\n")
        w("\n")

    path = ("G:/demo/21_xiaozhi/code-server-mirror/manager-api/src/main/resources/"
            "db/changelog/202610071100.sql")
    with io.open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(out.getvalue())

    total = sum(len(v[1]) for v in MODELS.values())
    print(f"written: {path}")
    print(f"models: {len(MODELS)}, voice rows: {total}")
    for model_id, (model_name, voices) in MODELS.items():
        print(f"  {model_id} ({model_name}): {len(voices)} voices")


if __name__ == "__main__":
    main()

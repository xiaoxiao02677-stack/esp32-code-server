#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
豆包声音复刻 —— TTS 请求包独立测试脚本（对齐官方 声音复刻 V3 脚本）
==================================================================

用途：把项目现在正在发的 TTS 请求包，原样抽成一份可以直接双击跑的脚本，
      你自己听一听「语气指令 / 音色指令」到底有没有生效。

来源：xiaozhi-server/core/providers/tts/doubao_v3.py（已对齐官方脚本）

依赖：pip install requests      （只这一个）
运行：python tts_voice_probe.py
产物：脚本同目录下 tts_out/*.mp3，直接双击试听

==================================================================
重要结论（实测，务必先看）
==================================================================
火山 TTS 输出是「非确定性」的：同一份请求连跑两次，md5 都不一样。
所以——**不要用文件大小 / md5 / 波形去判断情感有没有生效**，
那些差异全是随机噪声。唯一可靠的判定方式是人耳试听。
"""

import base64
import json
import os
import uuid

import requests

# ==========================================================
# 一、线上真实配置（取自 ai_model_config 的 config_json）
# ==========================================================
API_KEY = "d9f77dba-01ca-47fa-a4d3-7002adf6b6a4"
API_URL = "https://openspeech.bytedance.com/api/v3/tts/unidirectional"
RESOURCE_ID = "seed-icl-2.0"        # 声音复刻资源
SPEAKER = "S_N8pC5xwg2"             # 复刻音色（S_ 开头）
FORMAT = "mp3"
SAMPLE_RATE = 24000
UID = "xiaozhi-esp32-server"
NAMESPACE = "BidirectionalTTS"

# 如果你想用「后付费复刻」而不是预付费，把这两行打开：
# SPEAKER_TYPE = "postpaid"
# CUSTOM_SPEAKER_ID = "你的 custom_speaker_id"
SPEAKER_TYPE = "prepaid"
CUSTOM_SPEAKER_ID = None

# ---- 可选开关（默认全部关闭 = 严格对齐官方脚本）----
# 官方脚本的 req_params 里没有 model，也没有 enable_emotion / emotion_scale。
# 打开这些开关可以做「对齐 vs 全字段」的 A/B 对比。
USE_MODEL = False                   # True → 加 model=seed-tts-2.0-expressive
USE_EMOTION_SCALE = False           # True → 加 enable_emotion + emotion_scale
EXPLICIT_LANGUAGE = ""              # 官方脚本默认留空；中文可不填

# ---- 情感 ----
EMOTION = None                      # 手动指定，如 "happy"/"sad"/"angry"；留空则自动推断
EMOTION_SCALE = 4                   # 仅在 USE_EMOTION_SCALE=True 时发送（有效 1~5）
AUTO_EMOTION = True                 # 从中文语气指令自动推断 emotion

OUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tts_out")


# ==========================================================
# 二、语气指令关键词 -> 火山官方 emotion 枚举
#     （与 doubao_v3.py 的 EMOTION_KEYWORDS 完全一致）
# ==========================================================
EMOTION_KEYWORDS = {
    "happy": ("开心", "高兴", "快乐", "愉快", "喜悦", "欢喜", "雀跃", "兴高采烈",
              "笑", "乐", "甜", "happy", "joy"),
    "sad": ("难过", "伤心", "悲伤", "沮丧", "失落", "低落", "哭", "哽咽", "忧郁",
            "委屈", "消沉", "sad"),
    "angry": ("生气", "愤怒", "气愤", "恼火", "发火", "暴躁", "怒", "愤",
              "训斥", "angry"),
    "scared": ("害怕", "恐惧", "惊慌", "紧张", "颤抖", "发抖", "吓", "scared", "fear"),
    "surprised": ("惊讶", "震惊", "惊奇", "意外", "居然", "没想到", "不敢相信",
                  "surprised"),
    "hate": ("厌恶", "讨厌", "嫌弃", "鄙视", "不屑", "反感", "hate", "disgust"),
    "excited": ("激动", "亢奋", "热血", "振奋", "迫不及待", "欢呼", "excited"),
    "coldness": ("冷淡", "冷漠", "高冷", "冰冷", "敷衍", "无所谓", "漫不经心",
                 "coldness"),
    "neutral": ("平静", "平淡", "中性", "自然", "平稳", "客观", "neutral"),
}

EMOTION_SCALE_MIN, EMOTION_SCALE_MAX = 1, 5


def clamp_emotion_scale(value):
    """emotion_scale 为 0 或 >=6 时火山返回「空音频」，必须钳制。"""
    try:
        scale = int(float(value))
    except (TypeError, ValueError):
        return 4
    return max(EMOTION_SCALE_MIN, min(EMOTION_SCALE_MAX, scale))


def infer_emotion(instruction):
    """从中文语气指令推断 emotion；推断不出返回 None。"""
    if not instruction:
        return None
    text = str(instruction).lower()
    for emotion, kws in EMOTION_KEYWORDS.items():
        for kw in kws:
            if kw in text:
                return emotion
    return None


# ==========================================================
# 三、请求包构造（与 doubao_v3.py 的 _build_payload 逐字段一致）
# ==========================================================
def build_payload(text, instruction=None, emotion_override=None):
    # 1) audio_params（官方脚本顺序）
    audio_params = {
        "format": FORMAT,
        "sample_rate": SAMPLE_RATE,
        "speech_rate": 0,
        "loudness_rate": 0,
    }

    # 2) 情感：官方脚本只发 emotion 单字段
    emotion = emotion_override or EMOTION
    if not emotion and AUTO_EMOTION:
        emotion = infer_emotion(instruction)
    if emotion:
        audio_params["emotion"] = emotion
        if USE_EMOTION_SCALE:
            audio_params["enable_emotion"] = True
            audio_params["emotion_scale"] = clamp_emotion_scale(EMOTION_SCALE)

    # 3) speaker
    if SPEAKER_TYPE == "postpaid":
        speaker = "custom_speaker_id"
    else:
        speaker = SPEAKER

    req_params = {
        "text": text,
        "speaker": speaker,
        "audio_params": audio_params,
    }
    if SPEAKER_TYPE == "postpaid":
        req_params["custom_speaker_id"] = CUSTOM_SPEAKER_ID or SPEAKER
    if USE_MODEL:
        req_params["model"] = "seed-tts-2.0-expressive"

    # 4) additions：context_texts = 用户语气指令（官方唯一指令通道）
    additions = {}
    if EXPLICIT_LANGUAGE:
        additions["explicit_language"] = EXPLICIT_LANGUAGE
    if instruction:
        additions["context_texts"] = [instruction]
    if additions:
        req_params["additions"] = json.dumps(additions, ensure_ascii=False)

    # 5) 顶层三件套：user / req_params / namespace（对齐官方脚本）
    return {
        "user": {"uid": UID},
        "req_params": req_params,
        "namespace": NAMESPACE,
    }


def build_headers():
    return {
        "Content-Type": "application/json",
        "X-Api-Resource-Id": RESOURCE_ID,
        "X-Api-Request-Id": str(uuid.uuid4()),
        "X-Api-Key": API_KEY,
    }


def decode_chunk(data):
    clean = "".join(data.split())
    return base64.b64decode(clean + "=" * ((-len(clean)) % 4))


def synth(text, instruction=None, out_name="out.mp3", dump=False,
          emotion_override=None):
    payload = build_payload(text, instruction, emotion_override)
    if dump:
        print("  [请求体] " + json.dumps(payload, ensure_ascii=False, indent=2))

    resp = requests.post(API_URL, json=payload, headers=build_headers(),
                         stream=True, timeout=60)
    if resp.status_code != 200:
        print(f"  HTTP {resp.status_code}: {resp.text[:300]}")
        return None

    audio = bytearray()
    for line in resp.iter_lines(decode_unicode=True):
        if not line:
            continue
        obj = json.loads(line)
        code = obj.get("code")
        if code == 20000000:
            # 官方脚本判 message=="ok"；实测火山返回 "OK"（大写），
            # 这里抹平大小写，其余靠流读完自然退出
            if obj.get("data"):
                audio.extend(decode_chunk(obj["data"]))
            if str(obj.get("message") or "").strip().lower() == "ok":
                break
            continue
        if code not in (0, None):
            print(f"  错误 code={code} message={obj.get('message')}")
            return None
        if obj.get("data"):
            audio.extend(decode_chunk(obj["data"]))

    if not audio:
        print("  !! 返回空音频（emotion_scale 越界会静默返回空音频）")
        return None

    os.makedirs(OUT_DIR, exist_ok=True)
    path = os.path.join(OUT_DIR, out_name)
    with open(path, "wb") as f:
        f.write(bytes(audio))
    print(f"  -> {out_name}  ({len(audio)} 字节)")
    return path


# ==========================================================
# 四、测试用例
# ==========================================================
TEXT = "今天真是个好日子，我们一起出去玩吧！"

CASES = [
    ("01_基线_无指令",        None,                             None),
    ("02_开心指令",           "用非常开心、兴奋、雀跃的语气说话",  None),
    ("03_生气指令",           "用很生气愤怒的语气说话",            None),
    ("04_难过指令",           "用难过伤心、带哭腔的语气说话",       None),
    ("05_撒娇指令",           "用撒娇、可爱、甜美的语气说话",       None),
    ("06_固定emotion_happy",  None,                             "happy"),
    ("07_固定emotion_angry",  None,                             "angry"),
]


def main():
    print("=" * 66)
    print("豆包声音复刻 TTS 音色指令测试（对齐官方脚本）")
    print(f"音色 {SPEAKER} | 资源 {RESOURCE_ID} | 格式 {FORMAT}")
    print(f"开关: model={USE_MODEL} emotion_scale={USE_EMOTION_SCALE} "
          f"explicit_language={EXPLICIT_LANGUAGE or '(空)'}")
    print("=" * 66)

    for name, instruction, forced in CASES:
        print(f"\n--- {name} ---")
        if instruction:
            guess = infer_emotion(instruction)
            print(f"  指令: {instruction}")
            print(f"  推断 emotion: {guess or '(无关键词命中)'}")
        synth(TEXT, instruction, f"{name}.mp3",
              dump=(name.startswith("01")), emotion_override=forced)

    print("\n" + "=" * 66)
    print(f"全部完成，音频在：{OUT_DIR}")
    print("重点对比：01 基线 vs 02/03/04 —— 人耳听语气差别")
    print("注意：文件大小不同不代表情感生效，火山输出本身非确定性")
    print("=" * 66)


if __name__ == "__main__":
    main()

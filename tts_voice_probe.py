#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
豆包声音复刻 —— TTS 请求包独立测试脚本
=============================================

用途：把项目现在正在发的 TTS 请求包，原样抽成一份可以直接双击跑的脚本，
      你自己听一听「音色指令 / 语气指令」到底有没有生效。

来源：xiaozhi-server/core/providers/tts/doubao_v3.py
      （aoci 索引只覆盖固件 xiaozhi-esp32，固件是瘦客户端不含 TTS 请求包，
        所以按服务端源码转换）

依赖：pip install requests      （只这一个）

运行：python tts_voice_probe.py
产物：脚本同目录下的 out_*.mp3，直接双击试听
"""

import base64
import json
import os
import uuid

import requests

# ==========================================================
# 一、线上真实配置（取自 ai_model_config 的 config_json）
#     想换成你自己的，改这里就行
# ==========================================================
API_KEY = "d9f77dba-01ca-47fa-a4d3-7002adf6b6a4"
API_URL = "https://openspeech.bytedance.com/api/v3/tts/unidirectional"
RESOURCE_ID = "seed-icl-2.0"        # 声音复刻资源
SPEAKER = "S_N8pC5xwg2"             # 复刻音色（S_ 开头）
FORMAT = "mp3"
SAMPLE_RATE = 24000

# 如果你想用「后付费复刻」而不是预付费，把这两行打开：
# SPEAKER_TYPE = "postpaid"
# CUSTOM_SPEAKER_ID = "你的 custom_speaker_id"
SPEAKER_TYPE = "prepaid"
CUSTOM_SPEAKER_ID = None

# 可选：手动指定情感（留空则由语气指令自动推断）
EMOTION = None                      # 例如 "happy" / "sad" / "angry"
EMOTION_SCALE = 4                   # 实测有效范围 1~5，越界会返回空音频
AUTO_EMOTION = True                 # 从中文语气指令自动推断 emotion
EXPLICIT_LANGUAGE = "zh"
NAMESPACE = "BidirectionalTTS"      # 官方脚本固定值

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
    """实测：emotion_scale 为 0 或 >=6 时火山返回「空音频」，必须钳制。"""
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


def is_clone_resource():
    return str(RESOURCE_ID).startswith("seed-icl") or str(SPEAKER).startswith("S_")


# ==========================================================
# 三、请求包构造（与 doubao_v3.py 的 _build_payload 逐字段一致）
# ==========================================================
def build_payload(text, instruction=None):
    audio_params = {
        "format": FORMAT,
        "sample_rate": SAMPLE_RATE,
        "speech_rate": 0,
        "loudness_rate": 0,
    }

    emotion = EMOTION
    if not emotion and AUTO_EMOTION:
        emotion = infer_emotion(instruction)
    if emotion:
        audio_params["enable_emotion"] = True
        audio_params["emotion"] = emotion
        audio_params["emotion_scale"] = clamp_emotion_scale(EMOTION_SCALE)

    additions = {}
    if EXPLICIT_LANGUAGE:
        additions["explicit_language"] = EXPLICIT_LANGUAGE
    if instruction:
        additions["context_texts"] = [instruction]

    req_params = {"text": text, "audio_params": audio_params}
    if SPEAKER_TYPE == "postpaid":
        req_params["speaker"] = "custom_speaker_id"
        req_params["custom_speaker_id"] = CUSTOM_SPEAKER_ID or SPEAKER
    else:
        req_params["speaker"] = SPEAKER
    if additions:
        req_params["additions"] = json.dumps(additions, ensure_ascii=False)
    if is_clone_resource():
        req_params["model"] = "seed-tts-2.0-expressive"

    payload = {"user": {"uid": "xiaozhi-esp32-server"}, "req_params": req_params}
    if NAMESPACE:
        payload["namespace"] = NAMESPACE
    return payload


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


# ==========================================================
# 四、发请求（与 doubao_v3.py 一致：stream=True + iter_lines）
# ==========================================================
def synth(text, instruction=None, out_name="out.mp3", dump=False):
    payload = build_payload(text, instruction)
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
            if obj.get("data"):
                audio.extend(decode_chunk(obj["data"]))
            break
        if code not in (0, None):
            print(f"  错误 code={code} message={obj.get('message')}")
            return None
        if obj.get("data"):
            audio.extend(decode_chunk(obj["data"]))

    if not audio:
        print("  !! 返回空音频（注意：emotion_scale 越界会静默返回空音频）")
        return None

    os.makedirs(OUT_DIR, exist_ok=True)
    path = os.path.join(OUT_DIR, out_name)
    with open(path, "wb") as f:
        f.write(bytes(audio))
    print(f"  -> {path}  ({len(audio)} 字节)")
    return path


# ==========================================================
# 五、测试用例
# ==========================================================
TEXT = "今天真是个好日子，我们一起出去玩吧！"

CASES = [
    ("01_基线_无指令",        None,                              None),
    ("02_开心指令",           "用非常开心、兴奋、雀跃的语气说话",   None),
    ("03_生气指令",           "用很生气愤怒的语气说话",             None),
    ("04_难过指令",           "用难过伤心、带哭腔的语气说话",        None),
    ("05_撒娇指令",           "用撒娇、可爱、甜美的语气说话",        None),
    ("06_固定emotion_happy",  None,                              "happy"),
    ("07_固定emotion_angry",  None,                              "angry"),
]


def main():
    print("=" * 66)
    print("豆包声音复刻 TTS 音色指令测试")
    print(f"音色 {SPEAKER} | 资源 {RESOURCE_ID} | 格式 {FORMAT}")
    print("=" * 66)

    for name, instruction, forced in CASES:
        global EMOTION
        EMOTION = forced
        print(f"\n--- {name} ---")
        if instruction:
            guess = infer_emotion(instruction)
            print(f"  指令: {instruction}")
            print(f"  推断 emotion: {guess or '(无关键词命中，不发送 emotion)'}")
        synth(TEXT, instruction, f"{name}.mp3", dump=(name.startswith("01")))

    print("\n" + "=" * 66)
    print(f"全部完成，音频在：{OUT_DIR}")
    print("重点对比：01 基线 vs 02/03/04 —— 听语气差别")
    print("=" * 66)


if __name__ == "__main__":
    main()

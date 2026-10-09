#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
严格对齐「火山官方 声音复刻 V3 脚本」的 A/B 对照测试
====================================================
目的：找出到底哪套字段能让「语气指令(context_texts)」真正生效。

变体：
  A 官方原样      ：namespace+user+text/speaker/audio_params+additions(explicit_language)
  B 官方+CTX      ：A + additions.context_texts = 用户语气指令   <-- 用户要求的通道
  C 官方+EMO      ：A + audio_params.emotion（官方脚本单字段写法）
  D 官方+EMO+CTX  ：B + C
  E 当前项目      ：D + model + enable_emotion + emotion_scale   <-- 现网在跑的

所有变体都用 json= 提交，逐行读流，统计字节数/是否空音频。
"""

import base64
import json
import os
import uuid

import requests

API_KEY = "d9f77dba-01ca-47fa-a4d3-7002adf6b6a4"
API_URL = "https://openspeech.bytedance.com/api/v3/tts/unidirectional"
RESOURCE_ID = "seed-icl-2.0"
SPEAKER_ID = "S_N8pC5xwg2"
FORMAT = "mp3"
SAMPLE_RATE = 24000
UID = "xiaozhi-esp32-server"
NAMESPACE = "BidirectionalTTS"

TEXT = "今天真是个好日子，我们一起出去玩吧！"
INSTRUCTION = "用非常开心、兴奋、雀跃的语气说话，语速轻快，音调上扬"
EMOTION_GUESS = "happy"

OUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tts_ab_out")


def decode_chunk(data):
    clean = "".join(data.split())
    return base64.b64decode(clean + "=" * ((-len(clean)) % 4))


def build(variant, text, instruction=None, emotion=None):
    """按官方脚本结构组装，variant 决定额外挂哪些字段。"""
    audio_params = {
        "format": FORMAT,
        "sample_rate": SAMPLE_RATE,
        "speech_rate": 0,
        "loudness_rate": 0,
    }

    # 官方脚本写法：只有 emotion 单字段
    if variant in ("C", "D", "E") and emotion:
        audio_params["emotion"] = emotion
    if variant == "E":
        # 当前项目多带的两个非官方字段
        audio_params["enable_emotion"] = True
        audio_params["emotion_scale"] = 4

    req_params = {
        "text": text,
        "speaker": SPEAKER_ID,
        "audio_params": audio_params,
    }

    # additions：官方脚本只示范 explicit_language；context_texts 是指令通道
    additions = {"explicit_language": "zh"}
    if variant in ("B", "D", "E") and instruction:
        additions["context_texts"] = [instruction]
    req_params["additions"] = json.dumps(additions, ensure_ascii=False)

    if variant == "E":
        # 当前项目额外传的 model
        req_params["model"] = "seed-tts-2.0-expressive"

    return {"user": {"uid": UID}, "namespace": NAMESPACE, "req_params": req_params}


def synth(variant, out_name, instruction=None, emotion=None, dump=False):
    payload = build(variant, TEXT, instruction, emotion)
    if dump:
        print("  [请求体] " + json.dumps(payload, ensure_ascii=False, indent=2))

    headers = {
        "Content-Type": "application/json",
        "X-Api-Key": API_KEY,
        "X-Api-Resource-Id": RESOURCE_ID,
        "X-Api-Request-Id": str(uuid.uuid4()),
    }

    resp = requests.post(API_URL, json=payload, headers=headers,
                         stream=True, timeout=60)
    if resp.status_code != 200:
        print(f"  HTTP {resp.status_code}: {resp.text[:300]}")
        return None

    audio = bytearray()
    tail_msg = None
    n_lines = 0
    for line in resp.iter_lines(decode_unicode=True):
        if not line:
            continue
        n_lines += 1
        obj = json.loads(line)
        code = obj.get("code")
        msg = obj.get("message")
        if code == 20000000:
            # 官方脚本判定 message=="ok"；实测火山返回 "OK"（大写）
            tail_msg = msg
            if obj.get("data"):
                audio.extend(decode_chunk(obj["data"]))
            break
        if code not in (0, None):
            print(f"  错误 code={code} message={msg}")
            return None
        if obj.get("data"):
            audio.extend(decode_chunk(obj["data"]))

    flag = "空音频!" if not audio else "OK"
    print(f"  -> {len(audio)} 字节 | {n_lines} 帧 | 结束message={tail_msg!r} | {flag}")

    if audio:
        os.makedirs(OUT_DIR, exist_ok=True)
        path = os.path.join(OUT_DIR, out_name)
        with open(path, "wb") as f:
            f.write(bytes(audio))
        return path
    return None


CASES = [
    ("A_官方原样",        "A", None,         None),
    ("B_官方+context_texts", "B", INSTRUCTION, None),
    ("C_官方+emotion",       "C", None,         EMOTION_GUESS),
    ("D_官方+emo+ctx",      "D", INSTRUCTION, EMOTION_GUESS),
    ("E_当前项目全字段",     "E", INSTRUCTION, EMOTION_GUESS),
]


def main():
    print("=" * 70)
    print("官方脚本对齐 A/B 对照 —— 找 context_texts 生效组合")
    print(f"音色 {SPEAKER_ID} | 资源 {RESOURCE_ID}")
    print(f"文本: {TEXT}")
    print(f"指令: {INSTRUCTION}")
    print("=" * 70)
    for name, variant, instr, emo in CASES:
        print(f"\n--- {name} ---")
        synth(variant, f"{name}.mp3", instr, emo,
              dump=(variant in ("A", "E")))
    print("\n" + "=" * 70)
    print(f"产物：{OUT_DIR}")
    print("重点：A(基线) vs B(仅context_texts) vs D(两者) —— 人耳听语气差别")
    print("=" * 70)


if __name__ == "__main__":
    main()

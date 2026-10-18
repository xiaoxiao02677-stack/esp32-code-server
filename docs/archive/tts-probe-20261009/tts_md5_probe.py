#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
md5 精确比对：判断 context_texts / model / enable_emotion / emotion_scale
到底有没有被火山服务端采纳。

同一变体跑两次 -> 先确认是否确定性（可复现）
不同变体比 md5 -> md5 相同 = 该字段被完全忽略
"""

import base64
import hashlib
import json
import uuid

import requests

API_KEY = "d9f77dba-01ca-47fa-a4d3-7002adf6b6a4"
API_URL = "https://openspeech.bytedance.com/api/v3/tts/unidirectional"
RESOURCE_ID = "seed-icl-2.0"
SPEAKER_ID = "S_N8pC5xwg2"
TEXT = "今天真是个好日子，我们一起出去玩吧！"
INSTRUCTION = "用非常开心、兴奋、雀跃的语气说话，语速轻快，音调上扬"


def decode_chunk(data):
    clean = "".join(data.split())
    return base64.b64decode(clean + "=" * ((-len(clean)) % 4))


def build(ctx=False, emo=None, model=False, enable_emo=False, scale=None):
    audio_params = {"format": "mp3", "sample_rate": 24000,
                    "speech_rate": 0, "loudness_rate": 0}
    if emo:
        audio_params["emotion"] = emo
    if enable_emo:
        audio_params["enable_emotion"] = True
    if scale is not None:
        audio_params["emotion_scale"] = scale

    additions = {"explicit_language": "zh"}
    if ctx:
        additions["context_texts"] = [INSTRUCTION]

    req = {"text": TEXT, "speaker": SPEAKER_ID,
           "audio_params": audio_params,
           "additions": json.dumps(additions, ensure_ascii=False)}
    if model:
        req["model"] = "seed-tts-2.0-expressive"
    return {"user": {"uid": "yuhe-esp32-server"},
            "namespace": "BidirectionalTTS", "req_params": req}


def synth(**kw):
    headers = {"Content-Type": "application/json",
               "X-Api-Key": API_KEY,
               "X-Api-Resource-Id": RESOURCE_ID,
               "X-Api-Request-Id": str(uuid.uuid4())}
    r = requests.post(API_URL, json=build(**kw), headers=headers,
                      stream=True, timeout=60)
    if r.status_code != 200:
        return None, f"HTTP {r.status_code}"
    audio = bytearray()
    for line in r.iter_lines(decode_unicode=True):
        if not line:
            continue
        o = json.loads(line)
        if o.get("code") == 20000000:
            if o.get("data"):
                audio.extend(decode_chunk(o["data"]))
            break
        if o.get("data"):
            audio.extend(decode_chunk(o["data"]))
    if not audio:
        return None, "空音频"
    return bytes(audio), None


def run(label, times=2, **kw):
    digests = []
    for i in range(times):
        data, err = synth(**kw)
        if err:
            print(f"{label:<34} 第{i+1}次 失败: {err}")
            continue
        digests.append(hashlib.md5(data).hexdigest())
        print(f"{label:<34} run{i+1}  {len(data):>6}B  md5={hashlib.md5(data).hexdigest()[:16]}")
    if len(set(digests)) == 1 and len(digests) > 1:
        print(f"{'':<34} -> 确定性(两次一致)")
    elif len(digests) > 1:
        print(f"{'':<34} -> !! 非确定性(两次不同)")
    return digests


print("=" * 78)
print("md5 精确比对 —— 哪个字段真被采纳")
print(f"文本: {TEXT}")
print("=" * 78)

r = {}
r["A 基线(无指令无emo)"] = run("A 基线(无指令无emo)", ctx=False)
print()
r["B +context_texts"] = run("B +context_texts", ctx=True)
print()
r["C +emotion=happy"] = run("C +emotion=happy", ctx=False, emo="happy")
print()
r["D +emo+ctx"] = run("D +emo+ctx", ctx=True, emo="happy")
print()
r["E +model"] = run("E +model", ctx=False, model=True)
print()
r["F +enable_emotion"] = run("F +enable_emotion", ctx=False, enable_emo=True)
print()
r["G +emotion_scale=4"] = run("G +emotion_scale=4", ctx=False, scale=4)
print()
r["H 现网全字段"] = run("H 现网全字段", ctx=True, emo="happy",
                        model=True, enable_emo=True, scale=4)

print("\n" + "=" * 78)
print("判定（md5 与 A 基线相同 = 该字段被服务端完全忽略）：")
base = set(r["A 基线(无指令无emo)"])
for k, v in r.items():
    if k == "A 基线(无指令无emo)":
        continue
    if not v:
        print(f"  {k:<24} 无结果")
        continue
    same = set(v) & base
    if same:
        print(f"  {k:<24} ✗ 与基线相同 -> 被忽略")
    else:
        print(f"  {k:<24} ✓ 与基线不同 -> 生效")
print("=" * 78)

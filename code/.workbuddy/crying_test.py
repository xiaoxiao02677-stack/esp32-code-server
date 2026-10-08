#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""最简版 豆包TTS2.0 哭腔流式合成（用户提供的基准脚本，输出路径改为 /tmp）"""
import json, base64, requests

API_KEY = "d9f77dba-01ca-47fa-a4d3-7002adf6b6a4"
VOICE_TYPE = "zh_female_vv_uranus_bigtts"
OUTPUT_FILE = "/tmp/crying_tts.mp3"
TEXT = "你怎么可以这样对我……我真的好难过好难过，呜……呜……为什么要丢下我一个人……"
CONTEXT_TEXTS = ["用哭腔说话，声音哽咽，带着抽泣，说话断断续续，快要哭出来的语气"]

payload = {"req_params": {"text": TEXT, "speaker": VOICE_TYPE,
                          "audio_params": {"format": "mp3", "sample_rate": 24000},
                          "additions": json.dumps({"context_texts": CONTEXT_TEXTS}, ensure_ascii=False)}}
headers = {"Content-Type": "application/json", "X-Api-Key": API_KEY, "X-Api-Resource-Id": "seed-tts-2.0"}
url = "https://openspeech.bytedance.com/api/v3/tts/unidirectional"

resp = requests.post(url, headers=headers, data=json.dumps(payload), stream=True)
if resp.status_code != 200:
    print("请求失败", resp.text)
    exit(1)

audio_chunks = []
for raw_line in resp.iter_lines(decode_unicode=True):
    if not raw_line:
        continue
    msg = json.loads(raw_line)
    if msg.get("code") not in (0, 20000000):
        print("业务错误", msg.get("message"))
        exit(1)
    if d := msg.get("data"):
        audio_chunks.append(base64.b64decode(d))

with open(OUTPUT_FILE, "wb") as f:
    f.write(b"".join(audio_chunks))
print(f"完成，输出：{OUTPUT_FILE}", len(b"".join(audio_chunks)), "bytes")

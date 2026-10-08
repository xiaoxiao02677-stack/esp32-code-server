#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""在服务器上用真实 TTSProvider + 线上配置做情感合成实测。"""
import asyncio
import os
import sys

ROOT = "/root/xiaozhi-server/main/xiaozhi-server"
sys.path.insert(0, ROOT)

from core.providers.tts.doubao_v3 import TTSProvider  # noqa: E402

# 直接取自 ai_model_config.config_json（模型「豆包声音复刻」）
CFG = {
    "type": "doubao_v3",
    "format": "mp3",
    "api_key": "d9f77dba-01ca-47fa-a4d3-7002adf6b6a4",
    "api_url": "https://openspeech.bytedance.com/api/v3/tts/unidirectional",
    "speaker": "S_N8pC5xwg2",
    "resource_id": "seed-icl-2.0",
    "sample_rate": "24000",
}
TEXT = "今天真是个好日子，我们一起出去玩吧！"
OUT = "/tmp/tts_probe"


def run(tag, instruction=None, **over):
    os.makedirs(OUT, exist_ok=True)
    cfg = dict(CFG)
    cfg.update(over)
    p = TTSProvider(cfg, False)
    if instruction:
        p.set_dynamic_instruction(instruction)
    pl = p._build_payload(TEXT)
    ap = pl["req_params"]["audio_params"]
    print(f"\n--- {tag} ---")
    print("namespace:", pl.get("namespace"))
    print("emotion  :", ap.get("emotion"), "scale:", ap.get("emotion_scale"),
          "enable:", ap.get("enable_emotion"))
    print("additions:", pl["req_params"].get("additions"))
    print("model    :", pl["req_params"].get("model"))
    f = f"{OUT}/{tag}.mp3"
    asyncio.run(p.text_to_speak(TEXT, f))
    print("音频字节 :", os.path.getsize(f))


print("=" * 56)
print("服务器网络 · 真实 API · 情感合成实测")
print("=" * 56)
run("01_基线无指令")
run("02_开心", "用非常开心、兴奋、雀跃的语气说话")
run("03_生气", "用很生气愤怒的语气说话")
run("04_难过", "用难过伤心的语气说话")
run("05_DB现网指令", "大幅度发大幅度发的")
run("06_越界scale", "用开心的语气说话", emotion_scale=99)
print("\n全部完成")

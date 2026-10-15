#!/usr/bin/env python3
"""复现实验：直接用 doubao_v3 provider 合成（绕过推送调度），检验 0xAA/0x55 尾部垃圾来源。
场景 A：同一 provider 实例连续合成 4 次（模拟推送管线按 agent 缓存复用）
场景 B：每次新建 provider 合成 2 次
产物全部落 /tmp/repro-*.mp3 并输出完整性判定。
"""
import asyncio
import os
import re
import sys
import time

sys.path.insert(0, "/root/xiaozhi-server/main/xiaozhi-server")
os.chdir("/root/xiaozhi-server/main/xiaozhi-server")

from core.utils.modules_initialize import initialize_tts  # noqa: E402

TTS_CFG = {
    "selected_module": {"TTS": "doubao_v3"},
    "TTS": {
        "doubao_v3": {
            "type": "doubao_v3",
            "format": "mp3",
            "api_key": os.environ.get("DOUBAO_API_KEY", ""),
            "api_url": "https://openspeech.bytedance.com/api/v3/tts/unidirectional",
            "speaker": "S_N8pC5xwg2",
            "resource_id": "seed-icl-2.0",
            "sample_rate": "24000",
            "private_voice": "S_ZiVB5xwg2",
            "ttsRate": 25,
            "output_dir": "/tmp/",
        }
    },
}

TEXTS = [
    "今天天气不错，我们出去走走吧。",
    "嗯，我在想，如果你也刚好有空的话，就陪我聊聊天好不好？",
    "其实我一直都想跟你说，这世界上最温柔的事情，就是有人愿意听你讲废话。",
    "好啦，我知道你最近很累，那就早点休息，我在这里陪着你。",
]


def judge(path):
    d = open(path, "rb").read()
    n = len(d)
    tail = d[-1:]
    if tail in (b"\xaa", b"\x55"):
        i = n - 1
        while i > 0 and d[i - 1] in (0xAA, 0x55):
            i -= 1
        garb = n - i
    else:
        garb = 0
    has_oggs = d.count(b"OggS")
    return n, garb, tail.hex(), has_oggs


async def synth(provider, text, path):
    await asyncio.to_thread(lambda: asyncio.run(provider.text_to_speak(text, path)))


async def main():
    import yaml
    # 从环境变量取不到时，直接从 manager-api 配置里挖（复刻 topic_generator 的解析链）
    api_key = os.environ.get("DOUBAO_API_KEY")
    if not api_key:
        # 从 manager-api 数据库的模型配置表直接取 doubao_v3 真实配置
        import pymysql
        import json as _json
        conn = pymysql.connect(host="localhost", user="root", password="123456",
                               database="xiaozhi_esp32_server", charset="utf8mb4")
        cur = conn.cursor()
        cur.execute("SELECT config_json FROM ai_model_config WHERE config_json LIKE %s LIMIT 1",
                    ('%doubao_v3%',))
        row = cur.fetchone()
        conn.close()
        if not row:
            print("!! ai_model_config 中找不到 doubao_v3 配置，放弃")
            return
        conf = _json.loads(row[0])
        conf.setdefault("output_dir", "/tmp/")
        print("== 使用 DB 真实 TTS 配置: type =", conf.get("type"),
              "speaker =", conf.get("speaker"), "resource =", conf.get("resource_id"))
        tts_cfg = {"selected_module": {"TTS": "doubao_v3"},
                   "TTS": {"doubao_v3": conf}}
    else:
        tts_cfg = TTS_CFG

    results = []
    # 场景 A：同一实例连续 4 次
    p = initialize_tts(tts_cfg)
    p.delete_audio_file = False
    p.tts_timeout = 60
    for i, t in enumerate(TEXTS, 1):
        path = f"/tmp/repro-A-{i}.mp3"
        t0 = time.time()
        try:
            await synth(p, t, path)
            n, garb, tail, oggs = judge(path)
            results.append(("A", i, n, garb, tail, oggs, round(time.time() - t0, 1), "ok"))
        except Exception as e:
            results.append(("A", i, 0, 0, "-", 0, round(time.time() - t0, 1), f"FAIL:{str(e)[:60]}"))
    # 场景 B：每次新建实例
    for i, t in enumerate(TEXTS[:2], 1):
        p2 = initialize_tts(tts_cfg)
        p2.delete_audio_file = False
        p2.tts_timeout = 60
        path = f"/tmp/repro-B-{i}.mp3"
        t0 = time.time()
        try:
            await synth(p2, t, path)
            n, garb, tail, oggs = judge(path)
            results.append(("B", i, n, garb, tail, oggs, round(time.time() - t0, 1), "ok"))
        except Exception as e:
            results.append(("B", i, 0, 0, "-", 0, round(time.time() - t0, 1), f"FAIL:{str(e)[:60]}"))

    print(f"\n{'scn':4} {'#':2} {'size':>7} {'garbage':>7} {'tail':>4} {'OggS':>4} {'sec':>5}  status")
    for r in results:
        print(f"{r[0]:4} {r[1]:2} {r[2]:>7} {r[3]:>7} {r[4]:>4} {r[5]:>4} {r[6]:>5}  {r[7]}")
    garb_n = sum(1 for r in results if r[3] > 0)
    print(f"\n合成 {len(results)} 次，尾部垃圾 {garb_n} 次")


if __name__ == "__main__":
    asyncio.run(main())

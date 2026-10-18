# 临时性能探测脚本（live-prober，2026-10-13）：仅放 /tmp，只读调用项目模块，不修改项目文件
import asyncio
import sys
import os
import time
import threading

sys.path.insert(0, "/root/yh/app/yuhe-server")
os.chdir("/root/yh/app/yuhe-server")

import logging

logging.basicConfig(level=logging.WARNING)

from config.settings import load_config
from core.utils.tts import create_instance

SENTENCES = [
    "你好，这是一段性能测试语音。",
    "今天天气真不错，适合出门散步，顺便买一杯咖啡再回家。",
]

TARGET = os.environ.get("PERF_TTS_TARGET", "TTS_QwenTTS_Flash")


class MockConn:
    sample_rate = 16000
    audio_format = "pcm"
    stop_event = threading.Event()
    client_abort = False
    headers = {}


async def main():
    cfg = await load_config()
    tts_cfg = cfg.get("TTS", {}).get(TARGET)
    env_json = os.environ.get("TTS_CFG_JSON", "")
    if env_json:
        import json

        tts_cfg = json.loads(env_json)
    if not tts_cfg:
        print(f"NO_TTS_CONFIG: {TARGET}")
        return
    tts = create_instance(tts_cfg["type"], tts_cfg, delete_audio_file=True)
    tts.conn = MockConn()
    if not hasattr(tts, "opus_encoder") or tts.opus_encoder is None:

        class MockEnc:
            pass

        tts.opus_encoder = MockEnc()
    print(
        f"provider={type(tts).__name__} model={tts_cfg.get('model')} voice={tts_cfg.get('voice')} type={tts_cfg.get('type')}",
        flush=True,
    )
    # 预热/连通性
    try:
        f = tts.generate_filename()
        t0 = time.time()
        await tts.text_to_speak("连接测试", f)
        warm = time.time() - t0
        ok = f and os.path.exists(f) and os.path.getsize(f) > 0
        print(f"warmup={warm:.2f}s ok={'Y' if ok else 'N'}", flush=True)
        if not ok:
            print("CONNECT_FAIL")
            return
    except Exception as e:
        print(f"CONNECT_FAIL: {type(e).__name__}: {e}")
        return
    for i, s in enumerate(SENTENCES, 1):
        t0 = time.time()
        err = None
        f = tts.generate_filename()
        try:
            await tts.text_to_speak(s, f)
        except Exception as e:
            err = f"{type(e).__name__}: {e}"
        total = time.time() - t0
        size = os.path.getsize(f) if f and os.path.exists(f) else 0
        print(
            f"[{i}/{len(SENTENCES)}] total={total:.2f}s bytes={size} err={err}",
            flush=True,
        )
        await asyncio.sleep(1)


asyncio.run(main())

#!/usr/bin/env python3
"""Advanced yuhe TTS verification: latency, sentence stats, stability.

Usage: python verify_tts_adv.py "<text>" [timeout_sec] [label]
Prints structured RESULT lines for automated collection.
"""
import asyncio
import json
import sys
import time

import websockets

DEVICE_ID = "14:c1:9f:d1:33:48"
WS_URL = "ws://sandyun.top:8001/yuhe/v1/"


async def run_session(text: str, timeout_sec: float, label: str) -> dict:
    headers = [
        ("Authorization", "Bearer test"),
        ("Protocol-Version", "1"),
        ("Device-Id", DEVICE_ID),
        ("Client-Id", "verify-adv"),
    ]
    stats = {
        "label": label,
        "sentences": 0,
        "audio_frames": 0,
        "tts_bytes": 0,
        "got_stt": False,
        "got_llm": False,
        "got_tts_start": False,
        "got_tts_stop": False,
        "t_first_tts_start": None,
        "t_first_audio": None,
        "error": None,
    }

    try:
        async with websockets.connect(WS_URL, additional_headers=headers) as ws:
            hello = {
                "type": "hello",
                "version": 1,
                "transport": "websocket",
                "audio_params": {
                    "format": "opus",
                    "sample_rate": 16000,
                    "channels": 1,
                    "frame_duration": 60,
                },
            }
            await ws.send(json.dumps(hello))

            listen = {
                "session_id": "verify-adv",
                "type": "listen",
                "state": "start",
                "mode": "manual",
            }
            await ws.send(json.dumps(listen))
            text_msg = {
                "session_id": "verify-adv",
                "type": "listen",
                "state": "detect",
                "text": text,
            }
            await ws.send(json.dumps(text_msg))
            stop = {
                "session_id": "verify-adv",
                "type": "listen",
                "state": "stop",
            }
            await ws.send(json.dumps(stop))
            t_query = time.time()

            deadline = time.time() + timeout_sec
            while time.time() < deadline:
                try:
                    msg = await asyncio.wait_for(
                        ws.recv(), timeout=max(1, deadline - time.time())
                    )
                except asyncio.TimeoutError:
                    break
                if isinstance(msg, bytes):
                    stats["audio_frames"] += 1
                    stats["tts_bytes"] += len(msg)
                    if stats["t_first_audio"] is None:
                        stats["t_first_audio"] = round(
                            time.time() - t_query, 2
                        )
                else:
                    data = json.loads(msg)
                    t = data.get("type")
                    if t == "tts":
                        state = data.get("state")
                        if state == "start":
                            stats["got_tts_start"] = True
                            if stats["t_first_tts_start"] is None:
                                stats["t_first_tts_start"] = round(
                                    time.time() - t_query, 2
                                )
                        elif state == "sentence_start":
                            stats["sentences"] += 1
                        elif state == "stop":
                            stats["got_tts_stop"] = True
                            break
                    elif t == "stt":
                        if data.get("text"):
                            stats["got_stt"] = True
                    elif t == "llm":
                        stats["got_llm"] = True
    except Exception as e:
        stats["error"] = f"{type(e).__name__}: {e}"

    ok = (
        stats["got_stt"]
        and stats["got_llm"]
        and stats["got_tts_start"]
        and stats["audio_frames"] > 0
        and stats["got_tts_stop"]
    )
    stats["success"] = ok
    print(
        f"RESULT|{label}|sentences={stats['sentences']}"
        f"|frames={stats['audio_frames']}|bytes={stats['tts_bytes']}"
        f"|stt={int(stats['got_stt'])}|llm={int(stats['got_llm'])}"
        f"|tts_start={int(stats['got_tts_start'])}"
        f"|tts_stop={int(stats['got_tts_stop'])}"
        f"|latency_tts_start={stats['t_first_tts_start']}"
        f"|latency_first_audio={stats['t_first_audio']}"
        f"|success={int(ok)}"
        f"|error={stats['error']}"
    )
    return stats


async def main():
    text = sys.argv[1]
    timeout_sec = float(sys.argv[2]) if len(sys.argv) > 2 else 60
    label = sys.argv[3] if len(sys.argv) > 3 else "run"
    await run_session(text, timeout_sec, label)


if __name__ == "__main__":
    asyncio.run(main())

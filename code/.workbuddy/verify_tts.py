#!/usr/bin/env python3
"""Simulate a xiaozhi device: connect WS, say something, verify TTS audio.

Usage: python verify_tts.py [text]
"""
import asyncio
import base64
import json
import sys
import time

import websockets

# device id seen in server logs (my-s3-tft board)
DEVICE_ID = "14:c1:9f:d1:33:48"
WS_URL = "ws://sandyun.top:8001/xiaozhi/v1/"


async def main():
    text = sys.argv[1] if len(sys.argv) > 1 else "你好，请用一句话介绍你自己"

    headers = [
        ("Authorization", "Bearer test"),
        ("Protocol-Version", "1"),
        ("Device-Id", DEVICE_ID),
        ("Client-Id", "verify-script"),
    ]
    print(f"[*] connecting {WS_URL} as {DEVICE_ID}")
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
        print("[*] hello sent, waiting for TTS reply...")

        # send text as user query (text-based listen start with content)
        listen = {
            "session_id": "verify-001",
            "type": "listen",
            "state": "start",
            "mode": "manual",
        }
        await ws.send(json.dumps(listen))

        # some server versions accept text via this message form
        text_msg = {
            "session_id": "verify-001",
            "type": "listen",
            "state": "detect",
            "text": text,
        }
        await ws.send(json.dumps(text_msg))
        print(f"[*] query sent: {text}")

        stop = {
            "session_id": "verify-001",
            "type": "listen",
            "state": "stop",
        }
        await ws.send(json.dumps(stop))

        tts_bytes = 0
        audio_frames = 0
        text_out = []
        deadline = time.time() + 30
        try:
            while time.time() < deadline:
                msg = await asyncio.wait_for(ws.recv(), timeout=max(1, deadline - time.time()))
                if isinstance(msg, bytes):
                    audio_frames += 1
                    tts_bytes += len(msg)
                    if audio_frames <= 2:
                        print(f"[+] TTS audio frame #{audio_frames}: {len(msg)} bytes")
                else:
                    data = json.loads(msg)
                    t = data.get("type")
                    if t == "tts":
                        state = data.get("state")
                        print(f"[+] tts message: state={state}")
                        if state == "sentence_start":
                            print(f"    text: {data.get('text', '')[:60]}")
                    elif t == "stt":
                        print(f"[+] stt: {str(data.get('text',''))[:60]}")
                    elif t in ("llm",):
                        print(f"[+] llm: {str(data.get('emotion',''))[:20]}")
                    else:
                        text_out.append(data)
                        print(f"[i] {t}: {json.dumps(data, ensure_ascii=False)[:120]}")
                    # finish after tts stop + sentence_end
                    if t == "tts" and data.get("state") == "stop":
                        print("[+] got tts stop -> done")
                        break
        except asyncio.TimeoutError:
            print("[!] timeout waiting")
        except websockets.ConnectionClosed as e:
            print(f"[!] closed: {e}")

        print(f"\n=== RESULT: audio_frames={audio_frames} tts_bytes={tts_bytes} ===")
        if audio_frames > 0:
            print("VERDICT: TTS OK (audio frames received)")
        else:
            print("VERDICT: TTS FAIL (no audio frames)")


asyncio.run(main())

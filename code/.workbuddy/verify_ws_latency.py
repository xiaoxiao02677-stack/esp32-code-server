#!/usr/bin/env python3
"""Measure WS gateway latency: connect, hello RTT, query-to-first-audio-frame.

Also verifies hello negotiation echo when client advertises 24000 Hz.
"""
import asyncio
import json
import sys
import time

import websockets

DEVICE_ID = "14:c1:9f:d1:33:48"
WS_URL = "ws://sandyun.top:8001/yuhe/v1/"


async def run_once(text: str, sample_rate: int) -> dict:
    headers = [
        ("Authorization", "Bearer test"),
        ("Protocol-Version", "1"),
        ("Device-Id", DEVICE_ID),
        ("Client-Id", "verify-ws-latency"),
    ]
    result = {
        "sample_rate_sent": sample_rate,
        "connect_ms": None,
        "hello_rtt_ms": None,
        "first_audio_ms": None,
        "server_audio_params": None,
        "audio_frames": 0,
        "ok": False,
    }

    t0 = time.perf_counter()
    async with websockets.connect(WS_URL, additional_headers=headers) as ws:
        t1 = time.perf_counter()
        result["connect_ms"] = round((t1 - t0) * 1000, 1)

        hello = {
            "type": "hello",
            "version": 1,
            "transport": "websocket",
            "audio_params": {
                "format": "opus",
                "sample_rate": sample_rate,
                "channels": 1,
                "frame_duration": 60,
            },
        }
        await ws.send(json.dumps(hello))
        t2 = time.perf_counter()

        query_t0 = None
        deadline = time.time() + 30
        try:
            while time.time() < deadline:
                msg = await asyncio.wait_for(ws.recv(), timeout=max(1, deadline - time.time()))
                if isinstance(msg, bytes):
                    result["audio_frames"] += 1
                    if result["first_audio_ms"] is None:
                        result["first_audio_ms"] = round((time.perf_counter() - query_t0) * 1000, 1)
                        # got first frame, enough for latency stats
                        break
                else:
                    data = json.loads(msg)
                    t = data.get("type")
                    if t == "hello":
                        result["hello_rtt_ms"] = round((time.perf_counter() - t2) * 1000, 1)
                        result["server_audio_params"] = data.get("audio_params")
                        # send query now
                        await ws.send(json.dumps({
                            "session_id": "latency-001", "type": "listen",
                            "state": "start", "mode": "manual",
                        }))
                        await ws.send(json.dumps({
                            "session_id": "latency-001", "type": "listen",
                            "state": "detect", "text": text,
                        }))
                        await ws.send(json.dumps({
                            "session_id": "latency-001", "type": "listen",
                            "state": "stop",
                        }))
                        query_t0 = time.perf_counter()
        except (asyncio.TimeoutError, websockets.ConnectionClosed) as e:
            result["error"] = str(e)
            return result

        result["ok"] = result["audio_frames"] > 0
        return result


async def main():
    text = sys.argv[1] if len(sys.argv) > 1 else "网关延迟测试"
    runs = []
    for i in range(3):
        r = await run_once(text, 24000)
        runs.append(r)
        print(f"RUN{i+1}: connect={r['connect_ms']}ms hello_rtt={r['hello_rtt_ms']}ms "
              f"first_audio={r['first_audio_ms']}ms frames={r['audio_frames']} ok={r['ok']}")
        print(f"      server_audio_params={json.dumps(r['server_audio_params'])}")
        await asyncio.sleep(1)

    oks = sum(1 for r in runs if r["ok"])
    lat = [r["first_audio_ms"] for r in runs if r["first_audio_ms"] is not None]
    print(f"\n=== SUMMARY: success={oks}/3 ===")
    if lat:
        print(f"first_audio: min={min(lat)}ms max={max(lat)}ms avg={round(sum(lat)/len(lat),1)}ms")


asyncio.run(main())

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
小智设备 TTS 通信链路模拟器（省略 ASR，文字直转语音）
====================================================
依据 docs/websocket_zh.md 协议 + 服务端 sendTextHandle 实现整理：

通信流程（本脚本模拟设备角色，↘=我们发送，↙=服务器下发）：
  1. WS 连接 ws://sandyun.top:8001/yuhe/v1/（Authorization: Bearer 设备token）
  2. ↘ {"type":"hello","version":1,"transport":"websocket",
  3.    "audio_params":{"format":"opus","sample_rate":16000,"channels":1,"frame_duration":60}}
  4. ↙ {"type":"hello","transport":"websocket",...,"session_id":"..."}
  5. ↘ {"session_id":"...","type":"listen","state":"detect","text":"要合成的文字"}
     ↑ 省略 ASR 的关键：state=detect + text 文本直入
     服务端 listenMessageHandler:115 → startToChat(conn, text) → LLM → TTS
  6. ↙ {"type":"tts","state":"start"}                            ← 进入 speaking
  7. ↙ {"type":"tts","state":"sentence_start","text":"..."}       ← 每句字幕
  8. ↙ 二进制帧（Opus 16kHz 单声道 60ms/帧）                     ← TTS 音频流
  9. ↙ {"type":"tts","state":"stop"}                             ← 播放结束
 10. ↙ {"type":"llm","emotion":"happy","text":"😀"}               ← 表情（可选）

说明：
  - 「省略 ASR」的关键在第 5 步：不发麦克风音频，直接以 listen/detect 携带文本，
    服务器视作"唤醒词检测后的文字输入"走同一条 LLM→TTS→Opus 音频帧管线。
  - 二进制帧为 Opus 编码（与 hello 声明的 audio_params 一致）。
"""

import asyncio
import json
import sys
import wave

import websockets  # pip install websockets

# ================= 配置 =================
WS_URL = "ws://sandyun.top:8001/yuhe/v1/"  # 8001 双协议分流：明文 ws → nginx 9001 → Python 8000
DEVICE_TOKEN = ""  # 设备激活 token；服务器配置 server.auth.enabled=false 时可留空
TEXT = sys.argv[1] if len(sys.argv) > 1 else "你好，我是屿禾工坊的语音助手，很高兴见到你！"
OUT_WAV = "tts_output.wav"
AUDIO_TIMEOUT = 20  # 秒，TTS 音频流静默超时


async def main():
    headers = {
        "Protocol-Version": "1",
        "Device-Id": "14:c1:9f:d1:33:48",   # 模拟设备 MAC（与真实 ESP32 一致）
        "Client-Id": "tts-flow-demo-client",  # 模拟客户端标识
    }
    if DEVICE_TOKEN:
        headers["Authorization"] = "Bearer " + DEVICE_TOKEN
    print(f"[1] 连接 {WS_URL}")
    async with websockets.connect(WS_URL, additional_headers=headers,
                                  max_size=2 ** 22) as ws:
        # ---- hello 握手（设备→服务器）----
        hello = {
            "type": "hello",
            "version": 1,
            "features": {"mcp": True},
            "transport": "websocket",
            "audio_params": {
                "format": "opus",
                "sample_rate": 16000,
                "channels": 1,
                "frame_duration": 60,
            },
        }
        await ws.send(json.dumps(hello))
        print(f"[2] ↘ hello（opus/16k/mono/60ms）")

        # ---- 等服务器 hello（拿 session_id）----
        session_id = None
        while session_id is None:
            raw = await ws.recv()
            msg = json.loads(raw)
            print(f"[3] ↙ {msg.get('type')}: {str(msg)[:120]}")
            if msg.get("type") == "hello":
                session_id = msg.get("session_id", "")
        print(f"    session_id = {session_id}")
        # 服务器连接后异步初始化（模型/TTS 线程），等待就绪再发文本
        await asyncio.sleep(5)

        # ---- listen detect + text 直入（省略 ASR 的核心）----
        # 服务端 listenMessageHandler: state=detect 且带 text（非唤醒词）
        #   → startToChat(conn, text) → LLM → TTS → 二进制 Opus 帧
        await ws.send(json.dumps({
            "session_id": session_id, "type": "listen",
            "state": "detect", "text": TEXT,
        }))
        print(f"[5] ↘ listen detect 文本直入（触发 LLM→TTS）：{TEXT}")

        # ---- 接收 TTS 流 ----
        opus_frames = []
        pcm_frames = []
        subtitle = ""
        state = "speaking"
        try:
            while True:
                raw = await asyncio.wait_for(ws.recv(), timeout=AUDIO_TIMEOUT)
                if isinstance(raw, bytes):
                    opus_frames.append(raw)
                    print(f"\r[6] ↙ 音频帧 #{len(opus_frames)}（opus {len(raw)}B）", end="")
                else:
                    msg = json.loads(raw)
                    t = msg.get("type")
                    if t == "tts":
                        st = msg.get("state")
                        if st == "start":
                            print(f"\n[7] ↙ tts start —— 服务器开始下发语音")
                        elif st == "sentence_start":
                            subtitle = msg.get("text", "")
                            print(f"[8] ↙ 字幕：{subtitle}")
                        elif st == "stop":
                            print("[10] ↙ tts stop —— 播放结束")
                            state = "done"
                            break
                    elif t == "llm":
                        print(f"[11] ↙ 表情：{msg.get('emotion')} {msg.get('text','')}")
                    elif t == "stt":
                        print(f"    ↙ 服务器回显识别文本：{msg.get('text','')[:40]}")
                    else:
                        print(f"    ↙ 其他消息 {t}")
        except asyncio.TimeoutError:
            print("\n[!] 音频流静默超时（服务器未在限时内结束 TTS）")
        except websockets.ConnectionClosed as e:
            print(f"\n[!] 连接关闭：{e}")

    # ---- Opus → WAV 落盘（供试听验证）----
    total = sum(len(f) for f in opus_frames)
    print(f"\n===== 结果 =====")
    print(f"收到 {len(opus_frames)} 个 Opus 帧，共 {total} 字节")
    print(f"字幕：{subtitle}")
    if opus_frames:
        # 逐帧 Opus 解码为 PCM 后拼 WAV（需要 opuslib/pyogg；没有则保存原始 opus 流）
        try:
            import opuslib  # pip install opuslib
            dec = opuslib.Decoder(16000, 1)
            pcm = b"".join(
                dec.decode(f, frame_size=960) for f in opus_frames
            )
            with wave.open(OUT_WAV, "wb") as w:
                w.setnchannels(1)
                w.setsampwidth(2)
                w.setframerate(16000)
                w.writeframes(pcm)
            print(f"已解码并保存 WAV：{OUT_WAV}（{len(pcm)//2} 采样点 ≈ {len(pcm)/32000:.1f}s）")
        except ImportError:
            raw_file = OUT_WAV.replace(".wav", ".opus")
            with open(raw_file, "wb") as f:
                f.write(b"".join(opus_frames))
            print(f"未装 opuslib，已保存原始 Opus 流：{raw_file}（pip install opuslib 后可转 WAV）")


if __name__ == "__main__":
    asyncio.run(main())

#!/usr/bin/env python3
"""E2E 对话级验收：模拟 ESP32 设备 WS 对话，验证 A1「跨会话被记住」。

复用 verify_tts.py 的握手模式（hello + listen start/detect(text)/stop），
两轮会话：
  S1: 「我叫张三，我喜欢听粤语歌」—— 会话结束后服务端异步 save_memory，
      预期 auto_extract 抽取 profile/preference 条目（A1 数据侧）。
  S2: 「你还记得我吗？我喜欢听什么？」—— 预期 query_memory 注入 <memory>
      后 LLM 回答包含「张三」「粤语」（A1 行为侧）。

⚠️ 部署后才有 mem_holographic 与 demo Agent 绑定：
  - 线上（sandyun.top）尚未部署新代码前，本脚本自动 SKIP（默认行为）；
  - 部署后执行：python test_e2e_dialogue.py --run
  - 也可对本地/其他环境：--url ws://IP:PORT/xiaozhi/v1/ --device <mac>

断言逻辑：
  - 通过监听 WS 消息收集 tts 文本（sentence_start 携带 text）；
  - S2 回复需包含「张三」与「粤语」任一（LLM 措辞不可控，用 OR 放宽：
    命中「张三」+（「粤语」或「音乐」）计 PASS；仅命中其一计 WARN）。
  - 数据侧可在服务器本机另查：
    sqlite3 data/memory/{agent_id}.db "SELECT content,category,status FROM facts;"
    预期出现含「张三」的 profile 与含「粤语」的 preference，trust≈0.5。

用法：
  python test_e2e_dialogue.py            # 部署前默认跳过（exit 0，打印 SKIP）
  python test_e2e_dialogue.py --run      # 部署后真跑
  python test_e2e_dialogue.py --run --url ws://sandyun.top:8001/xiaozhi/v1/ \
      --device 14:c1:9f:d1:33:48 --agent-id 03532a34...
"""
import argparse
import asyncio
import json
import sys
import time

try:
    import websockets
except ImportError:
    websockets = None

DEVICE_ID = "14:c1:9f:d1:33:48"           # verify_tts.py 同款设备（my-s3-tft）
WS_URL = "ws://sandyun.top:8001/xiaozhi/v1/"
AGENT_ID = "03532a34"                      # 试点 demo Agent（部署后确认完整 id）

SESSION_1_UTTERANCE = "我叫张三，我喜欢听粤语歌"
SESSION_2_QUESTION = "你还记得我吗？我喜欢听什么？"
DEADLINE_SECONDS = 40


def verdict(tts_texts: list[str], question: str) -> tuple[str, str]:
    joined = "".join(tts_texts)
    has_name = "张三" in joined
    has_song = ("粤语" in joined) or ("音乐" in joined)
    if has_name and has_song:
        return "PASS", f"回复包含[张三]+[粤语/音乐]: {joined[:120]}"
    if has_name or has_song:
        return "WARN", f"仅命中其一（张三={has_name} 粤语/音乐={has_song}）: {joined[:120]}"
    return "FAIL", f"回复未含张三/粤语: {joined[:120]}"


async def run_dialogue(ws_url: str, device_id: str, utterance: str, session_id: str) -> list[str]:
    """One WS connection = one session. Returns collected tts sentence texts."""
    headers = [
        ("Authorization", "Bearer test"),
        ("Protocol-Version", "1"),
        ("Device-Id", device_id),
        ("Client-Id", "qa-e2e-dialogue"),
    ]
    tts_texts: list[str] = []
    async with websockets.connect(ws_url, additional_headers=headers) as ws:
        await ws.send(json.dumps({
            "type": "hello", "version": 1, "transport": "websocket",
            "audio_params": {"format": "opus", "sample_rate": 16000,
                             "channels": 1, "frame_duration": 60},
        }))
        await ws.send(json.dumps({"session_id": session_id, "type": "listen",
                                  "state": "start", "mode": "manual"}))
        await ws.send(json.dumps({"session_id": session_id, "type": "listen",
                                  "state": "detect", "text": utterance}))
        await ws.send(json.dumps({"session_id": session_id, "type": "listen",
                                  "state": "stop"}))

        deadline = time.time() + DEADLINE_SECONDS
        try:
            while time.time() < deadline:
                msg = await asyncio.wait_for(ws.recv(), timeout=max(1, deadline - time.time()))
                if isinstance(msg, bytes):
                    continue
                data = json.loads(msg)
                t = data.get("type")
                if t == "tts" and data.get("state") == "sentence_start":
                    text = str(data.get("text", ""))
                    if text:
                        tts_texts.append(text)
                        print(f"  [tts] {text[:80]}")
                elif t == "tts" and data.get("state") == "stop":
                    break
        except asyncio.TimeoutError:
            print("  [!] 等待回复超时")
        except websockets.ConnectionClosed as e:
            print(f"  [!] 连接关闭: {e}")
    return tts_texts


async def main() -> int:
    parser = argparse.ArgumentParser(description="A1 跨会话记忆 E2E 验收")
    parser.add_argument("--run", action="store_true", help="真正执行（缺省为部署前跳过）")
    parser.add_argument("--url", default=WS_URL, help="WS 地址")
    parser.add_argument("--device", default=DEVICE_ID, help="设备 MAC（试点设备）")
    parser.add_argument("--agent-id", default=AGENT_ID, help="试点 Agent id（记入日志）")
    args = parser.parse_args()

    if not args.run:
        print("SKIP: 线上尚未部署 mem_holographic 新代码（任务 #7 前），E2E 预演跳过。")
        print("      部署后用 --run 执行：python test_e2e_dialogue.py --run")
        return 0

    if websockets is None:
        print("FATAL: 本机无 websockets 库（pip install websockets）")
        return 2

    print(f"[*] 目标 {args.url}，设备 {args.device}，Agent {args.agent_id}")
    ts = time.strftime("%H%M%S")
    s1, s2 = f"qa-e2e-s1-{ts}", f"qa-e2e-s2-{ts}"

    print(f"\n== S1（会话 {s1}）: {SESSION_1_UTTERANCE}")
    s1_texts = await run_dialogue(args.url, args.device, SESSION_1_UTTERANCE, s1)
    print(f"   S1 收集 tts 句数: {len(s1_texts)}")
    # save_memory 在连接关闭后的守护线程异步落库，稍等让其完成
    await asyncio.sleep(3)

    print(f"\n== S2（新会话 {s2}）: {SESSION_2_QUESTION}")
    s2_texts = await run_dialogue(args.url, args.device, SESSION_2_QUESTION, s2)
    print(f"   S2 收集 tts 句数: {len(s2_texts)}")

    status, detail = verdict(s2_texts, SESSION_2_QUESTION)
    print(f"\n=== A1 E2E RESULT: {status} ===")
    print(f"   {detail}")
    print("   数据侧复验（服务器本机）:")
    print("   sqlite3 /root/xiaozhi-server/data/memory/*.db \\")
    print("     \"SELECT content, category, trust_score, status, device_id, session_id FROM facts;\"")
    print("   预期：含[张三]的 profile + 含[粤语]的 preference，trust≈0.5，来源设备/会话非空")
    return 0 if status == "PASS" else (1 if status == "FAIL" else 0)


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))

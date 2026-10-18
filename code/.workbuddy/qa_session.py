#!/usr/bin/env python3
"""QA multi-turn session simulator for yuhe WS server.

Simulates an ordinary user device: multi-turn dialogue inside ONE websocket
connection, plus repeated sessions (separate connections). Collects per-turn
evidence: STT echo, LLM emotion, TTS sentences, audio frame stats, latency,
failure-phrase hits.

Usage:
  python qa_session.py --turns "你好" "一加一等于几" "我刚才说了什么"
  python qa_session.py --sessions 3 --gap 2 --turns "你好" "讲个笑话"
  python qa_session.py --turns-file turns.json     # [["q1","q2"],["q3"]] per session
"""
import argparse
import asyncio
import json
import sys
import time

import websockets

DEVICE_ID = "14:c1:9f:d1:33:48"
WS_URL = "ws://sandyun.top:8001/yuhe/v1/"

# 验收标准第3节：失败标志话术关键词（任一命中即计入）
FAIL_PHRASES = [
    "有点忙", "现在忙", "忙，稍", "抱歉", "对不起", "稍后再", "稍候",
    "无法", "不可用", "暂时不能用", "连接不上", "连不上",
    "没听清", "没听懂", "再说一遍", "出错了", "出了点问题",
    "Sorry", "sorry", "busy", "try again later",
]

MAX_TURN_TIMEOUT = 60      # 单轮最长等待（秒）
SETTLE_AFTER_STOP = 1.2    # tts stop 后等待（秒），模拟用户反应时间


def fail_phrase_hits(sentences):
    hits = []
    for s in sentences:
        for p in FAIL_PHRASES:
            if p in s:
                hits.append({"sentence": s, "phrase": p})
                break
    return hits


async def run_turn(ws, session_id, turn_no, query):
    """One dialogue turn: listen start -> detect(text) -> stop -> collect until tts stop."""
    sid = f"qa-s{session_id}-t{turn_no}"
    result = {
        "session": session_id, "turn": turn_no, "query": query,
        "stt": None, "stt_all": [], "emotion": None, "sentences": [],
        "audio_frames": 0, "audio_bytes": 0,
        "tts_stop": False, "error": None,
        "t0": None, "t_first_sentence": None, "t_first_audio": None, "t_stop": None,
        "other_types": [],
    }
    await ws.send(json.dumps({"session_id": sid, "type": "listen", "state": "start", "mode": "manual"}))
    await ws.send(json.dumps({"session_id": sid, "type": "listen", "state": "detect", "text": query}))
    result["t0"] = time.time()
    await ws.send(json.dumps({"session_id": sid, "type": "listen", "state": "stop"}))

    deadline = time.time() + MAX_TURN_TIMEOUT
    try:
        while time.time() < deadline:
            timeout = max(1.0, deadline - time.time())
            try:
                msg = await asyncio.wait_for(ws.recv(), timeout=timeout)
            except asyncio.TimeoutError:
                result["error"] = "turn timeout"
                break
            if isinstance(msg, bytes):
                result["audio_frames"] += 1
                result["audio_bytes"] += len(msg)
                if result["t_first_audio"] is None:
                    result["t_first_audio"] = time.time()
            else:
                data = json.loads(msg)
                t = data.get("type")
                if t == "tts":
                    state = data.get("state")
                    if state == "sentence_start":
                        result["sentences"].append(data.get("text", ""))
                        if result["t_first_sentence"] is None:
                            result["t_first_sentence"] = time.time()
                    elif state == "stop":
                        result["t_stop"] = time.time()
                        result["tts_stop"] = True
                        break
                elif t == "stt":
                    result["stt"] = data.get("text", "")
                    result["stt_all"].append(data.get("text", ""))
                elif t == "llm":
                    result["emotion"] = data.get("emotion", "")
                elif t not in ("hello",):
                    result["other_types"].append(t)
    except websockets.ConnectionClosed as e:
        result["error"] = f"connection closed: {e}"

    # derived latencies (ms)
    t0 = result["t0"]
    result["latency_first_sentence_ms"] = round((result["t_first_sentence"] - t0) * 1000) if result["t_first_sentence"] else None
    result["latency_first_audio_ms"] = round((result["t_first_audio"] - t0) * 1000) if result["t_first_audio"] else None
    result["latency_total_ms"] = round((result["t_stop"] - t0) * 1000) if result["t_stop"] else None
    result["fail_phrase_hits"] = fail_phrase_hits(result["sentences"])
    # per-turn verdict: audio + tts stop + stt echo + no fail phrases
    result["verdict"] = "PASS" if (
        result["audio_frames"] > 0 and result["tts_stop"]
        and result["stt"] and not result["fail_phrase_hits"] and not result["error"]
    ) else "FAIL"
    for k in ("t0", "t_first_sentence", "t_first_audio", "t_stop"):
        result.pop(k, None)

    tag = f"[S{session_id}T{turn_no}]"
    print(f"{tag} Q: {query}")
    print(f"{tag} STT: {result['stt']} | emotion: {result['emotion']}")
    for s in result["sentences"]:
        print(f"{tag} A: {s}")
    print(f"{tag} audio={result['audio_frames']}f/{result['audio_bytes']}B "
          f"first_audio={result['latency_first_audio_ms']}ms total={result['latency_total_ms']}ms "
          f"tts_stop={result['tts_stop']} verdict={result['verdict']}"
          + (f" error={result['error']}" if result["error"] else ""))
    if result["fail_phrase_hits"]:
        print(f"{tag} !!! FAIL PHRASES: {result['fail_phrase_hits']}")
    sys.stdout.flush()
    return result


async def run_session(session_id, queries, gap):
    """One WS connection with N dialogue turns."""
    sess = {"session": session_id, "turns": [], "connect_ms": None, "error": None}
    headers = [
        ("Authorization", "Bearer test"),
        ("Protocol-Version", "1"),
        ("Device-Id", DEVICE_ID),
        ("Client-Id", f"qa-s{session_id}"),
    ]
    print(f"\n===== SESSION {session_id}: {len(queries)} turns =====")
    t_conn = time.time()
    try:
        async with websockets.connect(WS_URL, additional_headers=headers,
                                      open_timeout=20, ping_interval=15) as ws:
            hello = {
                "type": "hello", "version": 1, "transport": "websocket",
                "audio_params": {"format": "opus", "sample_rate": 16000,
                                 "channels": 1, "frame_duration": 60},
            }
            await ws.send(json.dumps(hello))
            # wait server hello
            msg = await asyncio.wait_for(ws.recv(), timeout=15)
            data = json.loads(msg)
            if data.get("type") != "hello":
                sess["error"] = f"first msg not hello: {data.get('type')}"
            sess["connect_ms"] = round((time.time() - t_conn) * 1000)
            print(f"[S{session_id}] connected+hello in {sess['connect_ms']}ms")

            for i, q in enumerate(queries, 1):
                turn = await run_turn(ws, session_id, i, q)
                sess["turns"].append(turn)
                if turn["error"] and "closed" in str(turn["error"]):
                    break
                if i < len(queries):
                    await asyncio.sleep(gap)
    except Exception as e:
        sess["error"] = f"{type(e).__name__}: {e}"
        print(f"[S{session_id}] SESSION ERROR: {sess['error']}")
    return sess


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--turns", nargs="+", help="queries for one session")
    ap.add_argument("--turns-file", help="JSON: list of query-lists, one per session")
    ap.add_argument("--sessions", type=int, default=1, help="number of sessions (repeats of turns)")
    ap.add_argument("--gap", type=float, default=1.5, help="seconds between turns")
    ap.add_argument("--sess-gap", type=float, default=3.0, help="seconds between sessions")
    ap.add_argument("--out", help="write full JSON result to this file")
    args = ap.parse_args()

    if args.turns_file:
        with open(args.turns_file, encoding="utf-8") as f:
            plan = json.load(f)
        if not isinstance(plan, list) or (plan and isinstance(plan[0], str)):
            plan = [plan]
    elif args.turns:
        plan = [args.turns] * args.sessions
    else:
        print("need --turns or --turns-file")
        sys.exit(2)

    results = []
    for si, queries in enumerate(plan, 1):
        sess = await run_session(si, queries, args.gap)
        results.append(sess)
        if si < len(plan):
            await asyncio.sleep(args.sess_gap)

    # summary
    all_turns = [t for s in results for t in s["turns"]]
    n_pass = sum(1 for t in all_turns if t["verdict"] == "PASS")
    lat_audio = sorted(t["latency_first_audio_ms"] for t in all_turns if t["latency_first_audio_ms"])
    lat_sent = sorted(t["latency_first_sentence_ms"] for t in all_turns if t["latency_first_sentence_ms"])
    fails = [t for t in all_turns if t["verdict"] == "FAIL"]
    sess_errs = [s["error"] for s in results if s["error"]]

    def pct(v, p):
        if not v:
            return None
        idx = min(len(v) - 1, int(len(v) * p / 100))
        return v[idx]

    summary = {
        "total_sessions": len(results),
        "session_errors": sess_errs,
        "total_turns": len(all_turns),
        "turns_pass": n_pass,
        "turns_fail": len(all_turns) - n_pass,
        "fail_turns": [{"session": t["session"], "turn": t["turn"], "query": t["query"],
                        "error": t["error"], "fail_phrase_hits": t["fail_phrase_hits"],
                        "audio_frames": t["audio_frames"], "tts_stop": t["tts_stop"], "stt": t["stt"]}
                       for t in fails],
        "first_audio_ms": {"p50": pct(lat_audio, 50), "p95": pct(lat_audio, 95),
                           "min": lat_audio[0] if lat_audio else None,
                           "max": lat_audio[-1] if lat_audio else None},
        "first_sentence_ms": {"p50": pct(lat_sent, 50), "p95": pct(lat_sent, 95)},
        "fail_phrase_total": sum(len(t["fail_phrase_hits"]) for t in all_turns),
    }
    print("\n===== SUMMARY =====")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump({"summary": summary, "sessions": results}, f, ensure_ascii=False, indent=2)
        print(f"[written] {args.out}")


if __name__ == "__main__":
    asyncio.run(main())

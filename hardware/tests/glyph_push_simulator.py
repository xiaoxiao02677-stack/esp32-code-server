#!/usr/bin/env python3
"""动态字形推送（glyph_push）端到端验收模拟器。

作用：以与服务端同一份契约（固件 main/protocols/text_glyph_payload.cc）构造 hello 能力声明，
连上真实 xiaozhi-server 的 WebSocket，触发一轮文本下发，把收到的 glyph_push 载荷
按**固件 Parse() 的每一条拒绝规则**逐项复检。

用法：
    python glyph_push_simulator.py ws://sandyun.top:8001/xiaozhi/v1/ --mac <真实设备MAC> \
        --text "你好小禾，请用一句话介绍你自己" --charset basic

    # 负向（未声明能力，应完全不下发）
    python glyph_push_simulator.py ws://sandyun.top:8001/xiaozhi/v1/ --mac <MAC> --no-glyph

依赖：websockets（生产 venv 已内置）
退出码：0=通过，1=失败
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import json
import sys
import time
import uuid

try:
    import websockets
except ImportError:  # pragma: no cover
    print("需要 websockets 库：pip install websockets")
    raise SystemExit(2)

MAX_GLYPHS = 64
MAX_BITMAP_BYTES = 64 * 1024


def firmware_parse(root: dict, capability: dict):
    """复刻 text_glyph_payload.cc::Parse()。返回 (ok, parsed_glyphs, reason)"""
    payload = root.get("glyph_push")
    if not isinstance(payload, dict):
        return True, [], "无 glyph_push 字段（固件直接放行）"

    v = payload.get("v")
    bundle = payload.get("bundle")
    size = payload.get("size")
    wire_bpp = payload.get("bpp")
    glyphs = payload.get("glyphs")

    if not (
        isinstance(v, (int, float))
        and int(v) == 1
        and isinstance(bundle, str)
        and bundle == capability.get("bundle")
        and isinstance(size, (int, float))
        and size == capability.get("size")
        and isinstance(wire_bpp, (int, float))
        and wire_bpp == capability.get("bpp")
        and isinstance(glyphs, list)
        and len(glyphs) <= MAX_GLYPHS
    ):
        return False, [], "Rejected incompatible glyph payload"

    parsed_bpp = int(wire_bpp)
    parsed, total = [], 0
    for item in glyphs:
        cp, adv_w = item.get("codepoint"), item.get("adv_w")
        box_w, box_h = item.get("box_w"), item.get("box_h")
        ofs_x, ofs_y = item.get("ofs_x"), item.get("ofs_y")
        bitmap = item.get("bitmap")

        def num(x):
            return isinstance(x, (int, float)) and not isinstance(x, bool)

        if not (
            num(cp) and 0 < cp <= 0x10FFFF
            and num(adv_w) and 0 <= adv_w <= 0xFFFFFFFF
            and num(box_w) and 0 <= int(box_w) <= 64
            and num(box_h) and 0 <= int(box_h) <= 64
            and num(ofs_x) and -32768 <= int(ofs_x) <= 32767
            and num(ofs_y) and -32768 <= int(ofs_y) <= 32767
            and isinstance(bitmap, str)
        ):
            return False, [], f"Rejected malformed glyph: U+{int(cp) if num(cp) else '?'}"

        expected = (int(box_w) * int(box_h) * parsed_bpp + 7) // 8
        total += expected
        if total > MAX_BITMAP_BYTES:
            return False, [], "Rejected oversized glyph payload"
        if len(bitmap) > ((expected + 2) // 3) * 4 + 4:
            return False, [], "Rejected oversized base64 bitmap"
        if expected == 0:
            if bitmap:
                return False, [], "空字形必须为空 bitmap"
        else:
            try:
                raw = base64.b64decode(bitmap, validate=True)
            except Exception as e:  # noqa: BLE001
                return False, [], f"base64 解码失败: {e}"
            if len(raw) != expected:
                return False, [], (
                    f"Rejected invalid bitmap for U+{int(cp):04X}: "
                    f"decoded={len(raw)} expected={expected}"
                )
        parsed.append({"codepoint": int(cp), "box": (int(box_w), int(box_h))})
    return True, parsed, "ok"


async def run(args) -> int:
    capability = {
        "bundle": args.bundle,
        "charset": args.charset,
        "size": args.size,
        "bpp": args.bpp,
    }
    session_id = uuid.uuid4().hex
    sep = "&" if "?" in args.uri else "?"
    uri = f"{args.uri}{sep}device-id={args.mac}"

    hello = {
        "type": "hello",
        "version": 1,
        "features": {"mcp": False} if args.no_glyph else {"mcp": False, "glyph_push": True},
        "transport": "websocket",
        "audio_params": {
            "format": "opus",
            "sample_rate": 16000,
            "channels": 1,
            "frame_duration": 60,
        },
    }
    if not args.no_glyph:
        hello["text_font"] = capability

    print(f"# 连接 {uri}")
    print(f"# hello: {json.dumps(hello, ensure_ascii=False)}")
    stats = {"text": 0, "glyph": 0, "audio": 0, "bad": 0}

    async with websockets.connect(uri, max_size=None, open_timeout=15) as ws:
        await ws.send(json.dumps(hello))
        first = await asyncio.wait_for(ws.recv(), timeout=15)
        print(f"# 服务端 hello: {first}")

        detect = {
            "session_id": session_id,
            "type": "listen",
            "state": "detect",
            "text": args.text,
        }
        print(f"# 发送 listen/detect: {json.dumps(detect, ensure_ascii=False)}")
        await ws.send(json.dumps(detect))

        deadline = time.time() + args.seconds
        while time.time() < deadline:
            try:
                msg = await asyncio.wait_for(ws.recv(), timeout=max(1, deadline - time.time()))
            except asyncio.TimeoutError:
                break
            if isinstance(msg, (bytes, bytearray)):
                stats["audio"] += 1
                continue
            try:
                root = json.loads(msg)
            except Exception:  # noqa: BLE001
                continue
            if "text" not in root:
                continue
            stats["text"] += 1
            has = "glyph_push" in root
            stats["glyph"] += int(has)
            ok, parsed, reason = firmware_parse(root, capability)
            stats["bad"] += int(not ok)
            gp = root.get("glyph_push") or {}
            gl = gp.get("glyphs") or []
            print(
                f"<- type={root.get('type')} state={root.get('state')} "
                f"text={root.get('text')!r} glyph_push={'YES' if has else 'no'}"
            )
            if has:
                cps = " ".join(f"U+{g['codepoint']:04X}" for g in parsed[:12])
                print(
                    f"   固件校验: {'PASS' if ok else 'FAIL'} ({reason}) | "
                    f"bundle={gp.get('bundle')} {gp.get('size')}_{gp.get('bpp')} "
                    f"glyphs={len(gl)} | {cps}"
                )
            else:
                print(f"   固件校验: {'PASS' if ok else 'FAIL'} ({reason})")

    print()
    print(
        f"# 统计: 文本消息={stats['text']} 含 glyph_push={stats['glyph']} "
        f"二进制音频帧={stats['audio']} 固件校验失败={stats['bad']}"
    )
    if args.no_glyph:
        return 0 if stats["glyph"] == 0 else 1
    return 0 if (stats["glyph"] > 0 and stats["bad"] == 0) else 1


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("uri", help="如 ws://sandyun.top:8001/xiaozhi/v1/")
    p.add_argument("--mac", required=True, help="必须是服务端已登记的真实设备 MAC")
    p.add_argument("--text", default="你好小禾，请用一句话介绍你自己")
    p.add_argument("--bundle", default="noto-v1")
    p.add_argument("--charset", default="basic", choices=("basic", "common"))
    p.add_argument("--size", type=int, default=20)
    p.add_argument("--bpp", type=int, default=4, choices=(1, 4))
    p.add_argument("--no-glyph", action="store_true", help="负向：不声明能力，应零下发")
    p.add_argument("--seconds", type=float, default=40)
    args = p.parse_args()
    return asyncio.run(run(args))


if __name__ == "__main__":
    sys.exit(main())

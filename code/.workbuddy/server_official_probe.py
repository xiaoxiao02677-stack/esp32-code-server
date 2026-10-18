#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""服务器端实测：用项目真实的 TTSProvider 发请求，验证对齐官方脚本后能出音频。

直接驱动 core/providers/tts/doubao_v3.py，打印它实际发出的 payload，
确认「用户语气指令 -> additions.context_texts」链路在线上可用。
"""
import asyncio
import json
import sys

sys.path.insert(0, "/root/xiaozhi-server/main/yuhe-server")

from core.providers.tts.doubao_v3 import TTSProvider  # noqa: E402

BASE = {
    "api_key": "d9f77dba-01ca-47fa-a4d3-7002adf6b6a4",
    "resource_id": "seed-icl-2.0",
    "private_voice": "S_N8pC5xwg2",
    "format": "mp3",
    "sample_rate": 24000,
}

TEXT = "今天真是个好日子，我们一起出去玩吧！"

CASES = [
    ("01 基线：无语气指令", {}, None),
    ("02 固定指令：开心", {"voice_instruction": "用非常开心、兴奋、雀跃的语气说话"}, None),
    ("03 动态指令：生气（用户每轮传入）", {}, "用很生气愤怒的语气说话"),
    ("04 动态指令：难过", {}, "用难过伤心、带哭腔的语气说话"),
    ("05 显式 model（回退验证）",
     {"voice_instruction": "用开心的语气说话", "model": "seed-tts-2.0-expressive"}, None),
]


def main():
    print("=" * 72)
    print("服务器实测：对齐官方脚本后的 doubao_v3 请求包")
    print("=" * 72)

    ok_count = 0
    for name, extra, dyn in CASES:
        print(f"\n--- {name} ---")
        cfg = dict(BASE)
        cfg.update(extra)
        try:
            p = TTSProvider(cfg, delete_audio_file=False)
            if dyn:
                p.set_dynamic_instruction(dyn)
            payload = p._build_payload(TEXT)
            print("  [实际发出] " + json.dumps(payload, ensure_ascii=False))
            data = asyncio.run(p.text_to_speak(TEXT, None))
            n = len(data) if data else 0
            print(f"  -> 音频 {n} 字节 {'✔' if n else '✘ 空音频'}")
            if n:
                ok_count += 1
        except Exception as e:
            print(f"  -> 失败: {e}")

    print("\n" + "=" * 72)
    print(f"结果：{ok_count}/{len(CASES)} 个用例产出音频")
    print("=" * 72)


if __name__ == "__main__":
    main()

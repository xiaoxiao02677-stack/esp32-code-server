# 临时性能探测脚本（live-prober，2026-10-13）：仅放 /tmp，只读调用项目模块，不修改项目文件
import asyncio
import sys
import os
import time

sys.path.insert(0, "/root/yh/app/xiaozhi-server")
os.chdir("/root/yh/app/xiaozhi-server")

import logging

logging.basicConfig(level=logging.WARNING)

from config.settings import load_config
from core.utils.llm import create_instance

SENTENCES = [
    "你好，我今天心情不太好，能安慰一下我吗？",
    "帮我查一下明天的天气如何？",
    "我想听一个有趣的故事，你能给我讲一个吗？",
    "现在几点了？今天是星期几？",
    "我想设置一个明天早上8点的闹钟提醒我开会",
]

MODEL_OVERRIDE = os.environ.get("PERF_MODEL_OVERRIDE", "")


async def main():
    cfg = await load_config()
    llm_cfg = cfg.get("LLM", {}).get("LLM_DeepSeek")
    env_json = os.environ.get("LLM_CFG_JSON", "")
    if env_json:
        import json

        llm_cfg = json.loads(env_json)
    if not llm_cfg:
        print("NO_LLM_CONFIG")
        return
    if MODEL_OVERRIDE:
        llm_cfg = dict(llm_cfg)
        llm_cfg["model_name"] = MODEL_OVERRIDE
    llm = create_instance(llm_cfg["type"], llm_cfg)
    print(
        f"provider={type(llm).__name__} model={llm_cfg.get('model_name')} base_url={llm_cfg.get('base_url')}",
        flush=True,
    )
    results = []
    for i, s in enumerate(SENTENCES, 1):
        t0 = time.time()
        first = None
        chunks = 0
        chars = 0
        err = None
        try:
            messages = [
                {
                    "role": "system",
                    "content": "你是小智，一个聪明可爱的AI助手。请用温暖友善的语气回复用户，回复保持简短。",
                },
                {"role": "user", "content": s},
            ]
            gen = llm.response("perf_probe", messages)
            try:
                for chunk in gen:
                    if first is None and chunk:
                        first = time.time() - t0
                    chunks += 1
                    if isinstance(chunk, str):
                        chars += len(chunk)
            except Exception as e:
                err = f"stream_error: {type(e).__name__}: {e}"
        except Exception as e:
            err = f"error: {type(e).__name__}: {e}"
        total = time.time() - t0
        results.append((i, first, total, chunks, chars, err))
        print(
            f"[{i}/{len(SENTENCES)}] first_token={('%.2f' % first) if first is not None else 'N/A'}s "
            f"total={total:.2f}s chunks={chunks} chars={chars} err={err}",
            flush=True,
        )
        await asyncio.sleep(1)

    ok = [r for r in results if r[1] is not None and r[5] is None]

    def pct(vals, p):
        if not vals:
            return float("nan")
        vals = sorted(vals)
        k = max(0, min(len(vals) - 1, int(round(p / 100 * (len(vals) - 1)))))
        return vals[k]

    if ok:
        ft = [r[1] for r in ok]
        tt = [r[2] for r in ok]
        print(
            f"SUMMARY ok={len(ok)}/{len(SENTENCES)} "
            f"first_token p50={pct(ft, 50):.2f}s p95={pct(ft, 95):.2f}s "
            f"total p50={pct(tt, 50):.2f}s p95={pct(tt, 95):.2f}s"
        )
    else:
        print("SUMMARY ok=0 全部失败")


asyncio.run(main())

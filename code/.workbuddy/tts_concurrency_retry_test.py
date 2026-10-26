#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""TTS 并发压测（生产重试语义版）：20 并发 × 5 次重试无退避。

复刻生产 tts/base.py to_tts 的重试行为（max_repeat_time=5，异常立即重试，
45000292 并发超限不在快速失败清单），看 20 设备同时说话的最终成功率。
"""
import concurrent.futures
import os
import sys
import time

sys.path.insert(0, "/root/xiaozhi-server/main/xiaozhi-server")

from core.providers.tts.doubao_v3 import TTSProvider  # noqa: E402

CFG = {
    "type": "doubao_v3",
    "format": "wav",
    "api_key": "d9f77dba-01ca-47fa-a4d3-7002adf6b6a4",
    "api_url": "https://openspeech.bytedance.com/api/v3/tts/unidirectional",
    "speaker": "zh_female_xiaohe_uranus_bigtts",
    "output_dir": "tmp/",
    "resource_id": "seed-tts-2.0",
    "sample_rate": 24000,
    "speech_rate": 0,
    "language": "普通话",
    "tts_timeout": 15,
    "appid": "2717008086",
}

TEXTS = [
    "你好，我是屿禾工坊的语音助手，很高兴认识你。",
    "今天天气不错，适合出门散散步。",
    "给我讲一个关于小机器人第一次看海的故事。",
    "现在几点了？我一会儿还有事情要安排。",
    "把音量调到百分之五十，谢谢。",
    "我喜欢安静的东西，比如深夜的雨声。",
    "酸得干脆，不装甜，这就是我的态度。",
    "帮我查一下明天北京的天气怎么样。",
    "晚安，祝你做个好梦，明天见。",
    "这个故事有点长，你慢慢讲，我不着急。",
    "你知道吗，修表铺的沈师傅已经干了四十年了。",
    "播放一首轻音乐，我想放松一下。",
    "屏幕亮度调亮一点，刚才有点看不清。",
    "主人的日程提醒已经设置好了，下午三点开会。",
    "今天学到了新东西，感觉特别充实。",
    "周末要不要一起去公园放风筝？",
    "我记得你上次说过喜欢喝柠檬水。",
    "这个问题有点难，让我想一想再回答你。",
    "谢谢你陪我聊天，心情好多了。",
    "最后那块表没卖，一直戴在年轻人腕上走了十年。",
]

import asyncio


def run_one(i):
    """复刻 to_tts 重试语义：5 次，异常立即重试，无退避。"""
    import copy
    text = TEXTS[i % len(TEXTS)]
    p = TTSProvider(copy.deepcopy(CFG), False)
    max_repeat = 5
    t0 = time.time()
    retries = 0
    last_err = ""
    while max_repeat > 0:
        try:
            audio = asyncio.run(p.text_to_speak(text, None))
            if audio:
                ms = (time.time() - t0) * 1000
                return (i, True, ms, len(audio), retries, "")
            max_repeat -= 1
        except Exception as e:
            last_err = str(e)[:100]
            retries += 1
            max_repeat -= 1
    ms = (time.time() - t0) * 1000
    return (i, False, ms, 0, retries, last_err)


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 20
    print(f"{'='*62}")
    print(f"TTS 并发压测（生产重试语义 5 次无退避）：{n} 请求")
    print(f"{'='*62}")
    t_start = time.time()
    with concurrent.futures.ThreadPoolExecutor(max_workers=n) as ex:
        results = list(ex.map(run_one, range(n)))
    total = (time.time() - t_start) * 1000

    oks = [r for r in results if r[1]]
    fails = [r for r in results if not r[1]]
    lat = sorted(r[2] for r in oks)

    def pct(p):
        return lat[min(len(lat) - 1, int(len(lat) * p))] if lat else 0

    for r in results:
        i, ok, ms, size, retries, err = r
        mark = "OK " if ok else "FAIL"
        print(f"[{mark}] #{i:02d} {ms:7.0f}ms {size//1024:4d}KB 重试{retries}次"
              + (f"  ERR: {err}" if err else ""))

    print(f"\n{'='*62}")
    print(f"总计: {n} | 成功 {len(oks)} | 失败 {len(fails)} | 总耗时 {total:.0f}ms")
    if oks:
        print(f"延迟: min={lat[0]:.0f}ms p50={pct(0.5):.0f}ms p90={pct(0.9):.0f}ms max={lat[-1]:.0f}ms")
        total_retries = sum(r[4] for r in results)
        print(f"总重试次数: {total_retries}（成功请求平均重试 {sum(r[4] for r in oks)/max(1,len(oks)):.1f} 次）")
    if fails:
        print("失败明细:")
        for r in fails:
            print(f"  #{r[0]:02d} 重试{r[4]}次后仍失败: {r[5]}")


if __name__ == "__main__":
    main()

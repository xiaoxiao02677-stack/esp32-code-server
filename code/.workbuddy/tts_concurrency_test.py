#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""TTS 并发压测：20 个请求同时发起，测豆包 v3 端点真实并发能力。

在生产服务器上运行（网络路径与生产一致）。用 ThreadPoolExecutor 绕开
requests 同步阻塞——生产 asyncio 事件循环里 text_to_speak 是同步调用，
事件循环会把并发串行化；线程池才能测出上游 API 的真实并发上限。

用法（生产服务器）：
    python3 /tmp/tts_concurrency_test.py [N]      # 默认 20
"""
import concurrent.futures
import os
import sys
import time

sys.path.insert(0, "/root/xiaozhi-server/main/xiaozhi-server")

from core.providers.tts.doubao_v3 import TTSProvider  # noqa: E402

# 线上真实配置（TTS_DoubaoV3，data/.config.yaml 无 TTS 段，运行时从 Java API 拉；
# 取自生产日志 2026-10-19 13:38 会话 dump 的 agent 级配置）
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

# 20 条不同文本（模拟 20 个设备同时要合成；长度不一更贴近真实）
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


def make_provider(idx):
    """每个线程独立 provider 实例（生产中每连接独立实例）。"""
    import copy
    p = TTSProvider(copy.deepcopy(CFG), False)
    p.output_dir = "/tmp/tts_conc"
    return p


def run_one(i):
    text = TEXTS[i % len(TEXTS)]
    out = f"/tmp/tts_conc/out_{i:02d}.wav"
    t0 = time.time()
    try:
        p = make_provider(i)
        # text_to_speak 是同步阻塞（生产事件循环里也这样跑）
        import asyncio
        asyncio.run(p.text_to_speak(text, out))
        ms = (time.time() - t0) * 1000
        size = os.path.getsize(out) if os.path.exists(out) else 0
        return (i, True, ms, size, text[:18], "")
    except Exception as e:
        ms = (time.time() - t0 * 1) * 1000 if False else (time.time() - t0) * 1000
        return (i, False, ms, 0, text[:18], str(e)[:120])


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 20
    os.makedirs("/tmp/tts_conc", exist_ok=True)
    # 清旧产物
    for f in os.listdir("/tmp/tts_conc"):
        os.unlink(os.path.join("/tmp/tts_conc", f))

    print(f"{'='*62}")
    print(f"TTS 并发压测：{n} 请求同时发起（豆包 v3 unidirectional）")
    print(f"音色: {CFG['speaker']}  resource: {CFG['resource_id']}")
    print(f"{'='*62}")

    t_start = time.time()
    results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=n) as ex:
        futs = [ex.submit(run_one, i) for i in range(n)]
        for f in concurrent.futures.as_completed(futs):
            r = f.result()
            results.append(r)
            i, ok, ms, size, txt, err = r
            mark = "OK " if ok else "FAIL"
            print(f"[{mark}] #{i:02d} {ms:7.0f}ms {size//1024:4d}KB  {txt}"
                  + (f"  ERR: {err}" if err else ""))
    total = (time.time() - t_start) * 1000

    results.sort(key=lambda r: r[0])
    oks = [r for r in results if r[1]]
    fails = [r for r in results if not r[1]]
    lat = sorted(r[2] for r in oks)

    def pct(p):
        return lat[min(len(lat) - 1, int(len(lat) * p))] if lat else 0

    print(f"\n{'='*62}")
    print(f"总计: {n} 请求 | 成功 {len(oks)} | 失败 {len(fails)} | 总耗时 {total:.0f}ms")
    if oks:
        print(f"延迟: min={lat[0]:.0f}ms  p50={pct(0.5):.0f}ms  "
              f"p90={pct(0.9):.0f}ms  max={lat[-1]:.0f}ms")
        print(f"有效并发吞吐: {len(oks)/(total/1000):.1f} req/s")
    if fails:
        print("\n失败明细:")
        for r in fails:
            print(f"  #{r[0]:02d}: {r[5]}")
        # 失败分类
        errs = {}
        for r in fails:
            key = r[5][:60]
            errs[key] = errs.get(key, 0) + 1
        print("错误分布:", errs)


if __name__ == "__main__":
    main()

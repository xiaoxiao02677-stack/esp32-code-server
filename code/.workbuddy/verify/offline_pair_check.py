#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""唤醒词「双键成对」离线实跑校验（零副作用，不连服务、不写盘、不建连接）。

目的：在不依赖任何设备 WS 会话的前提下，证明 wake_word_service.push_wake_words
真正产出的 payload 形态，以及 _on_sent 对 conn.config["wakeup_words"] 的同步口径。

做法：把 _push_device_config 替换成捕获器，只观察 payload 与 on_sent，
不触发真实推送/离线队列/数据库。

用法：python offline_pair_check.py
"""
import asyncio
import json
import os
import sys

_REPO = os.path.dirname(  # <repo>
    os.path.dirname(  # code
        os.path.dirname(  # .workbuddy
            os.path.dirname(os.path.abspath(__file__)))))  # verify
sys.path.insert(0, os.path.join(_REPO, "yh", "yuhe-server"))

from core.services.wake_word_service import WakeWordService  # noqa: E402


class Capture:
    """接住 _push_device_config 的入参，替代真实推送"""

    def __init__(self):
        self.payload = None
        self.on_sent = None
        self.log_tag = None

    async def __call__(self, agent_id, device_id, payload, log_tag="", on_sent=None):
        self.payload = json.loads(json.dumps(payload))
        self.on_sent = on_sent
        self.log_tag = log_tag
        return {"sent": 1, "offline": 0, "failed": 0, "skipped": 0}


class FakeConn:
    def __init__(self, config=None):
        self.config = dict(config or {})


async def run_case(svc, wake_words, display_words):
    cap = Capture()
    svc._push_device_config = cap
    res = await svc.push_wake_words("agent-1", "dev-1", wake_words, display_words=display_words)
    return cap, res


FAIL = 0


def check(name, ok, detail=""):
    global FAIL
    print(("  PASS  " if ok else "  FAIL  ") + name + (("  <" + detail + ">") if detail and not ok else ""))
    if not ok:
        FAIL += 1


async def main():
    svc = WakeWordService()

    print("== 用例1：正常双键（拼音 + 汉字）==")
    cap, res = await run_case(svc, ["zao shang hao"], ["早上好"])
    print("   payload =", json.dumps(cap.payload, ensure_ascii=False))
    check("payload 含 wake_word", cap.payload.get("wake_word") == ["zao shang hao"], str(cap.payload))
    check("payload 含 wake_word_display", cap.payload.get("wake_word_display") == ["早上好"], str(cap.payload))
    check("两数组等长", len(cap.payload["wake_word"]) == len(cap.payload["wake_word_display"]))
    check("log_tag = 唤醒词", cap.log_tag == "唤醒词", str(cap.log_tag))
    check("on_sent 已注册", cap.on_sent is not None)

    print("\n== 用例2：多词同序 ==")
    cap, res = await run_case(svc, ["zao shang hao", "guan deng", "xiao fang kuai"],
                             ["早上好", "关灯", "小方块"])
    print("   payload =", json.dumps(cap.payload, ensure_ascii=False))
    check("3 词成对且同序",
          cap.payload.get("wake_word") == ["zao shang hao", "guan deng", "xiao fang kuai"]
          and cap.payload.get("wake_word_display") == ["早上好", "关灯", "小方块"],
          str(cap.payload))

    print("\n== 用例3：display 参差（一项缺）→ 回落命令词自身，仍等长 ==")
    cap, res = await run_case(svc, ["zao shang hao", "guan deng"], ["早上好", ""])
    print("   payload =", json.dumps(cap.payload, ensure_ascii=False))
    check("缺 display 的位置回落 pinyin", cap.payload.get("wake_word_display") == ["早上好", "guan deng"],
          str(cap.payload))
    check("参差时两数组仍等长", len(cap.payload["wake_word"]) == len(cap.payload["wake_word_display"]))

    print("\n== 用例4：display_words=None（老链路，wake_words 即汉字）→ 不发 display 键 ==")
    cap, res = await run_case(svc, ["早上好"], None)
    print("   payload =", json.dumps(cap.payload, ensure_ascii=False))
    check("无 wake_word_display 键", "wake_word_display" not in cap.payload, str(cap.payload))

    print("\n== 用例5：display_words=[] 显式空 → 不发 display 键 ==")
    cap, res = await run_case(svc, ["zao shang hao"], [])
    print("   payload =", json.dumps(cap.payload, ensure_ascii=False))
    check("无 wake_word_display 键", "wake_word_display" not in cap.payload, str(cap.payload))

    print("\n== 用例6：超 5 条 → 截断到 5 且仍等长 ==")
    cap, res = await run_case(svc, ["a a", "b b", "c c", "d d", "e e", "f f"],
                             ["甲", "乙", "丙", "丁", "戊", "己"])
    print("   payload =", json.dumps(cap.payload, ensure_ascii=False))
    check("截断到 5", len(cap.payload["wake_word"]) == 5, str(len(cap.payload["wake_word"])))
    check("截断后仍等长", len(cap.payload["wake_word"]) == len(cap.payload.get("wake_word_display", [])))
    check("截断保序（不压缩下标）", cap.payload.get("wake_word_display") == ["甲", "乙", "丙", "丁", "戊"],
          str(cap.payload))

    print("\n== 用例7：中间有空命令词 → 成对剔除，display 不错位 ==")
    cap, res = await run_case(svc, ["zao shang hao", "", "guan deng"], ["早上好", "乙", "关灯"])
    print("   payload =", json.dumps(cap.payload, ensure_ascii=False))
    check("空词整条剔除", cap.payload.get("wake_word") == ["zao shang hao", "guan deng"], str(cap.payload))
    check("display 跟着剔除而非错位", cap.payload.get("wake_word_display") == ["早上好", "关灯"], str(cap.payload))

    print("\n== 用例8：_on_sent 全汉字 display → 词表写汉字（不写拼音）==")
    cap, _ = await run_case(svc, ["zao shang hao"], ["早上好"])
    conn = FakeConn({"wakeup_words": ["旧词"]})
    cap.on_sent(conn)
    print("   conn.config =", json.dumps(conn.config, ensure_ascii=False))
    check("wakeup_words = 汉字", conn.config.get("wakeup_words") == ["早上好"], str(conn.config))

    print("\n== 用例9：_on_sent display 参差 → 整组不动（防拼音污染词表）==")
    cap, _ = await run_case(svc, ["zao shang hao", "guan deng"], ["早上好", ""])
    conn = FakeConn({"wakeup_words": ["旧词"]})
    cap.on_sent(conn)
    print("   conn.config =", json.dumps(conn.config, ensure_ascii=False))
    check("参差 display 不覆盖词表", conn.config.get("wakeup_words") == ["旧词"], str(conn.config))

    print("\n== 用例10：_on_sent 老链路 None → 词表写 wake_words（本身是汉字）==")
    cap, _ = await run_case(svc, ["早上好"], None)
    conn = FakeConn({"wakeup_words": ["旧词"]})
    cap.on_sent(conn)
    print("   conn.config =", json.dumps(conn.config, ensure_ascii=False))
    check("老链路词表 = wake_words", conn.config.get("wakeup_words") == ["早上好"], str(conn.config))

    print("\n== 用例11：_on_sent display 显式空 → 不动词表（不可信）==")
    cap, _ = await run_case(svc, ["zao shang hao"], [])
    conn = FakeConn({"wakeup_words": ["旧词"]})
    cap.on_sent(conn)
    print("   conn.config =", json.dumps(conn.config, ensure_ascii=False))
    check("显式空不覆盖词表", conn.config.get("wakeup_words") == ["旧词"], str(conn.config))

    print("\n== 用例12：_on_sent 空数组 → 服务端词表清空 ==")
    cap, _ = await run_case(svc, [], [])
    conn = FakeConn({"wakeup_words": ["旧词"]})
    cap.on_sent(conn)
    print("   conn.config =", json.dumps(conn.config, ensure_ascii=False))
    check("清空词表", conn.config.get("wakeup_words") == [], str(conn.config))

    print("\nRESULT=" + ("ALL_PASS" if FAIL == 0 else "FAILED:%d" % FAIL))
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))

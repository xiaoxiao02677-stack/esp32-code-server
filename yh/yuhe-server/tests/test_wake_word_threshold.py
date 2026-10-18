#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""唤醒词阈值下发链路 · 模拟端到端验证

模拟「manager-api 保存阈值 → Python WS 直投 → 设备收帧」的完整下发流程。
固件侧 board.cc ApplyDeviceConfig 的解析契约以注释形式逐项断言：
    payload.wake_word_threshold ∈ [0,100]（cJSON_IsNumber）
    → NVS("wake_word_config").threshold 持久
    → AudioService.SetWakeWordThreshold(t/100) 热生效
    → 固件 0 夹取到 0.01（esp-sr 最低有效值）
另含 wake_word / wake_word_display 双数组配对契约（同序等长、成对剔除、
参差 display 不污染 wakeup_words、孤儿 display 守卫），见用例 10/11。

运行：python tests/test_wake_word_threshold.py
"""
import asyncio
import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
# tests/ 自带遮蔽用的 core/ 常规包（tests/core/__init__.py），常规包优先于
# 命名空间包，必须把 sys.path[0]（脚本所在 tests/）摘掉再挂根目录，
# 否则 import core.services 解析到空的 tests/core
_here = str(Path(__file__).resolve().parent)
sys.path = [p for p in sys.path if str(Path(p).resolve()) != _here]
sys.path.insert(0, str(_ROOT))

from core.services.wake_word_service import WakeWordService  # noqa: E402


# ---------- 测试桩：模拟固件连接 ----------

class FakeWebSocket:
    def __init__(self, fail=False, closed=False):
        self.sent = []
        self.fail = fail
        self.closed = closed

    async def send(self, data):
        if self.fail:
            raise ConnectionError("simulated send failure")
        self.sent.append(data)


class FakeConn:
    """模拟 connection.py 的设备连接对象"""

    def __init__(self, fail=False, closed=False, need_bind=False, mqtt_gateway=False):
        self.websocket = FakeWebSocket(fail=fail, closed=closed)
        self.need_bind = need_bind
        self.conn_from_mqtt_gateway = mqtt_gateway
        self.config = {}

    @property
    def frames(self):
        return [json.loads(x) for x in self.websocket.sent]


def check(name, cond, detail=""):
    mark = "PASS" if cond else "FAIL"
    print(f"[{mark}] {name}" + (f"  ({detail})" if detail else ""))
    return cond


async def test_online_push():
    """用例 1：在线设备直推，帧格式与固件解析契约一致"""
    svc = WakeWordService()
    conn = FakeConn()
    svc._connections["14:c1:9f:aa:bb:cc"] = conn
    svc.register_agent_device("agent-1", "14:c1:9f:aa:bb:cc")

    result = await svc.push_wake_word_threshold(agent_id="agent-1", threshold=40)
    ok = check("在线直推 result.sent == 1", result["sent"] == 1, str(result))
    frames = conn.frames
    ok &= check("收到且仅收到 1 帧", len(frames) == 1)
    frame = frames[0] if frames else {}
    ok &= check("帧 type == device_config（固件 application.cc 只认此 type）",
                frame.get("type") == "device_config", str(frame))
    payload = frame.get("payload", {})
    ok &= check("payload.wake_word_threshold == 40",
                payload.get("wake_word_threshold") == 40, str(payload))
    ok &= check("payload 无多余键（严格契约）", set(payload.keys()) == {"wake_word_threshold"})
    # 固件解析等价断言：t=40 → SetThreshold(0.40)，处于 esp-sr 有效域
    t = payload.get("wake_word_threshold")
    ok &= check("固件侧换算 40/100=0.40 落在 [0.01,1.0]", isinstance(t, int) and 0 <= t <= 100)
    return ok


async def test_boundary_values():
    """用例 2：0（最灵敏）与 100（最不灵敏）边界值均可下发"""
    svc = WakeWordService()
    ok = True
    for t in (0, 100):
        conn = FakeConn()
        svc._connections[f"dev-{t}"] = conn
        result = await svc.push_wake_word_threshold(device_id=f"dev-{t}", threshold=t)
        frame = conn.frames[0]
        ok &= check(
            f"边界值 threshold={t} 直推成功且帧值正确",
            result["sent"] == 1 and frame["payload"]["wake_word_threshold"] == t,
            str(frame))
    # 固件契约：0 → SetThreshold(0.0) → clamp 到 0.01（最低有效灵敏度）
    # 100 → SetThreshold(1.0)（最不灵敏）
    return ok


async def test_out_of_range():
    """用例 3：越界值（-1 / 101 / 非整数）在服务层拒绝"""
    svc = WakeWordService()
    ok = True
    for bad in (-1, 101, 40.5):
        try:
            await svc.push_wake_word_threshold(device_id="dev-x", threshold=bad)
            ok &= check(f"越界值 {bad} 被拒绝", False, "未抛出异常")
        except ValueError:
            ok &= check(f"越界值 {bad} 被拒绝", True)
    return ok


async def test_offline_queue_and_replay():
    """用例 4：离线缓存 + 上线补投（对齐唤醒词离线语义）"""
    svc = WakeWordService()
    # 设备不在线：帧进离线队列（每设备只留最新一条）
    r1 = await svc.push_wake_word_threshold(device_id="dev-off", threshold=80)
    ok = check("离线设备 result.offline == 1", r1["offline"] == 1, str(r1))
    queued = svc._offline_queue.get("dev-off", [])
    ok &= check("离线队列缓存了 device_config 帧",
                len(queued) == 1 and queued[0]["payload"]["wake_word_threshold"] == 80)
    # 离线期间再次修改：队列只保留最新值（旧 80 被新 20 覆盖）
    await svc.push_wake_word_threshold(device_id="dev-off", threshold=20)
    queued = svc._offline_queue.get("dev-off", [])
    ok &= check("重复下发覆盖为最新值 20",
                len(queued) == 1 and queued[0]["payload"]["wake_word_threshold"] == 20)
    # 设备上线：register_connection 自动补投
    conn = FakeConn()
    await svc.register_connection("dev-off", conn)
    frames = conn.frames
    ok &= check("上线自动补投 1 帧", len(frames) == 1, str(frames))
    ok &= check("补投帧值 == 最新阈值 20",
                frames and frames[0]["payload"]["wake_word_threshold"] == 20)
    ok &= check("补投后离线队列已清空", "dev-off" not in svc._offline_queue)
    return ok


async def test_skip_unbound_and_mqtt():
    """用例 5：未绑定设备 / MQTT 网关设备跳过（对齐 connection.py 下发策略）"""
    svc = WakeWordService()
    unbound = FakeConn(need_bind=True)
    mqtt = FakeConn(mqtt_gateway=True)
    svc._connections["dev-unbound"] = unbound
    svc._connections["dev-mqtt"] = mqtt
    result = await svc.push_wake_word_threshold(device_id="dev-unbound", threshold=30)
    ok = check("未绑定设备 skipped == 1 且未收到帧",
               result["skipped"] == 1 and unbound.frames == [], str(result))
    result = await svc.push_wake_word_threshold(device_id="dev-mqtt", threshold=30)
    ok &= check("MQTT 网关设备 skipped == 1 且未收到帧",
                result["skipped"] == 1 and mqtt.frames == [], str(result))
    return ok


async def test_send_failure_retries():
    """用例 6：发送失败进离线队列，下次上线重试"""
    svc = WakeWordService()
    broken = FakeConn(fail=True)
    svc._connections["dev-broken"] = broken
    result = await svc.push_wake_word_threshold(device_id="dev-broken", threshold=55)
    ok = check("发送失败 result.failed == 1", result["failed"] == 1, str(result))
    ok &= check("失败帧已入离线队列等待重试",
                len(svc._offline_queue.get("dev-broken", [])) == 1)
    # 修复后上线补投
    fixed = FakeConn()
    await svc.register_connection("dev-broken", fixed)
    ok &= check("恢复后上线补投成功",
                len(fixed.frames) == 1 and fixed.frames[0]["payload"]["wake_word_threshold"] == 55)
    return ok


async def test_wake_words_regression():
    """用例 7：既有唤醒词推送路径回归（重构后委托 _push_device_config）"""
    svc = WakeWordService()
    conn = FakeConn()
    svc._connections["dev-ww"] = conn
    result = await svc.push_wake_words(agent_id=None, device_id="dev-ww",
                                       wake_words=["你好", "早上好"], tts_rate=0)
    frame = conn.frames[0]
    ok = check("唤醒词帧 type/payload 不回归",
               result["sent"] == 1
               and frame["type"] == "device_config"
               and frame["payload"]["wake_word"] == ["你好", "早上好"], str(frame))
    ok &= check("服务端匹配词表同步钩子生效",
                conn.config.get("wakeup_words") == ["你好", "早上好"])
    return ok


async def test_http_handler():
    """用例 8：HTTP 入口 /api/device-config/push（通用 device_config 下发）"""
    import logging
    # BaseHandler.__init__ 会 setup_logging() → 依赖 data/.config.yaml；
    # 单测环境打桩掉，避免拉起真实配置
    import config.logger as _clog
    _clog.setup_logging = lambda *a, **k: logging.getLogger("test")
    from core.api.wake_word_handler import WakeWordHandler
    config = {"server": {"auth_key": "unit-test-secret"}}
    svc = WakeWordService()
    conn = FakeConn()
    svc._connections["dev-http"] = conn
    handler = WakeWordHandler(config, svc)

    class FakeRequest:
        def __init__(self, headers, body):
            self._headers = headers
            self._body = body

        @property
        def headers(self):
            return self._headers

        async def json(self):
            if self._body is None:
                import json as _json
                raise json.JSONDecodeError("bad", "doc", 0)
            return self._body

    ok = True
    good = {"Authorization": "Bearer unit-test-secret"}
    # 1. 无鉴权 → 401
    resp = await handler.handle_push_device_config(
        FakeRequest({}, {"agent_id": "a", "payload": {"wake_word_threshold": 40}}))
    ok &= check("缺少鉴权 → 401", resp.status == 401)
    # 2. 错误 token → 401
    resp = await handler.handle_push_device_config(
        FakeRequest({"Authorization": "Bearer wrong"}, {"agent_id": "a", "payload": {"wake_word_threshold": 40}}))
    ok &= check("错误 token → 401", resp.status == 401)
    # 3. 缺 payload → 400
    resp = await handler.handle_push_device_config(FakeRequest(good, {"agent_id": "a"}))
    ok &= check("缺 payload → 400", resp.status == 400)
    # 4. payload 全为非法键 → 400（白名单兜底）
    resp = await handler.handle_push_device_config(
        FakeRequest(good, {"agent_id": "a", "payload": {"evil_key": 1}}))
    ok &= check("payload 无合法键 → 400", resp.status == 400)
    # 5. 越界值被丢弃后无合法键 → 400
    resp = await handler.handle_push_device_config(
        FakeRequest(good, {"agent_id": "a", "payload": {"interrupt_threshold": 101}}))
    ok &= check("interrupt_threshold=101 被丢弃 → 400", resp.status == 400)
    # 6. agent_id/device_id 都缺 → 400
    resp = await handler.handle_push_device_config(
        FakeRequest(good, {"payload": {"wake_word_threshold": 40}}))
    ok &= check("无目标 → 400", resp.status == 400)
    # 7. 合法请求（唤醒词阈值）
    resp = await handler.handle_push_device_config(
        FakeRequest(good, {"device_id": "dev-http", "payload": {"wake_word_threshold": 10}}))
    body = json.loads(resp.text)
    ok &= check("唤醒词阈值合法请求 → code=0 且设备收到帧",
                resp.status == 200 and body["code"] == 0
                and conn.frames and conn.frames[0]["payload"]["wake_word_threshold"] == 10,
                resp.text)
    # 8. 混合 payload：合法键保留、非法键丢弃
    resp = await handler.handle_push_device_config(
        FakeRequest(good, {"device_id": "dev-http",
                           "payload": {"interrupt_threshold": 0, "evil": "x"}}))
    body = json.loads(resp.text)
    last = conn.frames[-1]["payload"]
    ok &= check("混合 payload 只下发白名单键",
                resp.status == 200 and last == {"interrupt_threshold": 0}, str(last))
    # 9. 孤儿 display：service 层守卫抛 ValueError → handler 应转 400（防被改成 500/200）
    resp = await handler.handle_push_device_config(
        FakeRequest(good, {"device_id": "dev-http",
                           "payload": {"wake_word": [], "wake_word_display": ["你好"]}}))
    ok &= check("孤儿 display → 400（service ValueError 转 400，不 500/静默成功）",
                resp.status == 400, f"status={resp.status}")
    return ok


async def test_interrupt_threshold():
    """用例 8.5：实时打断阈值（0~100 → VAD 人声确认窗 0~2000ms）"""
    svc = WakeWordService()
    conn = FakeConn()
    svc._connections["dev-int"] = conn
    ok = True
    # 边界 0：最灵敏（立即打断）
    r = await svc.push_interrupt_threshold(device_id="dev-int", threshold=0)
    frame = conn.frames[-1]
    ok &= check("打断阈值 0 下发成功（最灵敏）",
                r["sent"] == 1 and frame["payload"] == {"interrupt_threshold": 0}, str(frame))
    # 缺省语义值 15 ≈ 300ms
    await svc.push_interrupt_threshold(device_id="dev-int", threshold=15)
    ok &= check("打断阈值 15 帧值正确", conn.frames[-1]["payload"]["interrupt_threshold"] == 15)
    # 边界 100：最难打断
    await svc.push_interrupt_threshold(device_id="dev-int", threshold=100)
    ok &= check("打断阈值 100 帧值正确", conn.frames[-1]["payload"]["interrupt_threshold"] == 100)
    # 越界拒绝
    for bad in (-1, 101, 7.5):
        try:
            await svc.push_interrupt_threshold(device_id="dev-int", threshold=bad)
            ok &= check(f"打断阈值越界 {bad} 被拒绝", False, "未抛出异常")
        except ValueError:
            ok &= check(f"打断阈值越界 {bad} 被拒绝", True)
    # 非线性值校验：固件映射 confirm_ms = t*20，0/15/100 对应 0/300/2000ms
    ok &= check("映射关系 0/15/100 → 0/300/2000ms",
                [t * 20 for t in (0, 15, 100)] == [0, 300, 2000])
    return ok


async def test_firmware_contract():
    """用例 9：固件解析契约走查（board.cc / custom_wake_word.cc 逐项静态断言）

    固件源码树只在开发仓里存在。原实现按"离本文件 4 层上级"硬算路径，本地成立
    （.../21_xiaozhi/hardware/...），但测试机部署在 /root/yh/app/yuhe-server/
    多一层 app/，于是变成 FileNotFoundError —— 那是环境缺依赖，不是代码失败，
    却会把整轮测试判成 FAIL。改为向上搜索，找不到就跳过本用例。
    """
    rel = Path("hardware") / "sets" / "yuhe-esp32"
    base = None
    for parent in Path(__file__).resolve().parents:
        if (parent / rel / "main" / "boards" / "common" / "board.cc").exists():
            base = parent / rel
            break
    if base is None:
        print("[SKIP] 用例 9 固件解析契约走查：当前环境无 hardware/sets/yuhe-esp32 源码树")
        return True
    ok = True
    board = (base / "main" / "boards" / "common" / "board.cc").read_text(encoding="utf-8")
    cww = (base / "main" / "audio" / "wake_words" / "custom_wake_word.cc").read_text(encoding="utf-8")
    ok &= check("board.cc 解析 wake_word_threshold 键", '"wake_word_threshold"' in board)
    ok &= check("board.cc 区间放宽为 0~100（0=最灵敏）",
                "t >= 0 && t <= 100" in board)
    ok &= check("board.cc 落 NVS(wake_word_config).threshold",
                'Settings settings("wake_word_config", true)' in board
                and 'SetInt("threshold", t)' in board)
    ok &= check("board.cc 调 SetWakeWordThreshold 热生效",
                "SetWakeWordThreshold(t / 100.0f)" in board)
    ok &= check("custom_wake_word.cc 允许 0 并 clamp 到 0.01",
                "threshold < 0.01f ? 0.01f : threshold" in cww)
    ok &= check("custom_wake_word.cc 启动时从 NVS 恢复阈值（防重启回退）",
                'settings.GetInt("threshold", -1)' in cww and
                "SetThreshold(saved_threshold / 100.0f)" in cww)
    ok &= check("custom_wake_word.cc 启动时从 NVS 恢复时长",
                'settings.GetInt("duration", -1)' in cww)
    # 实时打断阈值契约
    afe_h = (base / "main" / "audio" / "engines" / "afe_audio_engine.h").read_text(encoding="utf-8")
    afe_cc = (base / "main" / "audio" / "engines" / "afe_audio_engine.cc").read_text(encoding="utf-8")
    ok &= check("board.cc 解析 interrupt_threshold 键", '"interrupt_threshold"' in board)
    ok &= check("board.cc 落 NVS(interrupt_config).threshold",
                'Settings settings("interrupt_config", true)' in board
                and 'SetInt("threshold", it)' in board)
    ok &= check("board.cc 调 SetInterruptThreshold 热生效",
                "SetInterruptThreshold(it)" in board)
    ok &= check("afe 引擎 0~100 → 人声确认窗线性映射（*20 → 0~2000ms）",
                "threshold * 20" in afe_cc and "vad_speech_confirm_ms_.store" in afe_cc)
    ok &= check("afe 人声确认窗改为可运行时修改的原子成员",
                "std::atomic<int> vad_speech_confirm_ms_" in afe_h
                and "vad_speech_confirm_ms_.load()" in afe_cc)
    ok &= check("afe Initialize 从 NVS 恢复打断阈值（重启不回退）",
                'settings.GetInt("threshold", -1)' in afe_cc and "Restored interrupt threshold" in afe_cc)
    return ok


async def test_wake_word_display_pairing():
    """用例 10：wake_word / wake_word_display 双数组配对契约（本轮新功能回归保护）

    核心风险是「喊 A 显示 B」：两数组一旦下标错位，设备唤醒成功但上报的
    detect text 是别的词。三条防线：成对构建（push_wake_words）、成对剔除
    （push_device_config）、wakeup_words 参差不污染（_on_sent）。
    """
    ok = True
    # 1. 双键同序等长：display[0] 必须是「你好小禾」，防「喊 A 显示 B」
    svc = WakeWordService()
    conn = FakeConn()
    svc._connections["dev-pair"] = conn
    r = await svc.push_wake_words(agent_id=None, device_id="dev-pair",
                                  wake_words=["ni hao xiao he", "gui gui", "xiao ai tong xue"],
                                  display_words=["你好小禾", "鬼鬼", "小爱同学"])
    payload = conn.frames[0]["payload"] if conn.frames else {}
    wake = payload.get("wake_word", [])
    disp = payload.get("wake_word_display", [])
    ok &= check("双键同序等长（3 词全可转）",
                r["sent"] == 1 and len(wake) == len(disp) == 3
                and wake == ["ni hao xiao he", "gui gui", "xiao ai tong xue"]
                and disp == ["你好小禾", "鬼鬼", "小爱同学"], str(payload))
    ok &= check("display[0] == 你好小禾（防喊 A 显示 B）",
                bool(disp) and disp[0] == "你好小禾", str(disp))

    # 2. 中间项非法（空串）时成对剔除：同下标删，两数组仍等长同序
    svc2 = WakeWordService()
    conn2 = FakeConn()
    svc2._connections["dev-pair2"] = conn2
    await svc2.push_device_config(device_id="dev-pair2", payload={
        "wake_word": ["a", "", "c"], "wake_word_display": ["甲", "乙", "丙"]})
    payload2 = conn2.frames[-1]["payload"] if conn2.frames else {}
    ok &= check("中间空串成对剔除且两数组等长同序",
                payload2.get("wake_word") == ["a", "c"]
                and payload2.get("wake_word_display") == ["甲", "丙"], str(payload2))

    # 3. 参差 display 不污染 wakeup_words（_on_sent any→all 修复的回归保护，最重要）
    svc3 = WakeWordService()
    conn3 = FakeConn()
    conn3.config["wakeup_words"] = ["旧词"]          # 预置旧值，证明参差时不覆盖
    svc3._connections["dev-pair3"] = conn3
    r3 = await svc3.push_wake_words(agent_id=None, device_id="dev-pair3",
                                    wake_words=["ni hao xiao he", "gui gui"],
                                    display_words=["你好小禾", ""])
    ww = conn3.config.get("wakeup_words")
    # sent == 1 是正向对照，必须保留：on_sent 只在发送成功后执行，
    # 若断言只有「值没变」，那么"正确的不动"和"on_sent 压根没跑"都会通过 ⇒ 假绿。
    ok &= check("参差 display 不污染 wakeup_words（保持原值且无拼音渗入）",
                r3.get("sent") == 1
                and ww == ["旧词"] and not any(w.isascii() for w in ww), str(ww))

    # 3b. 正向对照：display 全齐备时必须覆盖。补上 3 只有负向断言时的盲区——
    # 若 on_sent 被整体删掉、或 all() 分支误写成 sync_words=None，3 仍会绿，3b 会红。
    r3b = await svc3.push_wake_words(agent_id=None, device_id="dev-pair3",
                                     wake_words=["ni hao xiao he", "gui gui"],
                                     display_words=["你好小禾", "鬼鬼"])
    ok &= check("全齐备 display 时覆盖 wakeup_words（证明 all() 分支 on_sent 真执行）",
                r3b.get("sent") == 1
                and conn3.config.get("wakeup_words") == ["你好小禾", "鬼鬼"],
                str(conn3.config.get("wakeup_words")))

    # 4. 老链路 display=None：wakeup_words 等于传入的汉字原样（防 all() 改动误伤）
    svc4 = WakeWordService()
    conn4 = FakeConn()
    svc4._connections["dev-pair4"] = conn4
    await svc4.push_wake_words(agent_id=None, device_id="dev-pair4",
                               wake_words=["你好", "早上好"], display_words=None)
    ok &= check("老链路 display=None 时 wakeup_words == 汉字原样",
                conn4.config.get("wakeup_words") == ["你好", "早上好"],
                str(conn4.config.get("wakeup_words")))

    # 5. 孤儿 display 被拒：wake_word 无合法值时 display 不得单独下发
    svc5 = WakeWordService()
    conn5 = FakeConn()
    svc5._connections["dev-pair5"] = conn5
    raised = False
    try:
        await svc5.push_device_config(device_id="dev-pair5", payload={
            "wake_word": [], "wake_word_display": ["你好"]})
    except ValueError:
        raised = True
    ok &= check("孤儿 display 被拒（wake_word 空时抛 ValueError，不下发孤儿键）",
                raised and conn5.frames == [], str(conn5.frames))
    return ok


async def test_wake_word_display_edge_cases():
    """用例 11：display 边界场景（显式空 display / 孤儿 display 守卫）"""
    ok = True
    # 1. 显式空 display（display_words=[]，与"列表含空串"是不同前段路径）：
    #    帧内不应有 wake_word_display 键，wakeup_words 不被覆盖成拼音
    svc = WakeWordService()
    conn = FakeConn()
    conn.config["wakeup_words"] = ["旧词"]
    svc._connections["dev-edge1"] = conn
    await svc.push_wake_words(agent_id=None, device_id="dev-edge1",
                              wake_words=["ni hao"], display_words=[])
    payload = conn.frames[0]["payload"] if conn.frames else {}
    ok &= check("显式空 display 不下发 display 键且 wake_word 保留",
                "wake_word_display" not in payload
                and payload.get("wake_word") == ["ni hao"], str(payload))
    ok &= check("显式空 display 不动 wakeup_words",
                conn.config.get("wakeup_words") == ["旧词"],
                str(conn.config.get("wakeup_words")))

    # 2. 孤儿 display + 其他合法键：剥离 display、保留其他键、继续下发（不整包拒绝）
    svc2 = WakeWordService()
    conn2 = FakeConn()
    svc2._connections["dev-edge2"] = conn2
    r = await svc2.push_device_config(device_id="dev-edge2", payload={
        "wake_word": [], "wake_word_display": ["你好"], "brightness": 50})
    payload2 = conn2.frames[-1]["payload"] if conn2.frames else {}
    ok &= check("孤儿 display 剥离后其他合法键继续下发",
                r["sent"] == 1 and payload2 == {"brightness": 50}, str(payload2))

    # 3. 纯孤儿 display（无其他合法键）：剥离后 clean 为空 → 拒发（ValueError）
    svc3 = WakeWordService()
    conn3 = FakeConn()
    svc3._connections["dev-edge3"] = conn3
    raised = False
    try:
        await svc3.push_device_config(device_id="dev-edge3", payload={
            "wake_word_display": ["你好"]})
    except ValueError:
        raised = True
    ok &= check("纯孤儿 display 拒发（ValueError 且无帧）",
                raised and conn3.frames == [], str(conn3.frames))
    return ok


async def main():
    results = []
    results.append(await test_online_push())
    results.append(await test_boundary_values())
    results.append(await test_out_of_range())
    results.append(await test_offline_queue_and_replay())
    results.append(await test_skip_unbound_and_mqtt())
    results.append(await test_send_failure_retries())
    results.append(await test_wake_words_regression())
    results.append(await test_http_handler())
    results.append(await test_interrupt_threshold())
    results.append(await test_firmware_contract())
    results.append(await test_wake_word_display_pairing())
    results.append(await test_wake_word_display_edge_cases())
    total, passed = len(results), sum(results)
    print("-" * 60)
    print(f"合计 {total} 组用例，通过 {passed} 组" + ("，全部 PASS ✓" if passed == total else "，存在 FAIL ✗"))
    return passed == total


if __name__ == "__main__":
    ok = asyncio.run(main())
    sys.exit(0 if ok else 1)

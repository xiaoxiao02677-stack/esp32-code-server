"""实时打断一键开关（interrupt_enabled）单测。

开关语义：
- conn.interrupt_enabled = False → _maybe_server_interrupt 直接短路，
  确认窗满足也不触发 abort（handleAbortMessage 不被调用）；
- None/True → 原有链路不变（确认窗 + 回声探测照常）；
- 云端 device_config 携带 interrupt_enabled 时连接初始化恢复（connection.py）。
"""

import asyncio
import json

import pytest


class FakeASR:
    def __init__(self):
        self.calls = []

    def speech_to_text_wrapper(self, pcm_data, session_id=None):
        self.calls.append(pcm_data)
        return ""


def _mkconn(confirm_ms=300, enabled=None):
    """最小 ConnectionHandler 替身：只带打断判定所需状态。"""
    from types import SimpleNamespace

    conn = SimpleNamespace()
    conn.asr_audio = []
    conn.asr = FakeASR()
    conn.client_speaking_since_ms = 0.0
    conn.interrupt_voice_since_ms = 0.0
    conn.interrupt_confirm_ms = confirm_ms
    conn.interrupt_enabled = enabled
    return conn


def _make_abort_recorder(monkeypatch):
    calls = []

    async def fake_abort(conn):
        calls.append(conn)

    monkeypatch.setattr(
        "core.handle.receiveAudioHandle.handleAbortMessage", fake_abort
    )
    return calls


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro) if False else asyncio.run(coro)


async def _feed_voice_frames(conn, frames=40):
    """连续喂人声帧（每帧 60ms 语义），驱动确认窗计时。"""
    from core.handle.receiveAudioHandle import _maybe_server_interrupt

    for _ in range(frames):
        await _maybe_server_interrupt(conn)


def test_switch_off_blocks_interrupt(monkeypatch):
    """开关 OFF：确认窗远超阈值也不会 abort（链路整体短路）。"""
    calls = _make_abort_recorder(monkeypatch)
    conn = _mkconn(confirm_ms=300, enabled=False)
    asyncio.run(_feed_voice_frames(conn, frames=60))
    assert calls == [], "OFF 时不应触发任何打断"
    # 计时器也不应被推进（短路发生在计时之前）
    assert conn.interrupt_voice_since_ms == 0


def test_switch_on_still_interrupts(monkeypatch):
    """开关 ON（True）：确认窗满足后照常走打断链路（abort 被调用）。"""
    calls = _make_abort_recorder(monkeypatch)
    conn = _mkconn(confirm_ms=0, enabled=True)
    asyncio.run(_feed_voice_frames(conn, frames=1))
    assert len(calls) == 1, "0 档 + 开关 ON 应立即打断"


def test_switch_none_defaults_on(monkeypatch):
    """开关未设置（None）：默认开启，行为与 ON 一致。"""
    calls = _make_abort_recorder(monkeypatch)
    conn = _mkconn(confirm_ms=0, enabled=None)
    asyncio.run(_feed_voice_frames(conn, frames=1))
    assert len(calls) == 1, "None 默认开启，0 档应立即打断"


def test_switch_off_guard_window_irrelevant(monkeypatch):
    """开关 OFF 优先级最高：即使不在起播保护窗内也不打断（短路在保护窗判定之前）。"""
    calls = _make_abort_recorder(monkeypatch)
    conn = _mkconn(confirm_ms=0, enabled=False)
    conn.client_speaking_since_ms = 0.0  # 无保护窗
    asyncio.run(_feed_voice_frames(conn, frames=5))
    assert calls == []


def test_config_restore_from_device_config():
    """连接初始化：device_config 携带 interrupt_enabled=False 时恢复到 conn。

    connection.py 顶部 import websockets（本机无该依赖），无法 import 整模块，
    改为源码文本断言恢复分支存在且语义正确。
    """
    import re
    from pathlib import Path

    src = Path("core/connection.py").read_text(encoding="utf-8")
    assert 'device_config.get("interrupt_enabled")' in src
    assert re.search(r"self\.interrupt_enabled = _en", src), "恢复分支应写回 conn.interrupt_enabled"


def test_wake_word_service_allows_key():
    """wake_word_service：interrupt_enabled 在下发白名单内。"""
    from core.services.wake_word_service import DEVICE_CONFIG_ALLOWED_KEYS

    assert "interrupt_enabled" in DEVICE_CONFIG_ALLOWED_KEYS


def test_push_config_hot_sync_hook(monkeypatch):
    """push_device_config：payload 含 interrupt_enabled 时自动挂服务端热同步钩子。"""
    from core.services import wake_word_service as wws

    svc = wws.WakeWordService.__new__(wws.WakeWordService)  # 跳过 __init__ 重依赖
    captured = {}

    async def fake_push(agent_id, device_id, clean, log_tag, on_sent=None):
        captured["clean"] = clean
        captured["on_sent"] = on_sent
        return {"ok": 1}

    monkeypatch.setattr(svc, "_push_device_config", fake_push)
    asyncio.run(svc.push_device_config(None, None, {"interrupt_enabled": False}, "实时打断开关"))
    assert captured["clean"] == {"interrupt_enabled": False}
    assert callable(captured["on_sent"]), "含 interrupt_enabled 的 payload 应自动挂 on_sent 钩子"
    # 钩子语义：把 conn.interrupt_enabled 置为 False
    conn = _mkconn(enabled=None)
    captured["on_sent"](conn)
    assert conn.interrupt_enabled is False


def _mk_speaking_conn(enabled):
    """播报中的 realtime 连接替身（startToChat 拦截用）。"""
    conn = _mkconn(enabled=enabled)
    conn.client_is_speaking = True
    conn.client_listen_mode = "realtime"
    conn.need_bind = False
    conn.max_output_size = 0
    conn.current_speaker = None
    conn.logger = __import__("loguru").logger.bind(tag="test")
    conn.executor = __import__("concurrent.futures", fromlist=["ThreadPoolExecutor"]).ThreadPoolExecutor(max_workers=1)
    conn.chat = lambda text: chatted.append(("chat", text))
    return conn


def test_starttochat_off_drops_text_while_speaking(monkeypatch):
    """开关 OFF：播报期间上行文本整体丢弃，不 abort、不进对话。

    2026-10-19 15:07 生产实录：回声「我只是欢乐图」漏网进 startToChat，
    无条件 abort 掐断正在播的故事。开关 OFF 时必须在 abort 之前 return。
    """
    calls = _make_abort_recorder(monkeypatch)
    chatted = []

    async def fake_intent(conn, text):
        chatted.append(text)
        return False

    async def fake_stt(conn, text):
        chatted.append(text)

    monkeypatch.setattr("core.handle.receiveAudioHandle.handle_user_intent", fake_intent)
    monkeypatch.setattr("core.handle.receiveAudioHandle.send_stt_message", fake_stt)

    from core.handle.receiveAudioHandle import startToChat

    conn = _mk_speaking_conn(enabled=False)
    asyncio.run(startToChat(conn, "我只是欢乐图"))
    assert calls == [], "OFF 播报期不得 abort"
    assert chatted == [], "OFF 播报期上行文本不得进对话"


def test_starttochat_on_aborts_and_chats_while_speaking(monkeypatch):
    """开关 ON（默认）：播报期间上行文本照常 abort 并进对话（原行为不变）。"""
    calls = _make_abort_recorder(monkeypatch)
    chatted = []

    async def fake_intent(conn, text):
        chatted.append(text)
        return False

    async def fake_stt(conn, text):
        chatted.append(text)

    monkeypatch.setattr("core.handle.receiveAudioHandle.handle_user_intent", fake_intent)
    monkeypatch.setattr("core.handle.receiveAudioHandle.send_stt_message", fake_stt)

    from core.handle.receiveAudioHandle import startToChat

    conn = _mk_speaking_conn(enabled=True)
    asyncio.run(startToChat(conn, "别讲了换个话题"))
    assert len(calls) == 1, "ON 播报期应照常 abort"
    assert chatted, "ON 播报期上行文本应进对话"


def test_starttochat_off_idle_still_chats(monkeypatch):
    """开关 OFF 只挡播报期：空闲态（非 speaking）上行文本照常进对话。"""
    calls = _make_abort_recorder(monkeypatch)
    chatted = []

    async def fake_intent(conn, text):
        chatted.append(text)
        return False

    async def fake_stt(conn, text):
        chatted.append(text)

    monkeypatch.setattr("core.handle.receiveAudioHandle.handle_user_intent", fake_intent)
    monkeypatch.setattr("core.handle.receiveAudioHandle.send_stt_message", fake_stt)

    from core.handle.receiveAudioHandle import startToChat

    conn = _mk_speaking_conn(enabled=False)
    conn.client_is_speaking = False  # 空闲态
    conn.client_speak_ended_ms = 0  # 从未播报
    asyncio.run(startToChat(conn, "讲个新故事"))
    assert calls == [], "空闲态本就不 abort"
    assert chatted, "OFF 只挡播报期，空闲态对话不受影响"


def test_starttochat_off_tail_window_drops_echo(monkeypatch, monkeypatch_noop=None):
    """开关 OFF：播报刚结束（尾部窗内）的在途回声也丢弃。

    2026-10-19 15:41 实录：tts stop 后 1s 失真回声「之后好好好」漏网，
    client_is_speaking 已 False，播报期守卫拦不到。尾部窗以
    client_speak_ended_ms 起算 TAIL_ECHO_GUARD_MS。
    """
    import time as _time

    calls = _make_abort_recorder(monkeypatch)
    chatted = []

    async def fake_intent(conn, text):
        chatted.append(text)
        return False

    async def fake_stt(conn, text):
        chatted.append(text)

    monkeypatch.setattr("core.handle.receiveAudioHandle.handle_user_intent", fake_intent)
    monkeypatch.setattr("core.handle.receiveAudioHandle.send_stt_message", fake_stt)

    from core.handle.receiveAudioHandle import startToChat, TAIL_ECHO_GUARD_MS

    conn = _mk_speaking_conn(enabled=False)
    conn.client_is_speaking = False  # 播报已结束
    conn.client_speak_ended_ms = _time.time() * 1000 - (TAIL_ECHO_GUARD_MS / 2)  # 窗内
    asyncio.run(startToChat(conn, "之后好好好"))
    assert calls == [] and chatted == [], "尾部窗内在途回声应丢弃"

    # 窗外（结束后超过 TAIL_ECHO_GUARD_MS）：恢复正常对话
    conn2 = _mk_speaking_conn(enabled=False)
    conn2.client_is_speaking = False
    conn2.client_speak_ended_ms = _time.time() * 1000 - (TAIL_ECHO_GUARD_MS + 500)
    asyncio.run(startToChat(conn2, "讲个新故事"))
    assert chatted, "尾部窗外应恢复正常对话"

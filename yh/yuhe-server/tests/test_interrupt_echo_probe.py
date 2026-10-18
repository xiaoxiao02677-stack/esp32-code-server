"""服务端 VAD 打断回声探测的单元测试。

背景（2026-10-18 16:57 生产实录）：SERVER_AEC 板播报期持续推流，设备扬声器
播报声被麦克风拾取回传，Silero VAD 对原始上行 PCM 直判（无 AEC），连续
2000ms 回声过阈 → _maybe_server_interrupt 直接 abort，6 句播报只播到第 2 句。

修复：确认窗满足后不再直接打断，先取最近 3s 上行音频快速 ASR，
echo_guard 判回声——回声→放弃打断继续播；非回声→真人插话照常打断。
"""
import sys
import time
import asyncio
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
_here = str(Path(__file__).resolve().parent)
sys.path = [p for p in sys.path if str(Path(p).resolve()) != _here]
sys.path.insert(0, str(_ROOT))

from core.handle import receiveAudioHandle as rah  # noqa: E402
from core.utils.echo_guard import register_spoken_sentence  # noqa: E402


class FakeLogger:
    def bind(self, **kw):
        return self

    def info(self, msg):
        print("  [log]", msg)

    def warning(self, msg):
        print("  [warn]", msg)


class FakeASR:
    """探测用的假 ASR：可配置返回文本或抛异常，记录调用。"""

    def __init__(self, result=None, exc=None):
        self.result = result
        self.exc = exc
        self.calls = []

    async def speech_to_text_wrapper(self, pcm_data, session_id):
        self.calls.append(pcm_data)
        await asyncio.sleep(0)
        if self.exc:
            raise self.exc
        return (self.result, None)


class FakeConn:
    def __init__(self, asr=None):
        self.logger = FakeLogger()
        self.asr = asr or FakeASR()
        self.asr_audio = []
        self.session_id = "test-session"
        # 打断判定链所需状态
        self.client_aec = True
        self.client_is_speaking = True
        self.client_listen_mode = "auto"
        self.client_speaking_since_ms = 0
        self.interrupt_confirm_ms = 2000
        self.interrupt_voice_since_ms = 0


def _fill_audio(conn, frames, frame_bytes=1920):
    conn.asr_audio = [b"\x01\x00" * (frame_bytes // 2)] * frames


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro) if False else asyncio.run(coro)


def _make_abort_recorder(monkeypatch):
    calls = []

    async def fake_abort(conn):
        calls.append(conn)

    monkeypatch.setattr(rah, "handleAbortMessage", fake_abort)
    return calls


def test_asr_result_to_text():
    """ASR 返回值归一化：fun_local dict / 声纹 JSON / 纯文本 / 空。"""
    f = rah._asr_result_to_text
    assert f({"content": "玲玲的脑子转", "language": "zh"}) == "玲玲的脑子转"
    assert f('{"speaker": "主人", "content": "玲玲的脑子转"}') == "玲玲的脑子转"
    assert f("讲个故事吧") == "讲个故事吧"
    assert f({"content": ""}) == ""
    assert f(None) == ""
    assert f("not json {") == "not json {"
    print("  OK 归一化：dict/JSON/纯文本/空")


def test_probe_echo_gives_up_interrupt(monkeypatch):
    """回声探测核心场景（16:57:23 实录）：探测 ASR 识别出播报回声 → 不打断。"""
    aborts = _make_abort_recorder(monkeypatch)
    conn = FakeConn(asr=FakeASR(result="老巷子口有个卖糖水的阿婆"))
    register_spoken_sentence(conn, "老巷子口有个卖糖水的阿婆，摊子小得只有一条板凳")
    _fill_audio(conn, 50)

    _run(rah._interrupt_with_echo_probe(conn))

    assert not aborts, "回声被误判为真人插话（未放弃打断）"
    assert len(conn.asr.calls) == 1
    print("  OK 回声 → 放弃打断")


def test_probe_human_speech_interrupts(monkeypatch):
    """真人插话（16:57 场景的用户）：探测 ASR 识别出非回声文本 → 打断。"""
    aborts = _make_abort_recorder(monkeypatch)
    conn = FakeConn(asr=FakeASR(result="别讲了，我想听音乐"))
    register_spoken_sentence(conn, "老巷子口有个卖糖水的阿婆，摊子小得只有一条板凳")
    _fill_audio(conn, 50)

    _run(rah._interrupt_with_echo_probe(conn))

    assert len(aborts) == 1, "真人插话未被确认为打断"
    print("  OK 真人插话 → 打断")


def test_probe_empty_text_no_interrupt(monkeypatch):
    """ASR 空结果（静音/噪声）→ 保守放行不打断。"""
    aborts = _make_abort_recorder(monkeypatch)
    conn = FakeConn(asr=FakeASR(result=""))
    register_spoken_sentence(conn, "老巷子口有个卖糖水的阿婆")
    _fill_audio(conn, 50)

    _run(rah._interrupt_with_echo_probe(conn))
    assert not aborts
    print("  OK 空文本 → 放行不打断")


def test_probe_insufficient_audio(monkeypatch):
    """上行音频不足 60ms → 不发起 ASR、放行不打断。"""
    aborts = _make_abort_recorder(monkeypatch)
    conn = FakeConn(asr=FakeASR(result="别讲了"))
    conn.asr_audio = [b"\x00\x00" * 100]  # 200B，不足

    _run(rah._interrupt_with_echo_probe(conn))
    assert not aborts
    assert not conn.asr.calls, "音频不足时不应调用 ASR"
    print("  OK 音频不足 → 放行且不调 ASR")


def test_probe_asr_exception_no_interrupt(monkeypatch):
    """ASR 抛异常 → 保守放行不打断（探测绝不反向制造误打断）。"""
    aborts = _make_abort_recorder(monkeypatch)
    conn = FakeConn(asr=FakeASR(exc=RuntimeError("model busy")))
    _fill_audio(conn, 50)

    _run(rah._interrupt_with_echo_probe(conn))
    assert not aborts
    print("  OK ASR 异常 → 放行不打断")


def test_probe_truncated_dict_result(monkeypatch):
    """fun_local dict 返回形态（生产在用）端到端：content 提取 + 回声判定。"""
    aborts = _make_abort_recorder(monkeypatch)
    conn = FakeConn(
        asr=FakeASR(result={"content": "摊子小得只有一条板凳", "language": "zh"})
    )
    register_spoken_sentence(conn, "老巷子口有个卖糖水的阿婆，摊子小得只有一条板凳")
    _fill_audio(conn, 50)

    _run(rah._interrupt_with_echo_probe(conn))
    assert not aborts, "dict 返回形态的回声未被识别（归一化失效）"
    print("  OK dict 形态回声 → 放弃打断")


def test_maybe_server_interrupt_routes_to_probe(monkeypatch):
    """确认窗满足 → 走探测路径而非直接 abort（回声场景最终不打断）。"""
    aborts = _make_abort_recorder(monkeypatch)
    conn = FakeConn(asr=FakeASR(result="老巷子口有个卖糖水的阿婆"))
    register_spoken_sentence(conn, "老巷子口有个卖糖水的阿婆，摊子小得只有一条板凳")
    _fill_audio(conn, 50)
    # 起播保护窗早已过（client_speaking_since_ms 设为 10s 前）
    conn.client_speaking_since_ms = time.time() * 1000 - 10000
    # 连续人声从 3s 前开始 → 2000ms 确认窗早已满足
    conn.interrupt_voice_since_ms = time.time() * 1000 - 3000

    _run(rah._maybe_server_interrupt(conn))

    assert len(conn.asr.calls) == 1, "确认窗满足后未进入回声探测"
    assert not aborts, "回声场景仍被直接打断"
    assert conn.interrupt_voice_since_ms == 0, "计窗未复位"
    print("  OK 确认窗满足 → 探测 → 回声放弃打断")


def test_maybe_server_interrupt_confirm_window(monkeypatch):
    """确认窗未满足 → 既不探测也不打断；首帧只记时。"""
    aborts = _make_abort_recorder(monkeypatch)
    conn = FakeConn()
    _fill_audio(conn, 50)
    conn.client_speaking_since_ms = time.time() * 1000 - 10000

    # 首次：只记时
    _run(rah._maybe_server_interrupt(conn))
    assert conn.interrupt_voice_since_ms > 0
    assert not conn.asr.calls and not aborts

    # 300ms 未到 2000ms 窗：不打断
    conn.interrupt_voice_since_ms = time.time() * 1000 - 300
    _run(rah._maybe_server_interrupt(conn))
    assert not aborts and not conn.asr.calls
    print("  OK 确认窗内不打断")


def test_maybe_server_interrupt_guard_window(monkeypatch):
    """起播保护窗内（TTS 刚开始）不打断。"""
    aborts = _make_abort_recorder(monkeypatch)
    conn = FakeConn()
    _fill_audio(conn, 50)
    conn.client_speaking_since_ms = time.time() * 1000 - 100  # 100ms < 800ms 保护窗
    conn.interrupt_voice_since_ms = time.time() * 1000 - 3000

    _run(rah._maybe_server_interrupt(conn))
    assert not aborts and not conn.asr.calls
    print("  OK 起播保护窗内不打断")


def test_maybe_server_interrupt_zero_threshold_bypass(monkeypatch):
    """0 档（立即打断）跳过探测直接 abort——保持"立即"语义。"""
    aborts = _make_abort_recorder(monkeypatch)
    conn = FakeConn()
    _fill_audio(conn, 50)
    conn.interrupt_confirm_ms = 0
    conn.client_speaking_since_ms = time.time() * 1000 - 10000

    _run(rah._maybe_server_interrupt(conn))
    assert len(aborts) == 1, "0 档未立即打断"
    assert not conn.asr.calls, "0 档不应走探测"
    print("  OK 0 档 → 立即打断（不探测）")


def test_probe_window_frames_only(monkeypatch):
    """探测只取最近 50 帧（3s），不把整个 asr_audio 都识别一遍。"""
    aborts = _make_abort_recorder(monkeypatch)
    conn = FakeConn(asr=FakeASR(result="别讲了"))
    _fill_audio(conn, 100)  # 6s 音频

    _run(rah._interrupt_with_echo_probe(conn))
    pcm = conn.asr.calls[0]  # speech_to_text_wrapper(pcm_data=[bytes], ...)
    assert len(pcm) == 1
    assert len(pcm[0]) == 50 * 1920, f"探测窗长度错误: {len(pcm[0])}B"
    print("  OK 探测窗 = 最近 3s（50 帧 × 1920B）")


if __name__ == "__main__":
    import pytest

    pytest.main([__file__, "-v"])

"""chat 兜底降级验证：所有选中话题源失败时不再返回空（推送判 failed 的根因），
而是降级到 chat 源返回开场白。

复现生产失败路径：push_1792306453669（topic_sources=["memory"]，
agent 无记忆配置 → 单源失败 → 空 text → push_scheduler 判 failed）。
"""
import asyncio
import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch

_ROOT = Path(__file__).resolve().parent.parent
_here = str(Path(__file__).resolve().parent)
sys.path = [p for p in sys.path if str(Path(p).resolve()) != _here]
sys.path.insert(0, str(_ROOT))

from core.services.topic_generator import TopicGenerator  # noqa: E402


def make_tg():
    conn = type("C", (), {"client_ip": "1.2.3.4", "loop": None})()
    return TopicGenerator(config={}, conn=conn)


async def test_memory_fail_falls_back_to_chat():
    """生产实测路径：单选 memory、智能体无记忆配置 → 必须降级 chat 而非空结果。"""
    tg = make_tg()
    # memory 源必失败（模拟 _fetch_memory 抛"无可用记忆配置"）
    with patch.object(
        tg, "_fetch_memory", AsyncMock(side_effect=RuntimeError("agent 无可用记忆配置"))
    ), patch.object(
        tg, "_resolve_memory_config", AsyncMock(return_value=(None, None))
    ):
        result = await tg.generate(
            device_id="44:bd:8d:7b:3a:e4",
            topic_sources=["memory"],
        )
    assert result["text"], "降级 chat 后 text 不应为空"
    assert result["generation_meta"]["source"] == "chat"
    assert result["generation_meta"]["fallback_used"] is True
    print(f"  OK memory 失败 → chat 兜底: {result['text'][:30]!r} "
          f"meta={result['generation_meta']}")


async def test_all_selected_fail_falls_back():
    """memory + weather 都失败 → chat 兜底。"""
    tg = make_tg()
    with patch.object(
        tg, "_fetch_memory", AsyncMock(side_effect=RuntimeError("无记忆"))
    ), patch.object(
        tg, "_fetch_weather", AsyncMock(side_effect=RuntimeError("天气失败"))
    ):
        result = await tg.generate(
            device_id="44:bd:8d:7b:3a:e4",
            topic_sources=["memory", "weather"],
        )
    assert result["text"] and result["generation_meta"]["source"] == "chat"
    print(f"  OK 双源失败 → chat 兜底: {result['text'][:30]!r}")


async def test_normal_source_still_first():
    """正常源不受影响：weather 成功时优先用 weather，不走兜底。"""
    tg = make_tg()
    with patch.object(
        tg, "_fetch_weather", AsyncMock(return_value="广州 晴 25 度")
    ):
        result = await tg.generate(
            device_id="44:bd:8d:7b:3a:e4",
            topic_sources=["weather"],
        )
    assert result["text"] == "广州 晴 25 度"
    assert result["generation_meta"]["source"] == "weather"
    print(f"  OK 正常源优先: {result['text']!r}")


async def test_tts_fail_keeps_text():
    """TTS 失败时 text 保留（推送降级为仅字幕，不判 failed 的是这条路径之外的
    audio_url 空场景——此处验证 generate 本身的行为）。"""
    tg = make_tg()
    with patch.object(
        tg, "_fetch_chat", AsyncMock(return_value="你好呀")
    ), patch.object(
        tg, "_synthesize_tts", AsyncMock(side_effect=RuntimeError("TTS 挂了"))
    ):
        result = await tg.generate(
            device_id="44:bd:8d:7b:3a:e4",
            topic_sources=["chat"],
        )
    assert result["text"] == "你好呀" and result["audio_url"] == ""
    print("  OK TTS 失败保留文案")


async def main():
    for name, fn in [
        ("memory 失败→chat 兜底", test_memory_fail_falls_back_to_chat),
        ("双源失败→chat 兜底", test_all_selected_fail_falls_back),
        ("正常源优先", test_normal_source_still_first),
        ("TTS 失败保留文案", test_tts_fail_keeps_text),
    ]:
        print(f"== {name}")
        await fn()
    print("\nALL TESTS PASSED")


if __name__ == "__main__":
    asyncio.run(main())

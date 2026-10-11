"""TTS fallback 降级链路单测：主TTS必失败 -> EdgeTTS 备用合成提示音。"""
import asyncio
import sys
from types import SimpleNamespace

sys.path.insert(0, ".")

from core.providers.tts.base import TTSProviderBase, FALLBACK_TTS_TEXT
from core.providers.tts.edge import TTSProvider as EdgeTTS
from core.providers.tts.dto.dto import SentenceType
from core.utils import opus_encoder_utils


class BrokenTTS(TTSProviderBase):
    async def text_to_speak(self, text, output_file):
        raise Exception("模拟主TTS失败: http 403 forbidden")


def main():
    # 主TTS：必失败；备用：EdgeTTS
    main_tts = BrokenTTS({"output_dir": "tmp/"}, True)
    fallback = EdgeTTS({"voice": "zh-CN-XiaoxiaoNeural", "output_dir": "tmp/"}, True)
    main_tts.fallback_provider = fallback
    main_tts.conn = SimpleNamespace(sample_rate=16000)
    main_tts.opus_encoder = opus_encoder_utils.OpusEncoderUtils(
        sample_rate=16000, channels=1, frame_size_ms=60
    )

    # --- 测试1: to_tts（delete_audio=True 路径）---
    audio_datas = main_tts.to_tts("你好，这是一段测试文本")
    assert audio_datas, "to_tts fallback 未返回音频数据"
    print(f"[PASS] to_tts fallback: {len(audio_datas)} 帧opus, "
          f"首帧 {len(audio_datas[0])} 字节")

    # --- 测试2: to_tts_stream（生产主路径）---
    opus_frames = []
    main_tts.to_tts_stream("你好，这是流式测试", opus_handler=lambda d: opus_frames.append(d))
    assert opus_frames, "to_tts_stream fallback 未产生opus帧"
    # 字幕保底 FIRST 应已入队
    first_msg = main_tts.tts_audio_queue.get_nowait()
    assert first_msg[0] == SentenceType.FIRST, f"队列首条不是FIRST: {first_msg[0]}"
    print(f"[PASS] to_tts_stream fallback: {len(opus_frames)} 帧opus, "
          f"字幕保底FIRST入队: {first_msg[2]}")

    # --- 测试3: 无备用时维持现状（不抛异常）---
    main_tts2 = BrokenTTS({"output_dir": "tmp/"}, True)
    main_tts2.fallback_provider = None
    main_tts2.conn = SimpleNamespace(sample_rate=16000)
    main_tts2.opus_encoder = main_tts.opus_encoder
    result = main_tts2.to_tts("再测一次")
    assert result is None, "无备用时应返回None"
    print("[PASS] 无fallback时维持原状: 返回None")

    # --- 测试4: 提示文案是固定短文案 ---
    assert FALLBACK_TTS_TEXT == "抱歉，语音服务暂时出了点问题，请稍后再试。"
    print(f"[PASS] 固定提示文案: {FALLBACK_TTS_TEXT}")

    print("ALL_FALLBACK_TESTS_PASSED")


if __name__ == "__main__":
    main()

"""千问 ASR provider 单元测试（不触网：mock requests.post）"""
import sys
from pathlib import Path
from unittest import mock

PROJECT_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(PROJECT_ROOT))

from core.providers.asr.qwen3_asr_flash import ASRProvider, ASR_URL


class _Artifacts:
    def __init__(self, temp_path, file_path):
        self.temp_path = temp_path
        self.file_path = file_path


def _make_provider():
    cfg = {
        "api_key": "sk-test",
        "model_name": "qwen-audio-3.1-asr-flash",
        "format": "wav",
        "sample_rate": 16000,
        "output_dir": "tmp/",
    }
    return ASRProvider(cfg, delete_audio_file=False)


def _fake_resp(status=200, payload=None):
    resp = mock.Mock()
    resp.status_code = status
    resp.json.return_value = payload or {}
    resp.text = str(payload or "")
    return resp


def test_config_defaults():
    p = _make_provider()
    assert p.model_name == "qwen-audio-3.1-asr-flash"
    assert p.sample_rate == 16000
    assert p.api_key == "sk-test"


def test_missing_api_key_raises():
    import pytest
    with pytest.raises(ValueError):
        ASRProvider({"api_key": ""}, delete_audio_file=False)


def test_payload_structure(tmp_path):
    wav = tmp_path / "a.wav"
    wav.write_bytes(b"RIFF-fake")
    p = _make_provider()
    art = _Artifacts(str(wav), None)
    with mock.patch("core.providers.asr.qwen3_asr_flash.requests.post") as mp:
        mp.return_value = _fake_resp(200, {"text": "你好小智", "sentence": {"text": "你好小智"}})
        import asyncio
        text, _ = asyncio.run(p.speech_to_text([b"x"], "s1", art))
    assert text == "你好小智"
    # 断言请求形态：URL / 头 / input.messages 嵌套 / base64 内联
    args, kwargs = mp.call_args
    assert args[0] == ASR_URL
    assert kwargs["headers"]["Authorization"] == "Bearer sk-test"
    assert kwargs["headers"]["X-DashScope-SSE"] == "disable"
    payload = kwargs["json"]
    assert payload["model"] == "qwen-audio-3.1-asr-flash"
    content = payload["input"]["messages"][0]["content"][0]
    assert content["type"] == "input_audio"
    assert content["input_audio"]["data"].startswith("data:application/octet-stream;base64,")
    assert payload["parameters"]["format"] == "wav"
    assert payload["parameters"]["sample_rate"] == "16000"


def test_text_fallback_to_sentence(tmp_path):
    wav = tmp_path / "a.wav"
    wav.write_bytes(b"RIFF")
    p = _make_provider()
    art = _Artifacts(str(wav), None)
    with mock.patch("core.providers.asr.qwen3_asr_flash.requests.post") as mp:
        mp.return_value = _fake_resp(200, {"sentence": {"text": "备用文本"}})
        import asyncio
        text, _ = asyncio.run(p.speech_to_text([b"x"], "s1", art))
    assert text == "备用文本"


def test_http_error_returns_empty(tmp_path):
    wav = tmp_path / "a.wav"
    wav.write_bytes(b"RIFF")
    p = _make_provider()
    art = _Artifacts(str(wav), None)
    with mock.patch("core.providers.asr.qwen3_asr_flash.requests.post") as mp:
        mp.return_value = _fake_resp(401, {"code": "InvalidApiKey", "message": "bad key"})
        import asyncio
        text, fp = asyncio.run(p.speech_to_text([b"x"], "s1", art))
    assert text == ""


def test_biz_error_returns_empty(tmp_path):
    wav = tmp_path / "a.wav"
    wav.write_bytes(b"RIFF")
    p = _make_provider()
    art = _Artifacts(str(wav), None)
    with mock.patch("core.providers.asr.qwen3_asr_flash.requests.post") as mp:
        mp.return_value = _fake_resp(200, {"code": "InvalidParameter", "message": "xx", "request_id": "r1"})
        import asyncio
        text, _ = asyncio.run(p.speech_to_text([b"x"], "s1", art))
    assert text == ""

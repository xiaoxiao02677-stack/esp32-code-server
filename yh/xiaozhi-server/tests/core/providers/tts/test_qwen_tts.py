"""千问 TTS provider 契约测试（不触网）。

mock requests 验证：
- 端点路由：qwen-audio-* 走 SpeechSynthesizer（端点A），qwen3-tts-* 走
  multimodal-generation（端点B）
- payload 结构：端点B 含 parameters 包裹、instructions 透传
- OSS URL 下载写盘 / 返回 bytes
- HTTP/业务错误抛异常并带 request_id
- 默认值
"""
import asyncio
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from core.providers.tts.qwen_tts import QWEN_TTS_VOICES, TTSProvider

ENDPOINT_A = TTSProvider.ENDPOINT_SPEECH_SYNTHESIZER
ENDPOINT_B = TTSProvider.ENDPOINT_MULTIMODAL_GENERATION

_DEFAULT_JSON = {
    "output": {
        "audio": {"url": "http://oss.example.com/audio.wav", "data": ""},
        "finish_reason": "stop",
    },
    "usage": {"characters": 3},
}


def _make_provider(**cfg):
    """用最小配置构造 provider（不进 TTS 调度线程）。"""
    config = {"api_key": "sk-test", "output_dir": "tmp/test"}
    config.update(cfg)
    return TTSProvider(config, delete_audio_file=True)


def _run(coro):
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# 端点路由
# ---------------------------------------------------------------------------
def test_endpoint_a_used_for_qwen_audio_models():
    provider = _make_provider(model="qwen-audio-3.1-tts-flash")
    post = Mock(status_code=200)
    post.json.return_value = _DEFAULT_JSON
    post.content = b"fake"
    get = Mock(status_code=200, content=b"WAVDATA")
    with patch("core.providers.tts.qwen_tts.requests.post", return_value=post) as p, \
         patch("core.providers.tts.qwen_tts.requests.get", return_value=get):
        _run(provider.text_to_speak("你好", None))
    assert p.call_args.args[0] == ENDPOINT_A


def test_endpoint_b_used_for_qwen3_tts_models():
    provider = _make_provider(model="qwen3-tts-flash")
    post = Mock(status_code=200)
    post.json.return_value = _DEFAULT_JSON
    post.content = b"fake"
    get = Mock(status_code=200, content=b"WAVDATA")
    with patch("core.providers.tts.qwen_tts.requests.post", return_value=post) as p, \
         patch("core.providers.tts.qwen_tts.requests.get", return_value=get):
        _run(provider.text_to_speak("你好", None))
    assert p.call_args.args[0] == ENDPOINT_B


# ---------------------------------------------------------------------------
# payload 结构
# ---------------------------------------------------------------------------
def test_endpoint_b_payload_wraps_parameters_and_passes_instructions():
    provider = _make_provider(
        model="qwen3-tts-instruct-flash",
        voice="Cherry",
        sample_rate=24000,
        format="wav",
        instructions="用温柔的语气朗读",
    )
    post = Mock(status_code=200)
    post.json.return_value = _DEFAULT_JSON
    post.content = b"fake"
    get = Mock(status_code=200, content=b"WAVDATA")
    with patch("core.providers.tts.qwen_tts.requests.post", return_value=post) as p, \
         patch("core.providers.tts.qwen_tts.requests.get", return_value=get):
        _run(provider.text_to_speak("你好", None))
    payload = p.call_args.kwargs["json"]
    assert payload["model"] == "qwen3-tts-instruct-flash"
    assert payload["input"]["text"] == "你好"
    assert payload["input"]["voice"] == "Cherry"
    assert payload["input"]["instructions"] == "用温柔的语气朗读"
    assert payload["parameters"] == {"format": "wav", "sample_rate": 24000}


def test_endpoint_a_payload_has_no_parameters_wrapper():
    provider = _make_provider(
        model="qwen-audio-3.0-tts-plus", sample_rate=16000,
        instructions="端点A不支持instructions",
    )
    post = Mock(status_code=200)
    post.json.return_value = _DEFAULT_JSON
    post.content = b"fake"
    get = Mock(status_code=200, content=b"WAVDATA")
    with patch("core.providers.tts.qwen_tts.requests.post", return_value=post) as p, \
         patch("core.providers.tts.qwen_tts.requests.get", return_value=get):
        _run(provider.text_to_speak("你好", None))
    payload = p.call_args.kwargs["json"]
    assert payload["input"]["format"] == "wav"
    assert payload["input"]["sample_rate"] == 16000
    assert "parameters" not in payload
    # instructions 仅端点B模型有效，端点A不上送
    assert "instructions" not in payload["input"]


# ---------------------------------------------------------------------------
# OSS URL 下载写盘 / 返回 bytes
# ---------------------------------------------------------------------------
def test_downloads_oss_audio_and_writes_file(tmp_path):
    provider = _make_provider(model="qwen3-tts-flash")
    out_file = tmp_path / "out.wav"
    post = Mock(status_code=200)
    post.json.return_value = _DEFAULT_JSON
    post.content = b"fake"
    get = Mock(status_code=200, content=b"RIFFxxxxWAVEfmt ")
    with patch("core.providers.tts.qwen_tts.requests.post", return_value=post), \
         patch("core.providers.tts.qwen_tts.requests.get", return_value=get) as g:
        _run(provider.text_to_speak("你好", str(out_file)))
    assert g.call_args.args[0] == "http://oss.example.com/audio.wav"
    assert out_file.read_bytes() == b"RIFFxxxxWAVEfmt "


def test_returns_bytes_when_no_output_file():
    provider = _make_provider(model="qwen3-tts-flash")
    post = Mock(status_code=200)
    post.json.return_value = _DEFAULT_JSON
    post.content = b"fake"
    get = Mock(status_code=200, content=b"RIFFxxxxWAVEfmt ")
    with patch("core.providers.tts.qwen_tts.requests.post", return_value=post), \
         patch("core.providers.tts.qwen_tts.requests.get", return_value=get):
        result = _run(provider.text_to_speak("你好", None))
    assert result == b"RIFFxxxxWAVEfmt "


def test_audio_download_retries_once():
    provider = _make_provider(model="qwen3-tts-flash")
    post = Mock(status_code=200)
    post.json.return_value = _DEFAULT_JSON
    post.content = b"fake"
    get = Mock(side_effect=[Exception("boom"), Mock(status_code=200, content=b"OKDATA")])
    with patch("core.providers.tts.qwen_tts.requests.post", return_value=post), \
         patch("core.providers.tts.qwen_tts.requests.get", side_effect=get.side_effect) as g:
        result = _run(provider.text_to_speak("你好", None))
    assert result == b"OKDATA"
    assert g.call_count == 2


# ---------------------------------------------------------------------------
# 错误处理：抛异常并带 request_id
# ---------------------------------------------------------------------------
def test_http_error_raises_with_request_id():
    provider = _make_provider(model="qwen3-tts-flash")
    resp = Mock(status_code=401)
    resp.json.return_value = {"code": "InvalidApiKey", "request_id": "req-http-1"}
    resp.text = '{"code": "InvalidApiKey"}'
    resp.headers = {}
    with patch("core.providers.tts.qwen_tts.requests.post", return_value=resp):
        with pytest.raises(Exception) as exc_info:
            _run(provider.text_to_speak("你好", None))
    assert "401" in str(exc_info.value)
    assert "req-http-1" in str(exc_info.value)


def test_business_error_code_raises_with_request_id():
    provider = _make_provider(model="qwen3-tts-flash", voice="不存在的音色")
    resp = Mock(status_code=200)
    resp.json.return_value = {
        "code": "InvalidParameter",
        "message": "voice not match model",
        "request_id": "req-biz-2",
    }
    resp.text = ""
    with patch("core.providers.tts.qwen_tts.requests.post", return_value=resp):
        with pytest.raises(Exception) as exc_info:
            _run(provider.text_to_speak("你好", None))
    msg = str(exc_info.value)
    assert "InvalidParameter" in msg
    assert "req-biz-2" in msg


# ---------------------------------------------------------------------------
# 默认值
# ---------------------------------------------------------------------------
def test_defaults():
    provider = _make_provider()
    assert provider.model == "qwen3-tts-flash"
    assert provider.voice == "Cherry"
    assert provider.sample_rate == 24000
    assert provider.audio_file_type == "wav"
    assert provider.instructions is None
    assert provider.output_file == "tmp/test"


def test_voices_reference_table():
    assert len(QWEN_TTS_VOICES["qwen3-tts-flash"]) == 48
    assert len(QWEN_TTS_VOICES["qwen3-tts-instruct-flash"]) == 24
    assert QWEN_TTS_VOICES["qwen3-tts-instruct-flash"] == (
        QWEN_TTS_VOICES["qwen3-tts-flash"][:24]
    )
    assert QWEN_TTS_VOICES["qwen-tts"] == ["Cherry", "Serena", "Ethan", "Chelsie"]
    assert QWEN_TTS_VOICES["qwen-tts-latest"] == [
        "Cherry", "Serena", "Ethan", "Chelsie", "Jada", "Dylan", "Sunny",
    ]
    assert "Cherry" in QWEN_TTS_VOICES["qwen3-tts-flash"]

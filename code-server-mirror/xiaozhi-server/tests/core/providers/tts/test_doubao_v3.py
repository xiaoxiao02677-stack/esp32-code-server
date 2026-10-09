"""豆包 v3 TTS provider 契约测试（不触网）。

mock requests 验证：
- 鉴权头：旧版双头（X-Api-App-Id + X-Api-Access-Key）与新版单头（X-Api-Key）
- payload 结构：req_params 包裹 speaker/audio_params（format/sample_rate/speech_rate/loudness_rate）
- chunked JSON 流解析：多个 {"code","message","data"} 分片逐片 base64 解码拼接
- 结束分片（data=null, code=20000000）与错误分片处理
- base64 分片非 4 对齐（无填充）解码
- 写盘 / 返回 bytes / HTTP 错误
- 默认值
"""
import asyncio
import base64
import json
from unittest.mock import Mock, patch

import pytest

from core.providers.tts.doubao_v3 import TTSProvider

ENDPOINT = "https://openspeech.bytedance.com/api/v3/tts/unidirectional"


def _make_provider(**cfg):
    config = {
        "appid": "1234567890",
        "access_token": "test-token",
        "output_dir": "tmp/test",
    }
    config.update(cfg)
    return TTSProvider(config, delete_audio_file=True)


def _run(coro):
    return asyncio.run(coro)


def _chunked_response(chunks, status_code=200):
    """构造 chunked JSON 文本响应。chunks: [(code, message, data_or_None)]

    provider 用 resp.iter_lines(decode_unicode=True) 逐行读流，
    所以这里必须给 Mock 配上 iter_lines，否则整个测试套件会以
    "'Mock' object is not iterable" 全军覆没（历史遗留缺陷）。
    """
    body = "\n".join(
        json.dumps({"code": c, "message": m, "data": d}) for c, m, d in chunks
    )
    resp = Mock(status_code=status_code)
    resp.text = body
    resp.iter_lines = lambda **kwargs: iter(body.splitlines())
    return resp


def _mock_response(text, status_code=200):
    """任意响应体的 Mock（用于畸形分片等异常场景）。"""
    resp = Mock(status_code=status_code)
    resp.text = text
    resp.iter_lines = lambda **kwargs: iter(text.splitlines())
    return resp


# ---------------------------------------------------------------------------
# 鉴权头
# ---------------------------------------------------------------------------
def test_old_style_dual_headers():
    provider = _make_provider()
    post = _chunked_response([(0, "", base64.b64encode(b"AB").decode()),
                              (20000000, "OK", None)])
    with patch("core.providers.tts.doubao_v3.requests.post", return_value=post) as p:
        _run(provider.text_to_speak("你好", None))
    headers = p.call_args.kwargs["headers"]
    assert headers["X-Api-App-Id"] == "1234567890"
    assert headers["X-Api-Access-Key"] == "test-token"
    assert headers["X-Api-Resource-Id"] == "seed-tts-2.0"
    assert "X-Api-Key" not in headers
    assert "X-Api-Request-Id" in headers


def test_new_style_single_api_key_header():
    provider = _make_provider(api_key="my-api-key")
    post = _chunked_response([(0, "", base64.b64encode(b"AB").decode()),
                              (20000000, "OK", None)])
    with patch("core.providers.tts.doubao_v3.requests.post", return_value=post) as p:
        _run(provider.text_to_speak("你好", None))
    headers = p.call_args.kwargs["headers"]
    assert headers["X-Api-Key"] == "my-api-key"
    assert "X-Api-App-Id" not in headers
    assert "X-Api-Access-Key" not in headers


# ---------------------------------------------------------------------------
# payload 结构
# ---------------------------------------------------------------------------
def test_payload_structure():
    provider = _make_provider(
        speaker="zh_female_xiaohe_uranus_bigtts",
        format="wav",
        sample_rate=24000,
        speech_rate=10,
        loudness_rate=-5,
    )
    post = _chunked_response([(0, "", base64.b64encode(b"AB").decode()),
                              (20000000, "OK", None)])
    with patch("core.providers.tts.doubao_v3.requests.post", return_value=post) as p:
        _run(provider.text_to_speak("你好", None))
    payload = p.call_args.kwargs["json"]
    assert p.call_args.args[0] == ENDPOINT
    assert payload["req_params"]["text"] == "你好"
    assert payload["req_params"]["speaker"] == "zh_female_xiaohe_uranus_bigtts"
    assert payload["req_params"]["audio_params"] == {
        "format": "wav",
        "sample_rate": 24000,
        "speech_rate": 10,
        "loudness_rate": -5,
    }
    assert "uid" in payload["user"]


def test_private_voice_overrides_speaker():
    provider = _make_provider(
        speaker="zh_female_xiaohe_uranus_bigtts",
        private_voice="zh_male_beijingxiaoye_uranus_bigtts",
    )
    post = _chunked_response([(0, "", base64.b64encode(b"AB").decode()),
                              (20000000, "OK", None)])
    with patch("core.providers.tts.doubao_v3.requests.post", return_value=post) as p:
        _run(provider.text_to_speak("你好", None))
    assert p.call_args.kwargs["json"]["req_params"]["speaker"] == \
        "zh_male_beijingxiaoye_uranus_bigtts"


def test_voice_instruction_passed_through():
    """语气指令必须走官方通道：req_params.additions（JSON 字符串）.context_texts[0]。

    注意：火山 API 不存在 req_params.voice_instruction 字段，早期实现写该字段
    会被服务端静默忽略（请求照常 200），表现为「指令不起作用」。
    """
    provider = _make_provider(
        voice_instruction="用标准大陆普通话说话，不要台湾腔",
    )
    post = _chunked_response([(0, "", base64.b64encode(b"AB").decode()),
                              (20000000, "OK", None)])
    with patch("core.providers.tts.doubao_v3.requests.post", return_value=post) as p:
        _run(provider.text_to_speak("你好", None))
    req = p.call_args.kwargs["json"]["req_params"]
    # 官方：additions 是 JSON 序列化后的字符串，不是对象
    assert isinstance(req["additions"], str)
    additions = json.loads(req["additions"])
    # 官方：context_texts 是数组，且只有第一个值生效
    assert additions["context_texts"] == ["用标准大陆普通话说话，不要台湾腔"]
    # 非官方字段，绝不能再出现
    assert "voice_instruction" not in req


def test_no_additions_field_when_unset():
    provider = _make_provider()
    post = _chunked_response([(0, "", base64.b64encode(b"AB").decode()),
                              (20000000, "OK", None)])
    with patch("core.providers.tts.doubao_v3.requests.post", return_value=post) as p:
        _run(provider.text_to_speak("你好", None))
    req = p.call_args.kwargs["json"]["req_params"]
    assert "additions" not in req
    assert "voice_instruction" not in req


# ---------------------------------------------------------------------------
# 动态语气指令（音色「动态更新」开关）
# ---------------------------------------------------------------------------
def test_dynamic_instruction_overrides_fixed():
    """connection 每轮注入的动态指令应覆盖固定 voice_instruction。"""
    provider = _make_provider(voice_instruction="固定指令：温柔女声")
    provider.set_dynamic_instruction("用轻快俏皮的语气说")
    post = _chunked_response([(0, "", base64.b64encode(b"AB").decode()),
                              (20000000, "OK", None)])
    with patch("core.providers.tts.doubao_v3.requests.post", return_value=post) as p:
        _run(provider.text_to_speak("你好", None))
    additions = json.loads(p.call_args.kwargs["json"]["req_params"]["additions"])
    assert additions["context_texts"] == ["用轻快俏皮的语气说"]


def test_dynamic_instruction_none_falls_back_to_fixed():
    """动态指令置空（未开启或生成失败）时回落固定指令。"""
    provider = _make_provider(voice_instruction="固定指令：温柔女声")
    provider.set_dynamic_instruction("上一轮的动态指令")
    provider.set_dynamic_instruction(None)   # 本轮回落
    post = _chunked_response([(0, "", base64.b64encode(b"AB").decode()),
                              (20000000, "OK", None)])
    with patch("core.providers.tts.doubao_v3.requests.post", return_value=post) as p:
        _run(provider.text_to_speak("你好", None))
    additions = json.loads(p.call_args.kwargs["json"]["req_params"]["additions"])
    assert additions["context_texts"] == ["固定指令：温柔女声"]


def test_clone_resource_has_no_model_by_default():
    """复刻音色默认不发送 model —— 严格对齐火山官方 声音复刻 V3 脚本。

    官方脚本（seed-icl-2.0 + S_ 复刻音色）的 req_params 里没有 model 字段，
    仅靠 header 的 X-Api-Resource-Id=seed-icl-2.0 区分资源，实测可正常出音频。
    确需时可在 TTS 模型配置里显式写 model=seed-tts-2.0-expressive 恢复发送。
    """
    provider = _make_provider(resource_id="seed-icl-2.0",
                              voice_instruction="用低沉沙哑的语气")
    post = _chunked_response([(0, "", base64.b64encode(b"AB").decode()),
                              (20000000, "OK", None)])
    with patch("core.providers.tts.doubao_v3.requests.post", return_value=post) as p:
        _run(provider.text_to_speak("你好", None))
    req = p.call_args.kwargs["json"]["req_params"]
    assert "model" not in req


def test_model_sent_only_when_explicitly_configured():
    """只有配置里显式给了 model 才发送（保留回退能力）。"""
    provider = _make_provider(resource_id="seed-icl-2.0",
                              model="seed-tts-2.0-expressive",
                              voice_instruction="用低沉沙哑的语气")
    post = _chunked_response([(0, "", base64.b64encode(b"AB").decode()),
                              (20000000, "OK", None)])
    with patch("core.providers.tts.doubao_v3.requests.post", return_value=post) as p:
        _run(provider.text_to_speak("你好", None))
    assert p.call_args.kwargs["json"]["req_params"]["model"] == \
        "seed-tts-2.0-expressive"


def test_preset_voice_has_no_model_field():
    """官方预置音色不应被塞入 model 字段。"""
    provider = _make_provider(resource_id="seed-tts-2.0",
                              voice_instruction="用温柔的语气")
    post = _chunked_response([(0, "", base64.b64encode(b"AB").decode()),
                              (20000000, "OK", None)])
    with patch("core.providers.tts.doubao_v3.requests.post", return_value=post) as p:
        _run(provider.text_to_speak("你好", None))
    assert "model" not in p.call_args.kwargs["json"]["req_params"]


def test_no_explicit_language_by_default():
    """对齐官方脚本：EXPLICIT_LANGUAGE 默认留空，中文场景不发送。"""
    provider = _make_provider(voice_instruction="用温柔的语气")
    post = _chunked_response([(0, "", base64.b64encode(b"AB").decode()),
                              (20000000, "OK", None)])
    with patch("core.providers.tts.doubao_v3.requests.post", return_value=post) as p:
        _run(provider.text_to_speak("你好", None))
    additions = json.loads(p.call_args.kwargs["json"]["req_params"]["additions"])
    assert "explicit_language" not in additions
    assert additions["context_texts"] == ["用温柔的语气"]


def test_emotion_only_field_by_default():
    """对齐官方脚本：情感只发 emotion 单字段，不带 enable_emotion / emotion_scale。"""
    provider = _make_provider(voice_instruction="用非常开心雀跃的语气说话")
    post = _chunked_response([(0, "", base64.b64encode(b"AB").decode()),
                              (20000000, "OK", None)])
    with patch("core.providers.tts.doubao_v3.requests.post", return_value=post) as p:
        _run(provider.text_to_speak("你好", None))
    ap = p.call_args.kwargs["json"]["req_params"]["audio_params"]
    assert ap["emotion"] == "happy"
    assert "enable_emotion" not in ap
    assert "emotion_scale" not in ap


def test_emotion_extras_sent_only_when_configured():
    """enable_emotion / emotion_scale 仅在配置显式给出时附带。"""
    provider = _make_provider(voice_instruction="用非常开心雀跃的语气说话",
                              enable_emotion=True, emotion_scale=9)
    post = _chunked_response([(0, "", base64.b64encode(b"AB").decode()),
                              (20000000, "OK", None)])
    with patch("core.providers.tts.doubao_v3.requests.post", return_value=post) as p:
        _run(provider.text_to_speak("你好", None))
    ap = p.call_args.kwargs["json"]["req_params"]["audio_params"]
    assert ap["enable_emotion"] is True
    # 9 会被钳制到 5（越界会静默返回空音频）
    assert ap["emotion_scale"] == 5


# ---------------------------------------------------------------------------
# chunked 分片解析
# ---------------------------------------------------------------------------
def test_chunked_audio_concatenation(tmp_path):
    provider = _make_provider()
    part1 = base64.b64encode(b"RIFF-header").decode()
    part2 = base64.b64encode(b"-audio-body").decode()
    part3 = base64.b64encode(b"-tail").decode()
    post = _chunked_response([
        (0, "", part1),
        (0, "", part2),
        (0, "", part3),
        (20000000, "OK", None),
    ])
    with patch("core.providers.tts.doubao_v3.requests.post", return_value=post):
        result = _run(provider.text_to_speak("你好", None))
    assert result == b"RIFF-header-audio-body-tail"


def test_unpadded_base64_chunk_decoded():
    """服务端分片 base64 可能不带填充符（长度非 4 对齐）。"""
    provider = _make_provider()
    raw = b"WAVDATA-without-padding-chars"
    # 手工生成无填充 base64
    encoded = base64.b64encode(raw).decode().rstrip("=")
    post = _chunked_response([(0, "", encoded), (20000000, "OK", None)])
    with patch("core.providers.tts.doubao_v3.requests.post", return_value=post):
        result = _run(provider.text_to_speak("你好", None))
    assert result == raw


def test_writes_file(tmp_path):
    provider = _make_provider()
    audio = b"RIFFxxxxWAVEfmt "
    post = _chunked_response([
        (0, "", base64.b64encode(audio[:8]).decode()),
        (0, "", base64.b64encode(audio[8:]).decode()),
        (20000000, "OK", None),
    ])
    out_file = tmp_path / "out.wav"
    with patch("core.providers.tts.doubao_v3.requests.post", return_value=post):
        _run(provider.text_to_speak("你好", str(out_file)))
    assert out_file.read_bytes() == audio


# ---------------------------------------------------------------------------
# 错误处理
# ---------------------------------------------------------------------------
def test_http_error_raises():
    provider = _make_provider()
    resp = Mock(status_code=401)
    resp.text = '{"code":45000001,"message":"auth failed"}'
    with patch("core.providers.tts.doubao_v3.requests.post", return_value=resp):
        with pytest.raises(Exception) as exc_info:
            _run(provider.text_to_speak("你好", None))
    assert "401" in str(exc_info.value)


def test_business_error_code_raises():
    provider = _make_provider()
    post = _chunked_response([
        (0, "", base64.b64encode(b"partial").decode()),
        (45000001, "invalid voice", None),
    ])
    with patch("core.providers.tts.doubao_v3.requests.post", return_value=post):
        with pytest.raises(Exception) as exc_info:
            _run(provider.text_to_speak("你好", None))
    msg = str(exc_info.value)
    assert "45000001" in msg
    assert "invalid voice" in msg


def test_empty_audio_raises():
    provider = _make_provider()
    post = _chunked_response([(20000000, "OK", None)])
    with patch("core.providers.tts.doubao_v3.requests.post", return_value=post):
        with pytest.raises(Exception) as exc_info:
            _run(provider.text_to_speak("你好", None))
    assert "未包含任何音频" in str(exc_info.value)


def test_malformed_chunk_raises():
    provider = _make_provider()
    resp = _mock_response('{"code":0,"message":"","data":"QUJD"} not-json-tail')
    with patch("core.providers.tts.doubao_v3.requests.post", return_value=resp):
        with pytest.raises(Exception) as exc_info:
            _run(provider.text_to_speak("你好", None))
    assert "无法解析" in str(exc_info.value)


# ---------------------------------------------------------------------------
# 默认值
# ---------------------------------------------------------------------------
def test_defaults():
    provider = _make_provider()
    assert provider.api_url == ENDPOINT
    assert provider.resource_id == "seed-tts-2.0"
    assert provider.voice is None
    assert provider.audio_file_type == "wav"
    assert provider.sample_rate == 24000
    assert provider.speech_rate == 0
    assert provider.loudness_rate == 0

"""TTS 试听内部 API（manager-api 代理转发调用，非公开端点）。

安全模型与 memory_handler 一致（design §3.1 同源）：
- ``Authorization: Bearer {server.secret}`` 服务间鉴权（常量时间比较）
- 仅由 manager-api 在同机经 127.0.0.1 调用（http_server 回环中间件防护）
- 管理端登录态由 Java 侧 Shiro 把关，本端点不面向公网

GET /api/tts/preview?voice={voice}&text={text}  （配置经 POST body 传入）
- voice：音色 ID（tts_voice）
- text：试听文本（默认「你好，这是音色试听」，长度上限 60 字符）
- POST body：manager-api 已还原明文的完整 TTS config_json（含 type/凭据等），
  本端点不落盘、不记录凭据，仅用于即时合成一次。

响应：音频二进制（Content-Type 按配置 format 推断），失败返回 {code,msg} JSON。
"""
import asyncio
import hmac

from aiohttp import web

from config.logger import setup_logging
from core.api.base_handler import BaseHandler

TAG = __name__

# 试听文本长度上限（防止滥用作免费朗读通道）
MAX_TEXT_LEN = 60
DEFAULT_TEXT = "你好，这是音色试听。"

# provider type → 音频 MIME
MIME_BY_FORMAT = {
    "wav": "audio/wav",
    "mp3": "audio/mpeg",
    "ogg": "audio/ogg",
    "pcm": "audio/L16",
    "raw": "audio/L16",
    "opus": "audio/ogg",
    "p3": "audio/ogg",
}


def _json_error(status: int, msg: str) -> web.Response:
    return web.json_response({"code": status, "msg": msg, "data": None}, status=status)


class TtsPreviewHandler(BaseHandler):
    def __init__(self, config: dict):
        super().__init__(config)
        # 与 memory_handler 相同的三级 auth_key（app.py 已解析进 config["server"]["auth_key"]）
        self._auth_key = (config.get("server", {}) or {}).get("auth_key") or ""

    def _verify_auth(self, request) -> bool:
        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return False
        token = auth_header[7:]
        return bool(self._auth_key) and hmac.compare_digest(token, self._auth_key)

    async def handle_preview(self, request) -> web.Response:
        if not self._verify_auth(request):
            return _json_error(401, "未授权")

        voice = request.query.get("voice", "").strip()
        text = (request.query.get("text") or "").strip() or DEFAULT_TEXT
        if len(text) > MAX_TEXT_LEN:
            return _json_error(400, f"试听文本超长（>{MAX_TEXT_LEN}字）")

        if not voice:
            return _json_error(400, "voice 必填")

        # POST body：完整 TTS config_json（由 manager-api 从 DB 读取并还原明文）
        try:
            body = await request.json()
        except Exception:
            return _json_error(400, "请求体必须为 JSON")
        if not isinstance(body, dict) or not body.get("type"):
            return _json_error(400, "请求体缺少 type 字段")

        provider_type = str(body["type"])
        provider_config = dict(body)
        # 试听音色覆盖（不污染原配置）
        provider_config["voice"] = voice
        provider_config["speaker"] = voice
        provider_config.pop("private_voice", None)

        try:
            from core.utils.tts import create_instance

            provider = create_instance(provider_type, provider_config, delete_audio_file=True)
            # handler 本身运行在 aiohttp 事件循环内，直接 await（不可 asyncio.run）；
            # 55s 超时兜底：上游 TTS 偶发卡死时及时释放，避免拖垮其它 handler
            audio_bytes = await asyncio.wait_for(
                provider.text_to_speak(text, None), timeout=55.0
            )
        except asyncio.TimeoutError:
            return _json_error(504, "合成超时（55s），请重试")
        except LookupError:
            return _json_error(404, f"不支持的TTS类型: {provider_type}")
        except FileNotFoundError:
            return _json_error(404, f"TTS类型未部署: {provider_type}")
        except Exception as e:
            self.logger.bind(tag=TAG).error(f"TTS试听合成失败: {e}")
            return _json_error(500, f"合成失败: {str(e)[:480]}")

        if not audio_bytes:
            return _json_error(500, "合成返回空音频")

        audio_format = str(provider_config.get("format", "wav")).lower()
        mime = MIME_BY_FORMAT.get(audio_format, "application/octet-stream")
        response = web.Response(body=audio_bytes, content_type=mime)
        self._add_cors_headers(response)
        return response

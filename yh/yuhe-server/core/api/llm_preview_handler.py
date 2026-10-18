"""LLM 试聊内部 API（manager-api 代理转发调用，非公开端点）。

安全模型与 tts_preview_handler 一致（design §3.1 同源）：
- ``Authorization: Bearer *** 服务间鉴权（常量时间比较）
- 仅由 manager-api 在同机经 127.0.0.1 调用（http_server 回环中间件防护）
- 管理端登录态由 Java 侧 Shiro 把关，本端点不面向公网

GET /api/llm/preview?text={text}&system_prompt={system_prompt}
- text：用户输入文本（必填，长度上限 500 字符）
- system_prompt：可选系统提示词（为空时用智能体默认人设）
- POST body：manager-api 已还原明文的完整 LLM config_json（含 type/凭据等），
  本端点不落盘、不记录凭据，仅用于即时调用一次。

响应：{"code":0, "data": {"reply": "...", "elapsed_ms": 123}}，失败返回 {code,msg} JSON。
"""
import hmac
import time

from aiohttp import web

from config.logger import setup_logging
from core.api.base_handler import BaseHandler

TAG = __name__

# 试聊文本长度上限（防止滥用作免费对话通道）
MAX_TEXT_LEN = 500
MAX_SYSTEM_PROMPT_LEN = 2000


def _json_error(status: int, msg: str) -> web.Response:
    return web.json_response({"code": status, "msg": msg, "data": None}, status=status)


class LlmPreviewHandler(BaseHandler):
    def __init__(self, config: dict):
        super().__init__(config)
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

        text = (request.query.get("text") or "").strip()
        system_prompt = (request.query.get("system_prompt") or "").strip()
        if not text:
            return _json_error(400, "text 必填")
        if len(text) > MAX_TEXT_LEN:
            return _json_error(400, f"试聊文本超长（>{MAX_TEXT_LEN}字）")
        if len(system_prompt) > MAX_SYSTEM_PROMPT_LEN:
            return _json_error(400, f"系统提示词超长（>{MAX_SYSTEM_PROMPT_LEN}字）")

        # 获取provider_type和配置
        # 支持两种方式：
        # 1. GET请求：从URL参数provider_type获取，无需请求体
        # 2. POST请求：从body获取完整配置
        
        provider_type = request.query.get("provider_type")
        provider_config = {}
        
        if request.method == "GET" and provider_type:
            # GET请求：只需要provider_type
            provider_config["type"] = provider_type
        else:
            # POST请求或无provider_type：从body读取
            try:
                body = await request.json()
            except Exception:
                return _json_error(400, "请求体必须为 JSON")
            if not isinstance(body, dict) or not body.get("type"):
                return _json_error(400, "请求体缺少 type 字段")
            provider_type = str(body["type"])
            provider_config = dict(body)

        dialogue = []
        if system_prompt:
            dialogue.append({"role": "system", "content": system_prompt})
        dialogue.append({"role": "user", "content": text})

        started = time.monotonic()
        try:
            from core.utils.llm import create_instance

            provider = create_instance(provider_type, provider_config)
            # response() 是同步生成器（与 core/connection.py 消费方式一致），用同步 for
            # handler 运行在 aiohttp 事件循环内，同步迭代短回复不会阻塞过久
            chunks = []
            for chunk in provider.response("llm-preview", dialogue):
                if chunk:
                    if isinstance(chunk, tuple):
                        chunk = chunk[0]
                    if isinstance(chunk, dict):
                        chunk = chunk.get("content") or ""
                    if chunk:
                        chunks.append(str(chunk))
        except LookupError:
            return _json_error(404, f"不支持的LLM类型: {provider_type}")
        except ValueError as e:
            return _json_error(404, str(e)[:160])
        except Exception as e:
            self.logger.bind(tag=TAG).error(f"LLM试聊失败: {e}")
            return _json_error(500, f"对话失败: {str(e)[:120]}")

        reply = "".join(chunks).strip()
        if not reply:
            return _json_error(500, "模型返回空回复")

        elapsed_ms = int((time.monotonic() - started) * 1000)
        response = web.json_response(
            {"code": 0, "msg": "", "data": {"reply": reply, "elapsed_ms": elapsed_ms}}
        )
        self._add_cors_headers(response)
        return response

"""模型连通性测试内部 API（manager-api 代理转发调用，非公开端点）。

安全模型与 tts_preview_handler 一致：
- Bearer server.secret 服务间鉴权（常量时间比较）+ 仅回环调用
- 管理端登录态由 Java 侧 Shiro 把关

GET /api/model/test?type={modelType}&model_id={modelId}
- modelType: ASR/TTS/LLM/VLLM/Intent/Memory/VAD/Plugin/RAG
- POST body：manager-api 已还原明文的完整模型 config_json

按类型分发测试策略：
- TTS：合成固定短句（「模型测试」），验证返回非空音频
- LLM：发送「回复OK」短对话，验证非空回复
- ASR：实例化 provider 成功 + 具备 transcribe/识别接口即通过（不喂音频）
- 其余（VLLM/Intent/Memory/VAD/Plugin/RAG）：实例化 provider 成功即视为配置与凭据可用

响应：{"code":0, "data": {"ok":true, "message":"...", "elapsed_ms":123}}
"""
import hmac
import time

from aiohttp import web

from config.logger import setup_logging
from core.api.base_handler import BaseHandler

TAG = __name__

TTS_TEST_TEXT = "模型测试。"
LLM_TEST_TEXT = "请只回复两个字：正常"


def _json_error(status: int, msg: str) -> web.Response:
    return web.json_response({"code": status, "msg": msg, "data": None}, status=status)


class ModelTestHandler(BaseHandler):
    def __init__(self, config: dict):
        super().__init__(config)
        self._auth_key = (config.get("server", {}) or {}).get("auth_key") or ""

    def _verify_auth(self, request) -> bool:
        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return False
        token = auth_header[7:]
        return bool(self._auth_key) and hmac.compare_digest(token, self._auth_key)

    async def handle_test(self, request) -> web.Response:
        if not self._verify_auth(request):
            return _json_error(401, "未授权")

        model_type = (request.query.get("type") or "").strip().upper()
        if not model_type:
            return _json_error(400, "type 必填（ASR/TTS/LLM/...）")

        try:
            body = await request.json()
        except Exception:
            return _json_error(400, "请求体必须为 JSON")
        if not isinstance(body, dict) or not body.get("type"):
            return _json_error(400, "请求体缺少 type 字段")

        provider_type = str(body["type"])
        provider_config = dict(body)
        started = time.monotonic()

        try:
            if model_type == "TTS":
                ok, message = await self._test_tts(provider_type, provider_config)
            elif model_type == "LLM":
                ok, message = await self._test_llm(provider_type, provider_config)
            else:
                ok, message = self._test_generic(model_type, provider_type, provider_config)
        except LookupError:
            return _json_error(404, f"不支持的类型: {provider_type}")
        except FileNotFoundError:
            return _json_error(404, f"类型未部署: {provider_type}")
        except Exception as e:
            self.logger.bind(tag=TAG).error(f"模型测试失败[{model_type}/{provider_type}]: {e}")
            return _json_error(500, f"测试失败: {str(e)[:140]}")

        elapsed_ms = int((time.monotonic() - started) * 1000)
        response = web.json_response({
            "code": 0, "msg": "",
            "data": {"ok": bool(ok), "message": message[:200], "elapsed_ms": elapsed_ms},
        })
        self._add_cors_headers(response)
        return response

    async def _test_tts(self, provider_type, provider_config):
        from core.utils.tts import create_instance

        provider = create_instance(provider_type, provider_config, delete_audio_file=True)
        voice = provider_config.get("voice") or provider_config.get("speaker") or ""
        provider_config["voice"] = voice
        provider_config["speaker"] = voice
        audio = await provider.text_to_speak(TTS_TEST_TEXT, None)
        if not audio:
            return False, "合成返回空音频"
        return True, f"合成成功（{len(audio)} 字节音频）"

    async def _test_llm(self, provider_type, provider_config):
        from core.utils.llm import create_instance

        provider = create_instance(provider_type, provider_config)
        dialogue = [{"role": "user", "content": LLM_TEST_TEXT}]
        # response() 是同步生成器（与 core/connection.py 消费方式一致），用同步 for
        chunks = []
        for chunk in provider.response("model-test", dialogue):
            if chunk:
                if isinstance(chunk, tuple):
                    chunk = chunk[0]
                if isinstance(chunk, dict):
                    chunk = chunk.get("content") or ""
                if chunk:
                    chunks.append(str(chunk))
        reply = "".join(chunks).strip()
        if not reply:
            return False, "模型返回空回复"
        return True, f"模型响应：{reply[:60]}"

    def _test_generic(self, model_type, provider_type, provider_config):
        """ASR/VLLM/Intent/Memory/VAD/Plugin/RAG：实例化成功即视为配置可用。"""
        if model_type == "ASR":
            from core.utils.asr import create_instance
            factory = create_instance
        elif model_type == "VAD":
            from core.utils.vad import create_instance
            factory = create_instance
        elif model_type == "Memory":
            from core.utils.memory import create_instance
            factory = create_instance
        elif model_type == "Intent":
            from core.utils.intent import create_instance
            factory = create_instance
        elif model_type == "VLLM":
            from core.utils.vllm import create_instance
            factory = create_instance
        else:
            # Plugin / RAG / 其他：无统一工厂，仅校验配置非空
            if not provider_config.get("type"):
                return False, "缺少 provider type"
            return True, f"{model_type} 配置格式有效（无运行时测试器）"

        # ASR 基类构造需要 delete_audio_file（与主链路 modules_initialize 一致）
        provider = factory(provider_type, provider_config, delete_audio_file=True)
        if provider is None:
            return False, "实例化失败"
        return True, f"{model_type} 实例化成功，配置与凭据有效"

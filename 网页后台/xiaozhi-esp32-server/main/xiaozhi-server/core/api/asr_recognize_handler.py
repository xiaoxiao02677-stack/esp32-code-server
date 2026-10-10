"""ASR 语音识别内部 API（cc-console 链路模拟器真实 ASR 端点）。

安全模型与 tts_preview_handler 一致（design §3.1 同源）：
- Authorization: Bearer <server.secret> 服务间鉴权（常量时间比较）
- 仅由 manager-api 在同机经 127.0.0.1 调用（http_server 回环中间件防护）

POST /api/asr/recognize?modelId={modelId}
- Content-Type: audio/webm（浏览器 MediaRecorder 默认）或 audio/wav
- Body：音频二进制
- 响应：{"code":0, "data": {"text": "...", "elapsed_ms": 123}} / {code,msg}

实现：webm/opus → ffmpeg 转 16k 单声道 PCM → WAV 临时文件 → QwenASR
（qwen3_asr_flash.speech_to_text 走 artifacts.temp_path base64 上送）。
"""
import asyncio
import hmac
import os
import subprocess
import tempfile
import time

from aiohttp import web

from config.logger import setup_logging
from core.api.base_handler import BaseHandler

TAG = __name__

# 上传音频大小上限（防滥用）
MAX_AUDIO_BYTES = 2 * 1024 * 1024


def _json_error(status: int, msg: str) -> web.Response:
    return web.json_response({"code": status, "msg": msg, "data": None}, status=status)


class AsrRecognizeHandler(BaseHandler):
    def __init__(self, config: dict):
        super().__init__(config)
        self._auth_key = (config.get("server", {}) or {}).get("auth_key") or ""

    def _verify_auth(self, request) -> bool:
        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return False
        token = auth_header[7:]
        return bool(self._auth_key) and hmac.compare_digest(token, self._auth_key)

    async def handle_recognize(self, request) -> web.Response:
        if not self._verify_auth(request):
            return _json_error(401, "未授权")

        model_id = (request.query.get("modelId") or "").strip()
        if not model_id:
            return _json_error(400, "modelId 必填")

        audio = await request.read()
        if not audio:
            return _json_error(400, "音频内容为空")
        if len(audio) > MAX_AUDIO_BYTES:
            return _json_error(400, "音频过大（>2MB）")

        ctype = (request.headers.get("Content-Type") or "").lower()

        # 读取模型原始配置（与 tts_preview 同源：直读 DB，经 manage-api 传入不可行——
        # 这里由本服务自查 DB？不——与 ttsPreview 模式保持一致：Java 侧已把 rawConfig
        # 放进请求头 X-Asr-Config（服务间内网，非公开），避免本端点直连 DB 的耦合。
        raw_cfg = request.headers.get("X-Asr-Config") or ""
        if not raw_cfg:
            return _json_error(400, "缺少 ASR 配置（X-Asr-Config）")

        import json

        try:
            provider_config = json.loads(raw_cfg)
        except Exception:
            return _json_error(400, "ASR 配置 JSON 解析失败")
        provider_type = str(provider_config.get("type") or "")
        if not provider_type:
            return _json_error(400, "配置缺少 type 字段")

        started = time.monotonic()
        in_file = None
        wav_path = None
        try:
            # ① 浏览器音频 → 16k 单声道 PCM WAV（ffmpeg 解码任意容器）
            suffix = ".webm" if "webm" in ctype or "ogg" in ctype else (
                ".wav" if "wav" in ctype else ".bin")
            with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as f:
                f.write(audio)
                in_file = f.name

            wav_path = in_file + ".16k.wav"
            proc = subprocess.run(
                ["ffmpeg", "-y", "-i", in_file, "-ac", "1", "-ar", "16000",
                 "-f", "wav", wav_path],
                capture_output=True, timeout=30,
            )
            if proc.returncode != 0 or not os.path.exists(wav_path):
                err = proc.stderr.decode("utf-8", "ignore")[-200:]
                return _json_error(400, f"音频解码失败（需要 ffmpeg）: {err}")

            with open(wav_path, "rb") as f:
                wav_bytes = f.read()
            if len(wav_bytes) < 200:
                return _json_error(400, "音频时长过短")

            # ② 走真实 ASR provider（与主链路同一实现）
            from core.utils.asr import create_instance

            provider = create_instance(provider_type, provider_config, delete_audio_file=True)

            # qwen3_asr_flash.speech_to_text 需要 artifacts.temp_path（WAV 文件）
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tf:
                tf.write(wav_bytes)
                temp_wav = tf.name
            try:
                artifacts = provider.AudioArtifacts(
                    pcm_frames=[], pcm_bytes=b"", file_path=None, temp_path=temp_wav
                )
                text, _ = await asyncio.wait_for(
                    provider.speech_to_text([], "cc-sim", artifacts=artifacts),
                    timeout=60.0,
                )
            finally:
                try:
                    os.unlink(temp_wav)
                except OSError:
                    pass

            elapsed = int((time.monotonic() - started) * 1000)
            return web.json_response(
                {"code": 0, "msg": "success",
                 "data": {"text": (text or "").strip(), "elapsed_ms": elapsed}}
            )
        except asyncio.TimeoutError:
            return _json_error(504, "识别超时，请重试")
        except LookupError:
            return _json_error(404, f"不支持的ASR类型: {provider_type}")
        except FileNotFoundError:
            return _json_error(500, "服务器未安装 ffmpeg，无法解码浏览器音频")
        except Exception as e:
            self.logger.bind(tag=TAG).error(f"ASR 识别失败: {e}")
            return _json_error(500, f"识别失败: {str(e)[:200]}")
        finally:
            for p in (in_file, wav_path):
                if p:
                    try:
                        os.unlink(p)
                    except OSError:
                        pass

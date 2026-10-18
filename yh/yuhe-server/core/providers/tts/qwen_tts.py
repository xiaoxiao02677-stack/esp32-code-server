import requests

from core.utils.util import check_model_key
from core.providers.tts.base import TTSProviderBase
from config.logger import setup_logging

TAG = __name__
logger = setup_logging()

# ---------------------------------------------------------------------------
# 千问 TTS 音色参考表（供配置参考 / 前端音色选择器 / 测试使用）。
# 平台音色与模型强绑定，音色与模型不匹配会返回 code=InvalidParameter。
# ---------------------------------------------------------------------------
# qwen3-tts-flash 的 48 个音色（前 24 个为标准普通话音色，
# 中间为多语种/表现力音色，最后 10 个为方言音色）
_QWEN3_TTS_FLASH_VOICES = [
    # 24 个标准普通话音色（qwen3-tts-instruct-flash 仅支持这些）
    "Cherry", "Serena", "Ethan", "Chelsie", "Momo", "Vivian", "Moon", "Maia",
    "Kai", "Nofish", "Bella", "Jennifer", "Ryan", "Katerina", "Aiden",
    "Eldric Sage", "Mia", "Mochi", "Bellona", "Vincent", "Bunny", "Neil",
    "Elias", "Arthur",
    # 其余音色
    "Nini", "Seren", "Pip", "Stella", "Bodega", "Sonrisa", "Alek", "Dolce",
    "Sohee", "Ono Anna", "Lenn", "Emilien", "Andre", "Radio Gol",
    # 10 个方言音色
    "Jada", "Dylan", "Li", "Marcus", "Roy", "Peter", "Sunny", "Eric",
    "Rocky", "Kiki",
]

QWEN_TTS_VOICES = {
    # 48 音色全量
    "qwen3-tts-flash": _QWEN3_TTS_FLASH_VOICES,
    # 仅前 24 个普通话音色
    "qwen3-tts-instruct-flash": _QWEN3_TTS_FLASH_VOICES[:24],
    "qwen-tts": ["Cherry", "Serena", "Ethan", "Chelsie"],
    # qwen-tts-latest 在 qwen-tts 基础上追加 3 个
    "qwen-tts-latest": [
        "Cherry", "Serena", "Ethan", "Chelsie", "Jada", "Dylan", "Sunny",
    ],
}


class TTSProvider(TTSProviderBase):
    # 千问平台（maas.qianwenaiapi.com）有两套 TTS 端点，请求体结构不同，
    # 端点不可混用，按模型族路由：
    #   - 端点A SpeechSynthesizer：qwen-audio-3.x-tts-* 系列
    #     （这些模型不在 /compatible-mode/v1/models 列表里，但实测可用）
    #   - 端点B multimodal-generation：qwen3-tts-* / qwen-tts* 系列
    #     （在 models 列表里，支持 instructions 风格指令）
    ENDPOINT_SPEECH_SYNTHESIZER = (
        "https://maas.qianwenaiapi.com/api/v1/services/audio/tts/SpeechSynthesizer"
    )
    ENDPOINT_MULTIMODAL_GENERATION = (
        "https://maas.qianwenaiapi.com/api/v1/services/aigc/"
        "multimodal-generation/generation"
    )

    def __init__(self, config, delete_audio_file):
        super().__init__(config, delete_audio_file)
        self.api_key = config.get("api_key")
        self.model = config.get("model", "qwen3-tts-flash")
        if config.get("private_voice"):
            self.voice = config.get("private_voice")
        else:
            self.voice = config.get("voice", "Cherry")
        self.sample_rate = int(config.get("sample_rate", 24000))
        self.audio_file_type = config.get("format", "wav")
        # 语音风格指令，仅端点B模型（qwen3-tts-* / qwen-tts*）有效，端点A模型忽略
        self.instructions = config.get("instructions")
        self.output_file = config.get("output_dir", "tmp/")
        model_key_msg = check_model_key("TTS", self.api_key or "")
        if model_key_msg:
            logger.bind(tag=TAG).error(model_key_msg)

    def _use_speech_synthesizer_endpoint(self):
        """端点路由：qwen-audio-* 前缀走端点A，其余（qwen3-tts-* / qwen-tts*）走端点B。

        注意：两套端点的请求体结构不同（端点A 的 format/sample_rate 在 input 内，
        端点B 包在 parameters 里），端点不可混用。
        """
        return self.model.startswith("qwen-audio-")

    def _get_api_url(self):
        if self._use_speech_synthesizer_endpoint():
            return self.ENDPOINT_SPEECH_SYNTHESIZER
        return self.ENDPOINT_MULTIMODAL_GENERATION

    def _build_payload(self, text):
        """按端点构造请求体。"""
        if self._use_speech_synthesizer_endpoint():
            # 端点A：format / sample_rate 直接放在 input 里，无 parameters 包裹
            return {
                "model": self.model,
                "input": {
                    "text": text,
                    "voice": self.voice,
                    "format": self.audio_file_type,
                    "sample_rate": self.sample_rate,
                },
            }
        # 端点B：format / sample_rate 包在 parameters 里
        payload = {
            "model": self.model,
            "input": {
                "text": text,
                "voice": self.voice,
            },
            "parameters": {
                "format": self.audio_file_type,
                "sample_rate": self.sample_rate,
            },
        }
        if self.instructions:
            payload["input"]["instructions"] = self.instructions
        return payload

    @staticmethod
    def _extract_request_id(response):
        """从错误响应里提取 request_id（JSON 体优先，其次响应头）。"""
        try:
            request_id = (response.json() or {}).get("request_id")
            if request_id:
                return request_id
        except Exception:
            pass
        headers = response.headers or {}
        for key in ("request_id", "X-Request-Id", "X-DashScope-Request-Id"):
            if headers.get(key):
                return headers[key]
        return "unknown"

    def _download_audio(self, audio_url):
        """GET 下载 OSS 音频链接（http 链接无需鉴权，24h 内有效）。失败重试 1 次。"""
        last_error = None
        for attempt in range(2):
            try:
                response = requests.get(audio_url, timeout=self.tts_timeout)
                if response.status_code >= 400:
                    raise Exception(f"HTTP {response.status_code}")
                if not response.content:
                    raise Exception("下载的音频内容为空")
                return response.content
            except Exception as e:
                last_error = e
                logger.bind(tag=TAG).warning(
                    f"下载音频失败(第{attempt + 1}次): {e}"
                )
        raise Exception(f"音频下载失败(已重试1次): {last_error}")

    async def text_to_speak(self, text, output_file):
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        try:
            response = requests.post(
                self._get_api_url(),
                json=self._build_payload(text),
                headers=headers,
                timeout=self.tts_timeout,
            )
            if response.status_code >= 400:
                raise Exception(
                    f"HTTP {response.status_code}: {response.text[:200]}"
                    f", request_id={self._extract_request_id(response)}"
                )
            result = response.json()
            # 平台业务错误：音色与模型不匹配 → InvalidParameter；
            # key 无效 → InvalidApiKey
            code = result.get("code")
            if code and code != "OK":
                raise Exception(
                    f"code={code}, message={result.get('message', '')}"
                    f", request_id={result.get('request_id', 'unknown')}"
                )
            # 非流式响应 data 字段为空串，音频需再 GET output.audio.url 下载
            audio_url = ((result.get("output") or {}).get("audio") or {}).get("url")
            if not audio_url:
                raise Exception(
                    f"响应缺少 output.audio.url"
                    f", request_id={result.get('request_id', 'unknown')}"
                )
            audio_bytes = self._download_audio(audio_url)
            if output_file:
                with open(output_file, "wb") as audio_file:
                    audio_file.write(audio_bytes)
            else:
                return audio_bytes
        except Exception as e:
            raise Exception(f"{__name__} error: {e}")

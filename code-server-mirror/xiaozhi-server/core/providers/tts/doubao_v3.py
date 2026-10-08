import base64
import json
import uuid

import requests

from config.logger import setup_logging
from core.utils.util import check_model_key
from core.providers.tts.base import TTSProviderBase

TAG = __name__
logger = setup_logging()

# 豆包语音合成大模型 2.0 音色参考表（供配置参考 / 音色管理默认数据）。
# 完整音色列表见 https://www.volcengine.com/docs/6561/1257544
DOUBAO_V3_VOICES = {
    "zh_female_xiaohe_uranus_bigtts": "小何（温柔女声）",
    "zh_female_wanwanxiaohe_moon_bigtts": "婉婉小何（甜美女声）",
    "zh_female_gaolengyujie_uranus_bigtts": "高冷御姐（御姐女声）",
    "zh_female_vv_uranus_bigtts": "VV（多方言女声）",
    "zh_female_kaixin_uranus_bigtts": "开心（活泼女声）",
    "zh_male_rapunzeluranus_bigtts": " rapunzel（男声）",
    "zh_male_beijingxiaoye_uranus_bigtts": "北京小爷（北京男声）",
    "zh_male_dongbeiheurun_uranus_bigtts": "东北黑润（东北男声）",
    "zh_male_shaonianzixin_moon_bigtts": "少年自心（少年男声）",
    "zh_male_M392_conversation_wvae_bigtts": "M392（对话男声）",
    "zh_female_kaige_moon_bigtts": "凯哥（沉稳女声）",
    "zh_male_zhubo_jupiter_bigtts": "主播（新闻男声）",
}


class TTSProvider(TTSProviderBase):
    """豆包语音合成大模型（火山引擎 v3 HTTP 一次性合成端点）。

    端点：POST https://openspeech.bytedance.com/api/v3/tts/unidirectional
    鉴权：旧版控制台双头 X-Api-App-Id + X-Api-Access-Key（或新版单头 X-Api-Key）
    响应：HTTP chunked，每个 chunk 是一个 JSON 对象 {"code","message","data"}，
          data 为 Base64 音频分片（各自独立 base64，需逐片解码后拼接），
          末片 data 为 null + code=20000000 结束标记。
    """

    DEFAULT_API_URL = "https://openspeech.bytedance.com/api/v3/tts/unidirectional"

    def __init__(self, config, delete_audio_file):
        super().__init__(config, delete_audio_file)
        self.appid = config.get("appid")
        self.access_token = config.get("access_token")
        # 新版控制台 API Key（可选，二选一：api_key 或 appid+access_token）
        self.api_key = config.get("api_key")
        self.resource_id = config.get("resource_id", "seed-tts-2.0")
        self.api_url = config.get("api_url", self.DEFAULT_API_URL)

        if config.get("private_voice"):
            self.voice = config.get("private_voice")
        else:
            self.voice = config.get("speaker") or config.get("voice")

        self.audio_file_type = config.get("format", "wav")
        self.sample_rate = int(config.get("sample_rate", 24000))

        # 音频参数（v3 语义：speech_rate/loudness_rate 范围 [-50,100]）
        self.speech_rate = int(float(config.get("speech_rate", 0)))
        self.loudness_rate = int(float(config.get("loudness_rate", 0)))

        # 语音风格指令（2.0 音色支持指令遵循，如「用标准大陆普通话说话，不要台湾腔」）
        self.voice_instruction = config.get("voice_instruction")

        model_key_msg = check_model_key(
            "TTS", self.api_key or self.access_token or ""
        )
        if model_key_msg:
            logger.bind(tag=TAG).error(model_key_msg)

    def _build_headers(self):
        headers = {
            "Content-Type": "application/json",
            "X-Api-Resource-Id": self.resource_id,
            "X-Api-Request-Id": str(uuid.uuid4()),
        }
        if self.api_key:
            # 新版控制台单头鉴权
            headers["X-Api-Key"] = self.api_key
        else:
            # 旧版控制台双头鉴权
            headers["X-Api-App-Id"] = str(self.appid)
            headers["X-Api-Access-Key"] = self.access_token
        return headers

    def _build_payload(self, text):
        req_params = {
            "text": text,
            "speaker": self.voice,
            "audio_params": {
                "format": self.audio_file_type,
                "sample_rate": self.sample_rate,
                "speech_rate": self.speech_rate,
                "loudness_rate": self.loudness_rate,
            },
        }
        # 指令遵循（火山官方唯一通道，见 docs/6561/1329505、docs/6561/2528925）：
        #   req_params.additions = JSON 序列化后的字符串，内含 context_texts 数组
        #   - 仅「豆包语音合成模型 2.0」官方音色生效（uranus/saturn 系）
        #   - 官方明确「当前字符串列表只第一个值有效」→ 只放 1 条指令
        #   - 复刻/克隆音色需同时传 req_params.model="seed-tts-2.0-expressive" 才生效
        #   - seed-tts-2.0-standard 明确不支持 context_texts
        # 重要：voice_instruction 只是本项目的配置项名，并非火山 API 字段。
        #       早期实现直接写 req_params["voice_instruction"]，服务端对未知字段
        #       静默忽略（请求照常 200、音频照常返回），表现为「指令不起作用」。
        if self.voice_instruction:
            req_params["additions"] = json.dumps(
                {"context_texts": [self.voice_instruction]}, ensure_ascii=False
            )
        return {
            "user": {"uid": "xiaozhi-esp32-server"},
            "req_params": req_params,
        }

    @staticmethod
    def _decode_base64_chunk(data):
        """解码单个 base64 分片（服务端分片长度非 4 对齐时不带填充符）。"""
        clean = "".join(data.split())
        padding = (-len(clean)) % 4
        return base64.b64decode(clean + "=" * padding)

    def _parse_chunked_response(self, response):
        """解析 chunked JSON 流：逐对象提取 data 分片，解码拼接为完整音频字节。"""
        decoder = json.JSONDecoder()
        text = response.text
        audio = bytearray()
        pos = 0
        length = len(text)
        while pos < length:
            # 跳过分隔空白
            while pos < length and text[pos] in " \r\n\t":
                pos += 1
            if pos >= length:
                break
            try:
                obj, end = decoder.raw_decode(text, pos)
            except json.JSONDecodeError as e:
                raise Exception(f"响应包含无法解析的分片: {e}")
            pos = end
            code = obj.get("code")
            if code not in (0, 20000000):
                raise Exception(
                    f"code={code}, message={obj.get('message', '')}"
                )
            data = obj.get("data")
            if isinstance(data, str) and data:
                audio.extend(self._decode_base64_chunk(data))
        return bytes(audio)

    async def text_to_speak(self, text, output_file):
        try:
            response = requests.post(
                self.api_url,
                json=self._build_payload(text),
                headers=self._build_headers(),
                timeout=self.tts_timeout,
            )
            if response.status_code != 200:
                raise Exception(
                    f"HTTP {response.status_code}: {response.text[:200]}"
                )
            audio_bytes = self._parse_chunked_response(response)
            if not audio_bytes:
                raise Exception("响应未包含任何音频数据")
            if output_file:
                with open(output_file, "wb") as audio_file:
                    audio_file.write(audio_bytes)
            else:
                return audio_bytes
        except Exception as e:
            raise Exception(f"{__name__} error: {self._friendly_error(e)}")

    @staticmethod
    def _friendly_error(e):
        """把火山上游的典型错误翻译成可操作的中文提示。"""
        msg = str(e)
        if "resource ID is mismatched with speaker" in msg:
            return (
                f"{msg} —— 该音色是「声音复刻(克隆)音色」(S_ 开头)，与当前模型配置的 "
                f"resource(seed-tts-2.0，仅支持官方预置音色)不匹配。"
                f"请改用官方音色，或为复刻音色单独配置 TTS 模型"
                f"(resource_id=volc.megatts.default，且凭据需属于克隆该音色的应用)"
            )
        if "45000030" in msg:
            return (
                f"{msg} —— 当前凭据未被授权使用该资源(复刻合成/对应 resource)。"
                f"请到火山引擎控制台核对：音色归属的应用 appid、复刻服务是否开通"
            )
        return msg

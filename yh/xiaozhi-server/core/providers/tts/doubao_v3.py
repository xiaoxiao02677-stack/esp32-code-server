import base64
import json
import uuid

import requests

from config.logger import setup_logging
from core.utils.util import check_model_key
from core.utils.tts import convert_percentage_to_range
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

# 语气指令关键词 -> 火山 emotion 官方枚举。
# 说明：实测非法 emotion 值会被服务端「静默忽略」（照样返回 200 + 音频），
#       所以这里只收录官方 2.0 文档列出的枚举，避免静默退化成无情感。
EMOTION_KEYWORDS = {
    "happy": ("开心", "高兴", "快乐", "愉快", "喜悦", "欢喜", "雀跃", "兴高采烈",
              "笑", "乐", "甜", "happy", "joy"),
    "sad": ("难过", "伤心", "悲伤", "沮丧", "失落", "低落", "哭", "哽咽", "忧郁",
            "委屈", "消沉", "sad"),
    "angry": ("生气", "愤怒", "气愤", "恼火", "发火", "愤怒", "暴躁", "怒", "愤",
              "训斥", "angry"),
    "scared": ("害怕", "恐惧", "惊慌", "紧张", "颤抖", "发抖", "吓", "scared", "fear"),
    "surprised": ("惊讶", "震惊", "惊奇", "意外", "居然", "没想到", "不敢相信",
                  "surprised"),
    "hate": ("厌恶", "讨厌", "嫌弃", "鄙视", "不屑", "反感", "hate", "disgust"),
    "excited": ("激动", "亢奋", "热血", "振奋", "迫不及待", "欢呼", "excited"),
    "coldness": ("冷淡", "冷漠", "高冷", "冰冷", "敷衍", "无所谓", "漫不经心",
                 "coldness"),
    "neutral": ("平静", "平淡", "中性", "自然", "平稳", "客观", "neutral"),
}

# emotion_scale 实测有效区间：1~5。
# 0 或 >=6 服务端会返回「空音频」（code 正常、data 全空），是静默失败坑，必须钳制。
EMOTION_SCALE_MIN = 1
EMOTION_SCALE_MAX = 5


class TTSProvider(TTSProviderBase):
    """豆包语音合成大模型（火山引擎 v3 HTTP 单向流式合成端点）。

    端点：POST https://openspeech.bytedance.com/api/v3/tts/unidirectional
    通信方式（严格对齐火山官方 声音复刻 V3 脚本）：
      - 用 json 提交：requests.post(url, json=payload, stream=True)
      - 顶层三件套：user.uid / namespace("BidirectionalTTS") / req_params
      - req_params：text / speaker / audio_params / additions
      - 复刻音色：prepaid 用 speaker=S_xxx；postpaid 用 speaker="custom_speaker_id"
                  外加 req_params.custom_speaker_id
      - 语气指令：additions.context_texts = [用户传入的语气指令]  <- 官方指令通道
      - 情感：audio_params.emotion（官方脚本唯一情感字段）；
              enable_emotion / emotion_scale 为可选扩展，配置里不给就不发
      - 解析：resp.iter_lines(decode_unicode=True)，code==20000000 且
              message.lower()=="ok" 结束；code 非 0/20000000 判错
    """

    DEFAULT_API_URL = "https://openspeech.bytedance.com/api/v3/tts/unidirectional"
    DEFAULT_NAMESPACE = "BidirectionalTTS"
    DEFAULT_UID = "xiaozhi-esp32-server"

    def __init__(self, config, delete_audio_file):
        super().__init__(config, delete_audio_file)
        self.appid = config.get("appid")
        self.access_token = config.get("access_token")
        # 新版控制台 API Key（可选，二选一：api_key 或 appid+access_token）
        self.api_key = config.get("api_key")
        self.resource_id = config.get("resource_id", "seed-tts-2.0")
        self.api_url = config.get("api_url", self.DEFAULT_API_URL)

        # 音色：优先复刻音色(private_voice)，其次 speaker / voice
        if config.get("private_voice"):
            self.voice = config.get("private_voice")
        else:
            self.voice = config.get("speaker") or config.get("voice")
        # 声音复刻计费方式：prepaid(预付费，speaker=S_xxx) / postpaid(后付费，custom_speaker_id)
        self.speaker_type = str(config.get("speaker_type", "prepaid")).lower()
        self.custom_speaker_id = config.get("custom_speaker_id")

        self.audio_file_type = config.get("format", "wav")
        self.sample_rate = int(float(config.get("sample_rate", 24000)))

        # 音频参数（v3 语义：speech_rate/loudness_rate 范围 [-50,100]）
        # 管理台下发的 ttsRate（-50~100 百分比）优先：经百分比→范围映射后生效；
        # 未下发时回落模型自身配置的 speech_rate 原始键（默认 0）
        if "ttsRate" in config:
            self.speech_rate = int(
                convert_percentage_to_range(config["ttsRate"], -50, 100, 0)
            )
        else:
            self.speech_rate = int(float(config.get("speech_rate", 0)))
        self.loudness_rate = int(float(config.get("loudness_rate", 0)))

        # 语音风格指令（2.0 音色支持指令遵循，如「用标准大陆普通话说话，不要台湾腔」）
        # 用户每轮传入的「语气指令」经 set_dynamic_instruction() 覆盖这里，
        # 最终作为 additions.context_texts 发出（官方唯一指令通道）。
        self.voice_instruction = config.get("voice_instruction")

        # 情感控制（严格对齐官方脚本）
        # 官方脚本 audio_params 里只有 EMOTION 一个情感字段：
        #     if EMOTION: req_params["audio_params"]["emotion"] = EMOTION
        # enable_emotion / emotion_scale 不是官方脚本字段，默认 None 即不发送，
        # 只有在配置里显式写了才附带（保留回退能力）。
        self.emotion = config.get("emotion")
        self.enable_emotion = config.get("enable_emotion")
        self.emotion_scale = config.get("emotion_scale")
        if self.emotion_scale is not None:
            self.emotion_scale = self._clamp_emotion_scale(self.emotion_scale)
        # 是否允许从语气指令里自动推断 emotion（默认开）
        self.auto_emotion = bool(config.get("auto_emotion", True))
        # 显式语言（官方脚本 EXPLICIT_LANGUAGE，默认 "" 即留空=自动/中英混）
        # 官方脚本注释：「中文可不填」，故默认不发送该字段。
        self.explicit_language = config.get("explicit_language")
        # namespace（官方脚本固定 BidirectionalTTS；实测复刻/非复刻均安全）
        self.namespace = config.get("namespace", self.DEFAULT_NAMESPACE)
        # model：官方脚本不传该字段；复刻音色确需时可显式配置
        self.model = config.get("model")
        # user.uid（官方脚本 UID）
        self.uid = config.get("uid", self.DEFAULT_UID)

        model_key_msg = check_model_key(
            "TTS", self.api_key or self.access_token or ""
        )
        if model_key_msg:
            logger.bind(tag=TAG).error(model_key_msg)

    # ------------------------------------------------------------------ #
    # 参数处理
    # ------------------------------------------------------------------ #
    @staticmethod
    def _clamp_emotion_scale(value):
        """把 emotion_scale 钳制到实测有效区间 [1,5]。

        实测：scale=0 或 >=6 时火山返回「空音频」（code 正常但 data 全空），
        属于静默失败，必须在发出请求前拦掉。
        """
        try:
            scale = int(float(value))
        except (TypeError, ValueError):
            return 4
        return max(EMOTION_SCALE_MIN, min(EMOTION_SCALE_MAX, scale))

    @classmethod
    def _infer_emotion(cls, instruction):
        """从中文语气指令里推断官方 emotion 枚举；推断不出返回 None。

        例：「用非常开心、兴奋的语气说话」-> "happy"
        """
        if not instruction:
            return None
        text = str(instruction).lower()
        for emotion, keywords in EMOTION_KEYWORDS.items():
            for kw in keywords:
                if kw in text:
                    return emotion
        return None

    def _is_clone_resource(self):
        """声音复刻(克隆)资源：seed-icl-*，或音色为 S_ 前缀。"""
        return str(self.resource_id).startswith("seed-icl") or str(
            self.voice or ""
        ).startswith("S_")

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
        """按火山官方 声音复刻 V3 脚本逐字段组装请求体。

        官方脚本结构（本方法与其一一对应）：
            payload = {
                "user":      {"uid": UID},
                "namespace": "BidirectionalTTS",
                "req_params": {
                    "text":         TEXT,
                    "speaker":      SPEAKER_ID | "custom_speaker_id",
                    "audio_params": {format, sample_rate, speech_rate,
                                     loudness_rate, emotion?},
                    "additions":    JSON字符串 {explicit_language?,
                                                context_texts?},
                },
            }

        用户每轮传入的「语气指令」= additions.context_texts（官方指令通道）。
        """
        # 1) 语气指令：优先动态指令（connection 每轮注入），回落固定指令。
        #    这就是用户在控制台/对话里传进来的那句「用开心的语气说话」。
        instruction = self._dynamic_instruction or self.voice_instruction

        # 2) audio_params：官方脚本顺序 format/sample_rate/speech_rate/loudness_rate
        audio_params = {
            "format": self.audio_file_type,
            "sample_rate": self.sample_rate,
            "speech_rate": self.speech_rate,
            "loudness_rate": self.loudness_rate,
        }

        # 3) 情感：官方脚本只发 emotion 单字段
        #    （if EMOTION: audio_params["emotion"] = EMOTION）
        emotion = self.emotion
        if not emotion and self.auto_emotion:
            emotion = self._infer_emotion(instruction)
        if emotion:
            audio_params["emotion"] = emotion
            # 非官方脚本字段，仅在配置显式指定时附带
            if self.enable_emotion is not None:
                audio_params["enable_emotion"] = bool(self.enable_emotion)
            if self.emotion_scale is not None:
                audio_params["emotion_scale"] = self._clamp_emotion_scale(
                    self.emotion_scale
                )

        # 4) speaker：prepaid=S_xxx；postpaid="custom_speaker_id"
        if self.speaker_type == "postpaid":
            speaker = "custom_speaker_id"
        else:
            speaker = self.voice

        req_params = {
            "text": text,
            "speaker": speaker,
            "audio_params": audio_params,
        }

        # 后付费复刻：真实音色走 custom_speaker_id
        if self.speaker_type == "postpaid":
            if self.custom_speaker_id or self.voice:
                req_params["custom_speaker_id"] = (
                    self.custom_speaker_id or self.voice
                )

        # model：官方脚本不传；复刻音色确需时可在配置里显式指定
        if self.model:
            req_params["model"] = self.model

        # 5) additions：context_texts = 用户语气指令（官方唯一指令通道）
        #    - 官方明确「当前字符串列表只第一个值有效」→ 只放 1 条指令
        additions = {}
        if self.explicit_language:
            additions["explicit_language"] = self.explicit_language
        if instruction:
            additions["context_texts"] = [instruction]
        if additions:
            req_params["additions"] = json.dumps(
                additions, ensure_ascii=False
            )

        # 6) 顶层三件套：user / namespace / req_params（顺序对齐官方脚本）
        payload = {
            "user": {"uid": self.uid},
            "req_params": req_params,
        }
        if self.namespace:
            payload["namespace"] = self.namespace
        return payload

    # ------------------------------------------------------------------ #
    # 响应解析
    # ------------------------------------------------------------------ #
    @staticmethod
    def _decode_base64_chunk(data):
        """解码单个 base64 分片（服务端分片长度非 4 对齐时不带填充符）。"""
        clean = "".join(data.split())
        padding = (-len(clean)) % 4
        return base64.b64decode(clean + "=" * padding)

    def _parse_chunked_response(self, response):
        """按官方脚本方式解析：iter_lines 逐行读，收完 data 后自然结束。

        官方脚本判定：
          - code == 20000000 且 message == "ok" -> 正常结束，break
          - code 非 0 且非 20000000           -> 报错
        实测火山结束帧的 message 是 "OK"（大写），官方脚本的 "ok" 判定
        永远不会命中，它是靠「流读完」才退出的。这里保留同样的行为，
        但把大小写差异抹平（.lower() == "ok"），既能正常 break，
        又不会因 message 文案变化而漏收音频。
        """
        audio = bytearray()
        for line in response.iter_lines(decode_unicode=True):
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError as e:
                raise Exception(f"响应包含无法解析的分片: {e}")

            code = obj.get("code")
            data = obj.get("data")

            if code == 20000000:
                # 结束帧：先收尾片数据（通常 data 为 null），再退出
                if isinstance(data, str) and data:
                    audio.extend(self._decode_base64_chunk(data))
                message = str(obj.get("message") or "").strip().lower()
                if message == "ok":
                    break
                # message 不是 ok（火山曾返回大写 OK，未来可能改文案）：
                # 继续读，流结束自然退出，不报错、不丢数据
                continue

            if code not in (0, None):
                raise Exception(
                    f"code={code}, message={obj.get('message', '')}"
                )

            if isinstance(data, str) and data:
                audio.extend(self._decode_base64_chunk(data))
        return bytes(audio)

    async def text_to_speak(self, text, output_file):
        try:
            response = requests.post(
                self.api_url,
                json=self._build_payload(text),
                headers=self._build_headers(),
                stream=True,
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
                f"(resource_id=seed-icl-2.0，且凭据需属于克隆该音色的应用)"
            )
        if "45000030" in msg:
            return (
                f"{msg} —— 当前凭据未被授权使用该资源(复刻合成/对应 resource)。"
                f"请到火山引擎控制台核对：音色归属的应用 appid、复刻服务是否开通"
            )
        return msg

"""豆包 TTS 动态语气指令补丁（doubao_v3.py）：
- 下发配置带 dynamic_instruction=true 时，按会话周期用 LLM 读取
  短期聊天记录 + 长期记忆，生成口语化的语气指令（voice_instruction），
  缓存到本会话结束；LLM 失败或未配置时回退固定 voice_instruction。
- instruction_llm_id 指定生成用的 LLM 模型 id（缺省用连接主 LLM 配置）。
"""
import re
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

        # ===== 动态语气指令（屿禾工坊定制）=====
        self.dynamic_instruction = bool(config.get("dynamic_instruction"))
        self.instruction_llm_id = config.get("instruction_llm_id")
        # 本会话缓存：session_id -> 生成的指令（连接断开/换会话自动失效）
        self._dynamic_cache = {}

        model_key_msg = check_model_key(
            "TTS", self.api_key or self.access_token or ""
        )
        if model_key_msg:
            logger.bind(tag=TAG).error(model_key_msg)

    # ---------- 动态指令 ----------
    @staticmethod
    def _session_key():
        conn = TTSProviderBase._current_conn  # 可能不存在，兼容处理
        return None

    def _get_session_chat(self):
        """抓当前连接（conn 通过线程局部/生成器闭包挂到 provider 上）。"""
        return getattr(self, "_session_chat_snapshot", None)

    def _dynamic_instruction_for(self):
        """生成本轮语音指令（会话内只生成一次，带失败降级）。"""
        if not self.dynamic_instruction:
            return self.voice_instruction
        conn = getattr(self, "conn", None)
        key = None
        if conn is not None:
            key = getattr(conn, "session_id", None) or id(conn)
        if key is not None and key in self._dynamic_cache:
            return self._dynamic_cache[key]

        result = self.voice_instruction  # 降级：固定指令
        try:
            generated = self._generate_instruction()
            if generated:
                result = generated
        except Exception as e:
            logger.bind(tag=TAG).warning(f"动态语气指令生成失败，回退固定指令: {e}")
        if key is not None:
            self._dynamic_cache[key] = result
        return result

    def _generate_instruction(self):
        """用 LLM 读短期聊天 + 长期记忆，生成口语化语气指令。"""
        conn = getattr(self, "conn", None)
        if conn is None:
            return None

        short_chat = []
        long_mem = []
        try:
            short_chat = conn.short_term_memory.get_chat_messages()[-6:] \
                if getattr(conn, "short_term_memory", None) else []
        except Exception:
            short_chat = []
        try:
            if getattr(conn, "mem0", None) and getattr(conn, "long_term_memory", None):
                long_mem = conn.long_term_memory.get_summary_memories()
        except Exception:
            long_mem = []

        # 组装聊天摘要文本
        lines = []
        for m in short_chat:
            role = getattr(m, "role", "user")
            content = getattr(m, "content", "")
            if content:
                lines.append(f"{role}: {content}")
        chat_text = "\n".join(lines[-12:]) or "（暂无聊天记录）"
        mem_text = "\n".join([str(m) for m in (long_mem or [])][-10:]) or "（暂无长期记忆）"

        prompt = (
            "你是语音语气指令生成器。根据下面的短期聊天记录和长期记忆，"
            "生成一条给 TTS 语音合成引擎的语气指令（不超过 60 字）。\n"
            "要求：\n"
            "1. 口语化、自然，符合用户与助手的真实聊天氛围；\n"
            "2. 只描述说话方式（语气/语速/情绪/口癖），不要复述聊天内容；\n"
            "3. 直接输出指令文本，不要任何解释或标点包裹。\n\n"
            f"[短期聊天记录]\n{chat_text}\n\n[长期记忆]\n{mem_text}\n\n语气指令："
        )

        # LLM 配置来源：instruction_llm_id 指定 → 单独拉配置；否则复用连接主 LLM
        cfg = None
        if self.instruction_llm_id:
            try:
                from core.utils.http_client import HttpClient
                from config import config as global_config
                from core.utils.util import get_path
                api_key = global_config.get("manager_api_key")
                base = global_config.get("manager_api_url", "http://127.0.0.1:8002/xiaozhi")
                resp = requests.get(
                    f"{base}/models/{self.instruction_llm_id}",
                    headers={"Authorization": f"Bearer {api_key}"},
                    timeout=8,
                )
                if resp.status_code == 200:
                    data = resp.json()
                    if data.get("code") == 0 and data.get("data"):
                        cfg = data["data"].get("configJson") or {}
            except Exception as e:
                logger.bind(tag=TAG).warning(f"拉取 instruction_llm 配置失败: {e}")
        if not cfg:
            cfg = getattr(conn, "llm_config", None) or {}

        llm = self._build_llm(cfg)
        if llm is None:
            return None
        out = llm(prompt)
        text = (out or "").strip().strip("「」\"'")
        return text[:80] if text else None

    def _build_llm(self, cfg):
        """极简 OpenAI 兼容 LLM 调用（同步，短文本生成，30s 超时）。"""
        api_key = cfg.get("api_key") or cfg.get("apiKey") or ""
        base_url = (cfg.get("base_url") or cfg.get("api_url") or "").rstrip("/")
        model = cfg.get("model_name") or cfg.get("model") or ""
        if not api_key or not model:
            return None
        if not base_url:
            base_url = "https://api.openai.com/v1"

        def call(prompt):
            resp = requests.post(
                f"{base_url}/chat/completions",
                headers={"Authorization": f"Bearer {api_key}"},
                json={
                    "model": model,
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": 120,
                    "temperature": 0.8,
                },
                timeout=30,
            )
            resp.raise_for_status()
            data = resp.json()
            return data["choices"][0]["message"]["content"]

        return call

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
        # 动态指令优先；无动态时用固定指令（仅 2.0 系音色生效，服务端忽略不支持的音色）
        instruction = self._dynamic_instruction_for()
        if instruction:
            req_params["voice_instruction"] = instruction
        return {
            "user": {"uid": "xiaozhi-esp32-server"},
            "req_params": req_params,
        }

    @staticmethod
    def _decode_base64_chunk(data):
        """解码单个 base64 分片（服务端分片长度非 4 对齐时不带填充符）。"""
        if not data:
            return b""
        try:
            padded = data + "=" * (-len(data) % 4)
            return base64.b64decode(padded)
        except Exception:
            return base64.b64decode(data + "==")

    def _parse_chunked_response(self, response):
        """解析 chunked JSON 流，拼接 base64 音频分片。"""
        audio_parts = []
        final_code = None
        for line in response.iter_lines():
            if not line:
                continue
            try:
                chunk = json.loads(line)
            except Exception:
                continue
            code = chunk.get("code")
            data = chunk.get("data")
            if data:
                audio_parts.append(self._decode_base64_chunk(data))
            elif code is not None:
                final_code = code
        if final_code is not None and final_code != 20000000:
            logger.bind(tag=TAG).warning(f"豆包 v3 流结束码: {final_code}")
        return b"".join(audio_parts)

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
        return msg

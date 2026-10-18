import os
import asyncio
from typing import Optional, Tuple, List
import requests
from config.logger import setup_logging
from core.providers.asr.base import ASRProviderBase
from core.providers.asr.dto.dto import InterfaceType

TAG = __name__
logger = setup_logging()

# 千问平台同步 ASR 端点（官方文档 RESTful 形态，2026-10-07 实测可用）
# - 模型：qwen-audio-3.1-asr-flash / qwen-audio-3.0-asr-flash / fun-asr-flash 系列
# - 请求体：input.messages[].content[] 为 {type:"input_audio", input_audio:{data:<本地路径或URL>}}
# - 响应体：顶层 sentence.text 与 text 均为识别文本（实测双字段一致）
# - 注意：qwen3-asr-flash（dashscope SDK 顶层 messages 形态）在本平台不可用（400），勿改回
ASR_URL = "https://maas.qianwenaiapi.com/api/v1/services/aigc/multimodal-generation/generation"


class ASRProvider(ASRProviderBase):
    def __init__(self, config: dict, delete_audio_file: bool):
        super().__init__()
        # 音频文件上传类型，非流式文本识别输出
        self.interface_type = InterfaceType.NON_STREAM
        """千问 Qwen-Audio-ASR 初始化"""

        # 配置参数
        self.api_key = config.get("api_key")
        if not self.api_key:
            raise ValueError("千问ASR 需要配置 api_key")

        self.model_name = config.get("model_name", "qwen-audio-3.1-asr-flash")
        self.output_dir = config.get("output_dir", "./audio_output")
        self.delete_audio_file = delete_audio_file
        self.format = config.get("format", "wav")
        self.sample_rate = int(config.get("sample_rate", 16000))
        self.timeout = int(config.get("timeout", 120))

        # 确保输出目录存在
        os.makedirs(self.output_dir, exist_ok=True)

    def prefers_temp_file(self) -> bool:
        return True

    def requires_file(self) -> bool:
        return True

    def _read_audio_b64(self, path: str) -> str:
        import base64
        with open(path, "rb") as f:
            return base64.b64encode(f.read()).decode("ascii")

    async def speech_to_text(
        self, opus_data: List[bytes], session_id: str, artifacts=None
    ) -> Tuple[Optional[str], Optional[str]]:
        """将语音数据转换为文本（同步端点，本地文件以 base64 内联上送）"""
        file_path = None
        try:
            if artifacts is None:
                return "", None
            file_path = artifacts.file_path
            temp_file_path = artifacts.temp_path
            if not temp_file_path:
                return "", file_path

            # 本地文件 → base64 内联（data 字段支持 URL 或 base64）
            audio_b64 = self._read_audio_b64(temp_file_path)

            payload = {
                "model": self.model_name,
                "input": {
                    "messages": [
                        {
                            "role": "user",
                            "content": [
                                {
                                    "type": "input_audio",
                                    "input_audio": {"data": "data:application/octet-stream;base64," + audio_b64},
                                }
                            ],
                        }
                    ]
                },
                "parameters": {"format": self.format, "sample_rate": str(self.sample_rate)},
            }
            headers = {
                "Authorization": "Bearer " + self.api_key,
                "Content-Type": "application/json",
                "X-DashScope-SSE": "disable",
            }
            # 在线程池中执行同步 HTTP 请求，避免阻塞事件循环（模拟器端点与设备主链路共用）
            resp = await asyncio.to_thread(
                requests.post, ASR_URL, json=payload, headers=headers, timeout=self.timeout
            )
            if resp.status_code != 200:
                logger.bind(tag=TAG).error(
                    "千问ASR HTTP {}: {}", resp.status_code, resp.text[:200]
                )
                return "", file_path
            data = resp.json()
            if data.get("code") and data.get("code") not in (0, "0", "OK"):
                logger.bind(tag=TAG).error(
                    "千问ASR 业务错误 [{}] {} (request_id={})",
                    data.get("code"), data.get("message", ""), data.get("request_id", ""),
                )
                return "", file_path
            # 顶层 sentence.text 与 text 双字段一致（实测），优先 text
            text = (data.get("text") or "").strip() or (
                (((data.get("sentence") or {}).get("text")) or "").strip()
            )
            return text, file_path
        except Exception as e:
            logger.bind(tag=TAG).error("语音识别失败: {}", e)
            return "", file_path

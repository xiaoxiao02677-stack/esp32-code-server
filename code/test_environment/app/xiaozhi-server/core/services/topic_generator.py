#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""话题源随机聊天生成管线。

功能：
- 多源随机选题：从 memory / weather / chat 三个源中随机挑选一个，再在该源内随机取材。
- 降级链：memory → weather → chat → 跳过（每步失败记日志并降级）。
- LLM 调用包装 asyncio.to_thread，避免阻塞事件循环；外层 wait_for 设超时并自动重试。
- TTS 合成复用 initialize_tts fallback 链（默认挂 EdgeTTS），仅可用 delete_audio_file=False 模式。
- 合成结果写入 tmp/ 目录，返回 http://host/tmp/filename 格式的 URL。
- 同 agent 去重：通过 wake_word_service._agent_devices 反查 agent → devices，按 agent 聚合后去重。
"""
import asyncio
import logging
import os
import random
import time
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)
TAG = __name__

# 降级链顺序
_FALIBACK_CHAIN = ["memory", "weather", "chat"]

# 闲聊开场白模板
_CHAT_OPENINGS = [
    "嘿，你今天在干嘛呀？",
    "今天过得怎么样？",
    "有什么有趣的事情想和我分享吗？",
    "你现在心情怎么样？",
    "今天天气不错呢，你有什么打算？",
    "最近有没有遇到什么好玩的事？",
    "你在做什么呢？",
    "跟我说说你的今天吧！",
]

# LLM 调用超时（秒）
_LLM_TIMEOUT = 20.0
# LLM 重试次数
_LLM_MAX_RETRIES = 2


class TopicGenerator:
    """话题源随机聊天生成器。

    Args:
        config: 服务端完整配置字典（包含 TTS、LLM、Memory、server 等 section）
        conn: ConnectionHandler 实例（需要 client_ip、loop 属性）
        wake_word_service: WakeWordService 实例（用于 agent→devices 反查）
    """

    def __init__(
        self,
        config: dict,
        conn: Any,
        wake_word_service=None,
    ):
        self._config = config
        self._client_ip = getattr(conn, "client_ip", None)
        self._loop = getattr(conn, "loop", None) or asyncio.get_event_loop()
        self._wake_word_service = wake_word_service

        # 延迟初始化，避免循环导入
        self._tts_provider = None
        self._llm_provider = None
        self._memory_providers: Dict[str, Any] = {}  # agent_id -> provider 惰性缓存

    # ------------------------------------------------------------------
    # 公共接口
    # ------------------------------------------------------------------

    async def generate(
        self,
        device_id: str,
        topic_sources: List[str],
        location: Optional[str] = None,
    ) -> dict:
        """随机生成一条话题文案 + TTS 音频 URL。

        Args:
            device_id: 触发设备的 ID（用于日志）
            topic_sources: 话题源列表，取值子集 ⊆ {"memory", "weather", "chat"}
            location: 可选的地理位置（覆盖天气源默认城市）

        Returns:
            {
                "text": str,           # 生成文案
                "audio_url": str,      # http URL，可被设备直接访问
                "subtitles": [{"text": str}],
                "generation_meta": {
                    "source": str,     # 实际使用的源（memory/weather/chat/skipped）
                    "fallback_used": bool,
                },
            }
        """
        # 规范化 topic_sources
        valid_sources = set(topic_sources) & set(_FALIBACK_CHAIN)
        if not valid_sources:
            logger.warning("[%s] topic_sources 全部无效，跳过生成", TAG)
            return self._empty_result(device_id)

        # 按降级链顺序，随机打乱后依次尝试
        sources_to_try = list(valid_sources)
        random.shuffle(sources_to_try)

        text = None
        used_source = None
        fallback_used = False

        for source in sources_to_try:
            try:
                text = await self._fetch_topic_text(source, location)
                used_source = source
                break
            except Exception as e:
                logger.warning(
                    "[%s] 话题源 '%s' 获取失败，降级到下一源: %s", TAG, source, e
                )
                fallback_used = True

        if text is None:
            logger.error("[%s] 所有话题源均失败，跳过本次生成", TAG)
            return self._empty_result(device_id)

        # TTS 合成
        try:
            audio_url = await self._synthesize_tts(text, device_id, used_source)
        except Exception as e:
            logger.error("[%s] TTS 合成失败: %s", TAG, e, exc_info=True)
            # TTS 失败时仍返回文案，audio_url 留空让设备仅显示字幕
            audio_url = ""

        meta = {
            "source": used_source or "skipped",
            "fallback_used": fallback_used,
        }
        subtitles = [{"text": text}]
        return {
            "text": text,
            "audio_url": audio_url,
            "subtitles": subtitles,
            "generation_meta": meta,
        }

    async def generate_for_agent(
        self,
        agent_id: str,
        topic_sources: List[str],
        location: Optional[str] = None,
    ) -> dict:
        """按指定 agent 生成话题（该 agent 下所有设备共用同一话题）。

        Returns:
            dict 结构与 generate() 相同。
        """
        logger.info(
            "[%s] agent=%s 生成话题: sources=%s, location=%s",
            TAG, agent_id, topic_sources, location,
        )
        return await self.generate(agent_id, topic_sources, location)

    # ------------------------------------------------------------------
    # 内部实现
    # ------------------------------------------------------------------

    def _empty_result(self, device_id: str) -> dict:
        return {
            "text": "",
            "audio_url": "",
            "subtitles": [],
            "generation_meta": {"source": "skipped", "fallback_used": False},
        }

    async def _fetch_topic_text(
        self, source: str, location: Optional[str]
    ) -> str:
        """从指定源获取原始文本素材（未 LLM 加工）。"""
        if source == "memory":
            return await self._fetch_memory()
        elif source == "weather":
            return await self._fetch_weather(location)
        elif source == "chat":
            return await self._fetch_chat()
        raise ValueError(f"未知话题源: {source}")

    async def _fetch_memory(self) -> str:
        """从记忆库随机取一条记忆作为话题素材。"""
        memory_type = self._config.get("selected_module", {}).get("Memory", "nomem")
        if memory_type in ("nomem", "mem_report_only"):
            raise RuntimeError(f"记忆服务未启用（type={memory_type}）")

        agent_id = getattr(self, "_agent_id", None)
        if not agent_id:
            raise RuntimeError("无法获取 agent_id，记忆源跳过")

        provider = self._lazy_get_memory_provider(memory_type, agent_id)
        if provider is None:
            raise RuntimeError("记忆 provider 初始化失败")

        try:
            # 随机问一个开放式问题，让记忆检索返回相关内容
            queries = [
                "最近有什么值得记住的事情？",
                "请回想一下之前聊过的有趣话题。",
                "用户之前表达了哪些想法或情感？",
            ]
            query = random.choice(queries)
            result = await provider.query_memory(query)
            if result and result.strip():
                return result.strip()
            raise RuntimeError("记忆查询返回空结果")
        except Exception as e:
            raise RuntimeError(f"记忆查询失败: {e}") from e

    def _lazy_get_memory_provider(self, memory_type: str, agent_id: str) -> Optional[Any]:
        """惰性缓存记忆 provider 实例（按 agent_id 隔离）。"""
        cache_key = f"{memory_type}_{agent_id}"
        if cache_key not in self._memory_providers:
            try:
                from core.utils.memory import create_instance as memory_create
                from core.utils.modules_initialize import initialize_modules

                modules = initialize_modules(
                    logger,
                    self._config,
                    init_memory=True,
                )
                mem_inst = modules.get("memory")
                if mem_inst is None:
                    return None
                mem_inst.init_memory(role_id=agent_id, llm=None)
                self._memory_providers[cache_key] = mem_inst
            except Exception as e:
                logger.warning("[%s] 记忆 provider 初始化失败: %s", TAG, e)
                return None
        return self._memory_providers.get(cache_key)

    async def _fetch_weather(self, location: Optional[str]) -> str:
        """异步获取天气数据（不依赖 threading.Event 的同步封装）。"""
        try:
            import httpx
            from plugins_func.functions.get_weather import (
                HEADERS,
                WEATHER_CODE_MAP,
                fetch_city_info,
                fetch_weather_page,
                parse_weather_info,
            )

            weather_config = self._config.get("plugins", {}).get("get_weather", {})
            api_host = weather_config.get("api_host", "mj7p3y7naa.re.qweatherapi.com")
            api_key = weather_config.get("api_key", "a861d0d5e7bf4ee1a83d9a9e4f96d4da")
            default_location = weather_config.get("default_location", "广州")

            target_location = location or default_location

            async with httpx.AsyncClient(timeout=httpx.Timeout(8.0, connect=3.0)) as client:
                city_info = await fetch_city_info(target_location, api_key, api_host)
            if not city_info:
                raise RuntimeError(f"无法获取城市信息: {target_location}")

            soup = await fetch_weather_page(city_info["fxLink"])
            if not soup:
                raise RuntimeError(f"天气页面请求失败: {target_location}")

            city_name, current_abstract, current_basic, temps_list = parse_weather_info(soup)

            lines = [f"您所在位置是：{city_name}，当前天气：{current_abstract}。"]
            if current_basic:
                params = [f"{k}：{v}" for k, v in current_basic.items() if v != "0"]
                if params:
                    lines.append("详细参数：" + "；".join(params) + "。")
            if temps_list:
                forecast = "未来几天预报："
                for date, weather, high, low in temps_list[:3]:
                    forecast += f"{date}{weather}，{low}到{high}度；"
                lines.append(forecast)
            return "\n".join(lines)
        except Exception as e:
            raise RuntimeError(f"天气获取失败: {e}") from e

    async def _fetch_chat(self) -> str:
        """纯闲聊模式：随机取一个开场白。"""
        return random.choice(_CHAT_OPENINGS)

    async def _call_llm(self, system_prompt: str, user_prompt: str) -> str:
        """异步调用 LLM（to_thread 包装，避免阻塞事件循环）。

        失败时自动重试 _LLM_MAX_RETRIES 次。
        """
        llm_provider = self._lazy_get_llm_provider()
        if llm_provider is None:
            raise RuntimeError("LLM provider 未初始化，回退到原始文本")

        last_error = None
        for attempt in range(1, _LLM_MAX_RETRIES + 1):
            try:
                result = await asyncio.wait_for(
                    asyncio.to_thread(
                        llm_provider.response_no_stream,
                        system_prompt,
                        user_prompt,
                    ),
                    timeout=_LLM_TIMEOUT,
                )
                if result and isinstance(result, str) and result.strip():
                    return result.strip()
                raise RuntimeError("LLM 返回空文本")
            except (asyncio.TimeoutError, Exception) as e:
                last_error = e
                logger.warning(
                    "[%s] LLM 调用第 %d 次失败: %s", TAG, attempt, e
                )
                if attempt < _LLM_MAX_RETRIES:
                    await asyncio.sleep(1.0 * attempt)  # 简单指数退避

        raise RuntimeError(f"LLM 调用失败（已重试 {_LLM_MAX_RETRIES} 次）: {last_error}")

    def _lazy_get_llm_provider(self) -> Optional[Any]:
        """惰性初始化 LLM provider。"""
        if self._llm_provider is not None:
            return self._llm_provider
        try:
            from core.utils.modules_initialize import initialize_modules

            modules = initialize_modules(
                logger,
                self._config,
                init_llm=True,
            )
            self._llm_provider = modules.get("llm")
            if self._llm_provider is None:
                logger.warning("[%s] LLM 模块初始化失败", TAG)
            else:
                logger.info("[%s] LLM provider 已初始化", TAG)
        except Exception as e:
            logger.warning("[%s] LLM 初始化异常: %s", TAG, e)
        return self._llm_provider

    async def _synthesize_tts(self, text: str, device_id: str, source: str) -> str:
        """使用 TTS 合成音频，写入 tmp/ 目录，返回 HTTP URL。

        复用 initialize_tts 的 fallback 链（默认挂 EdgeTTS），
        以 delete_audio_file=False 模式运行，保证文件持久化。
        """
        tts_provider = self._lazy_get_tts_provider()
        if tts_provider is None:
            raise RuntimeError("TTS provider 初始化失败")

        # 生成文件名
        ext = getattr(tts_provider, "audio_file_type", "mp3")
        filename = f"topic-{int(time.time() * 1000)}-{device_id[:8]}.{ext}"
        output_dir = self._config.get("tmp_dir", "tmp")
        os.makedirs(output_dir, exist_ok=True)
        output_path = os.path.join(output_dir, filename)

        try:
            await asyncio.to_thread(
                tts_provider.text_to_speak,
                text,
                output_path,
            )
        except Exception as e:
            # 清理可能的空文件
            if os.path.exists(output_path):
                try:
                    os.remove(output_path)
                except OSError:
                    pass
            raise RuntimeError(f"TTS 合成失败: {e}") from e

        if not os.path.exists(output_path) or os.path.getsize(output_path) == 0:
            raise RuntimeError("TTS 合成文件为空")

        # 构建 HTTP URL
        server_config = self._config.get("server", {})
        http_port = server_config.get("http_port", 8003)
        host_ip = server_config.get("ip", "0.0.0.0")
        # 用 127.0.0.1 以便设备在同一局域网访问
        base_url = f"http://{host_ip if host_ip != '0.0.0.0' else '127.0.0.1'}:{http_port}"
        audio_url = f"{base_url}/tmp/{filename}"
        logger.info(
            "[%s] TTS 合成成功: device=%s, source=%s, url=%s",
            TAG, device_id, source, audio_url,
        )
        return audio_url

    def _lazy_get_tts_provider(self) -> Optional[Any]:
        """惰性初始化 TTS provider（delete_audio_file=False）。"""
        if self._tts_provider is not None:
            return self._tts_provider
        try:
            from core.utils.modules_initialize import initialize_tts

            self._tts_provider = initialize_tts(self._config)
            if self._tts_provider is not None:
                # 强制 delete_audio_file=False，保证生成的音频文件持久化
                self._tts_provider.delete_audio_file = False
                logger.info("[%s] TTS provider 已初始化（delete_audio_file=False）", TAG)
            else:
                logger.warning("[%s] TTS provider 初始化返回 None", TAG)
        except Exception as e:
            logger.warning("[%s] TTS 初始化异常: %s", TAG, e)
        return self._tts_provider

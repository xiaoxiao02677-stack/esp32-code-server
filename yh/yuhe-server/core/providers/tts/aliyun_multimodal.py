import json
import os
import struct
import time
import uuid
import asyncio
import traceback
import queue

import websockets

from config.logger import setup_logging
from core.utils.tts import MarkdownCleaner
from core.utils.alibl_endpoint import build_ws_connect_options, resolve_ws_url
from core.providers.tts.base import TTSProviderBase
from core.providers.tts.dto.dto import SentenceType, ContentType, InterfaceType

TAG = __name__
logger = setup_logging()

# 多模态交互套件（multimodal-dialog）固定取值
_TASK_GROUP = "aigc"
_TASK = "multimodal-generation"
_FUNCTION = "generation"
_DEFAULT_MODEL = "multimodal-dialog"

# 单段 RequestToRespond 从发出到 RespondingEnded 的兜底等待（长文本合成可能较慢）
_DEFAULT_RESPOND_TIMEOUT = 60

# duplex 上行 PCM 采样率：与 connection._decode_opus_packet 的
# opuslib_next.Decoder(16000, 1) 对齐，固定 16k
_UPSTREAM_SAMPLE_RATE = 16000


def _pcm_to_wav(pcm: bytes, sample_rate: int, channels: int = 1, sample_width: int = 2) -> bytes:
    """裸 PCM(16bit) 加 44 字节 WAV 头，供试听/文件场景直接播放。"""
    data_len = len(pcm)
    header = struct.pack(
        "<4sI4s4sIHHIIHH4sI",
        b"RIFF", 36 + data_len, b"WAVE",
        b"fmt ", 16,
        1,  # PCM
        channels, sample_rate,
        sample_rate * channels * sample_width,
        channels * sample_width,
        sample_width * 8,
        b"data", data_len,
    )
    return header + pcm


async def _handle_duplex_asr(conn, asr_text: str):
    """duplex 一条龙：服务端 ASR 结果落地。
    1) 设备字幕（stt 消息）；
    2) 本地意图识别（音量/退出/唤醒词响应等设备控制），命中则本地处理；
    3) 未命中意图 → 纯透传给百炼应用（它自己会 LLM+TTS），本地不进 LLM。"""
    from core.handle.sendAudioHandle import send_stt_message, send_tts_message
    from core.handle.intentHandler import handle_user_intent

    # 回声防护：与最近播报句相似即丢弃（duplex 播报期上行静音，这里是兜底）
    from core.utils.echo_guard import check_echo
    if check_echo(conn, asr_text):
        return

    await send_stt_message(conn, asr_text)

    # 复位打断标志：本地链路里它由 startToChat 尾部复位，duplex 旁路了
    # startToChat，不复位的话一次打断后所有音频都会被 client_abort 丢弃
    conn.client_abort = False

    # 本地意图（音量控制等）命中即本地响应，百炼不再收到这段语音的回复
    # （语音已上行，但 duplex 服务端打断后服务端会自己处理——本地命中后
    #  发 RequestToSpeak 抢占，让服务端停止当前轮回复）
    intent_handled = False
    try:
        intent_handled = await handle_user_intent(conn, asr_text)
    except Exception as e:
        logger.bind(tag=TAG).warning(f"duplex 意图识别异常: {e}")

    if intent_handled:
        tts = conn.tts
        if tts and hasattr(tts, "ws") and tts.ws and tts.dialog_id:
            try:
                await tts.ws.send(json.dumps(
                    tts._continue_task(
                        conn.session_id,
                        {"directive": "RequestToSpeak", "dialog_id": tts.dialog_id},
                    )
                ))
            except Exception:
                pass


class TTSProvider(TTSProviderBase):
    """阿里云百炼多模态交互套件（multimodal-dialog）。

    两种模式（config.full_duplex 切换）：
    - false（默认）push2talk TTS-only：ASR/LLM/VAD/打断走本地既有链路，
      文本经 RequestToRespond(type=transcript) 直转语音下发。
    - true duplex 一条龙：设备音频直推 dashscope（持续上行 + 静音填充），
      ASR+LLM+TTS 全在百炼应用内完成，本地不配 LLM；SpeechContent 出字幕，
      RespondingStarted/Ended 驱动设备音频流，语音打断由服务端 VAD 完成。
    协议要点：Start 后必须等 DialogStateChanged(Listening) 才能发指令/音频；
    duplex 任意状态 20s 无上行即断（静音帧保活）+ 25s 心跳防 ResponseTimeout。
    """

    # ttsVolume/ttsRate/ttsPitch 为 Java 侧注入的音色级百分比参数，
    # 映射到套件 downstream 的 volume(0-100)/speech_rate(50-200)/pitch_rate(50-200)
    TTS_PARAM_CONFIG = [
        ("ttsVolume", "volume", 0, 100, 50, int),
        ("ttsRate", "speech_rate", 50, 200, 100, int),
        ("ttsPitch", "pitch_rate", 50, 200, 100, int),
    ]

    def __init__(self, config, delete_audio_file):
        super().__init__(config, delete_audio_file)

        self.interface_type = InterfaceType.DUAL_STREAM
        self.audio_file_type = "wav"

        self.api_key = config.get("api_key")
        if not self.api_key:
            raise ValueError("api_key is required for Aliyun Multimodal TTS")
        self.workspace_id = config.get("workspace_id")
        if not self.workspace_id:
            raise ValueError("workspace_id is required for Aliyun Multimodal TTS")
        self.app_id = config.get("app_id")
        if not self.app_id:
            raise ValueError("app_id is required for Aliyun Multimodal TTS")

        self.ws_url = resolve_ws_url(config.get("ws_url"))
        self.ws_connect_options = build_ws_connect_options(self.tts_timeout)
        self.model = config.get("model", _DEFAULT_MODEL)
        self.respond_timeout = float(config.get("respond_timeout", _DEFAULT_RESPOND_TIMEOUT))

        self.voice = config.get("voice", "longxiaochun_v3")
        if config.get("private_voice"):
            self.voice = config.get("private_voice")

        # 下行合成参数（0/50-200 各自合法，判断时用 is not None）
        volume = config.get("volume", 50)
        self.volume = int(volume) if volume is not None else None
        speech_rate = config.get("speech_rate", 100)
        self.speech_rate = int(speech_rate) if speech_rate is not None else None
        pitch_rate = config.get("pitch_rate", 100)
        self.pitch_rate = int(pitch_rate) if pitch_rate is not None else None
        self._apply_percentage_params(config)

        # 试听/文件合成的采样率（设备流式路径用 conn.sample_rate）
        self.sample_rate = int(config.get("sample_rate", 16000))

        self.header = {"Authorization": f"Bearer {self.api_key}"}

        # 会话状态（流式路径）
        self.ws = None
        self._monitor_task = None
        self.activate_session = False
        self.dialog_id = None
        self._listening_event = None
        self._responding_ended_event = None
        self._stopped_event = None
        self._session_error = None
        self._segment_text = None
        # duplex 会话互斥锁：多入口（tts 线程 FIRST 确认/上行泵重建/音频
        # 上行节流重建）并发 start_session 会竞态（见 start_session docstring）
        self._session_lock = asyncio.Lock()
        # 百炼控制台提示词占位符变量名（如 ${prompt} 中的 prompt），
        # 人设经 biz_params.user_prompt_params[该变量名] 注入，连接级参数
        self.prompt_variable = str(config.get("prompt_variable", "prompt"))

        # ---------------- duplex 全双工一条龙 ----------------
        # full_duplex=True：设备音频直推 dashscope，ASR+LLM+TTS 全在百炼应用内完成，
        # 本地不再走 LLM 链（测试端"聊天一条龙"模式）。
        # full_duplex=False（默认）：仅消费 TTS 能力（push2talk 文本转语音）。
        self.full_duplex = str(config.get("full_duplex", "false")).lower() in ("1", "true", "yes", "on")
        # duplex 模式下设备 20s 不上行音频即报错，须长驻会话 + 静音填充
        self._upstream_task = None          # 音频上行任务（含心跳）
        self._upstream_buffer = asyncio.Queue(maxsize=200)  # PCM 帧缓冲（100ms 合并后上行）
        self._upstream_silence = None        # 静音帧（按 conn.sample_rate 初始化）
        self._resync_dialog = False          # 服务端语音打断后需要新 sentence 轮次
        self._responding_active = False      # 服务端 Responding 进行中（音频已到设备）
        self._duplex_asr_partial = ""        # 当前句服务端 ASR 累积（SpeechEnded 取全量）
        # 重建去抖：并发触发的 _rebuild_duplex_session 只放一个进临界区，
        # 后续触发者确认会话已被别人重建后直接返回
        self._rebuild_task = None
        self._responding_text = ""           # 当前轮 LLM 增量文本累积（上报用）

    # ------------------------------------------------------------------
    # 消息构造
    # ------------------------------------------------------------------

    def _build_start_message(self, task_id, sample_rate, user_id):
        downstream = {
            "voice": self.voice,
            "sample_rate": sample_rate,
            "audio_format": "pcm",
        }
        if self.volume is not None:
            downstream["volume"] = self.volume
        if self.speech_rate is not None:
            downstream["speech_rate"] = self.speech_rate
        if self.pitch_rate is not None:
            downstream["pitch_rate"] = self.pitch_rate
        if self.full_duplex:
            # 一条龙模式：需要 ASR 中间结果做设备字幕
            downstream["intermediate_text"] = "transcript"
        upstream = {"type": "AudioOnly", "mode": "push2talk"}
        if self.full_duplex:
            # duplex：持续上行音频，服务端 VAD + 语音打断。
            # 上行 PCM 采样率固定 16k（connection._decode_opus_packet 用
            # Decoder(16000,1) 解码设备 opus），绝不能用 conn.sample_rate
            # （那是下行输出采样率，本环境 24k——声明错会音频错位 ASR 全废）
            upstream["mode"] = "duplex"
            upstream["audio_format"] = "pcm"
            upstream["sample_rate"] = _UPSTREAM_SAMPLE_RATE
        parameters = {
            "upstream": upstream,
            "downstream": downstream,
            "client_info": {"user_id": user_id[:36]},
        }
        # 智能体人设注入控制台提示词占位符（如 ${prompt}）：
        # biz_params.user_prompt_params 为连接级参数，KV 键须与控制台
        # 自定义变量名一致。取 conn.config["prompt"]（Java 下发的智能体
        # 原始 systemPrompt），未下发时不下发该块（百炼应用用控制台默认提示词）
        persona = self._persona_text()
        if persona:
            parameters["biz_params"] = {
                "user_prompt_params": {self.prompt_variable: persona}
            }
        return {
            "header": {"action": "run-task", "task_id": task_id, "streaming": "duplex"},
            "payload": {
                "task_group": _TASK_GROUP,
                "task": _TASK,
                "function": _FUNCTION,
                "model": self.model,
                "input": {
                    "directive": "Start",
                    "workspace_id": self.workspace_id,
                    "app_id": self.app_id,
                },
                "parameters": parameters,
            },
        }

    @staticmethod
    def _continue_task(task_id, payload_input):
        return {
            "header": {"action": "continue-task", "task_id": task_id, "streaming": "duplex"},
            "payload": {"input": payload_input},
        }

    @staticmethod
    def _finish_task(task_id, payload_input):
        return {
            "header": {"action": "finish-task", "task_id": task_id, "streaming": "duplex"},
            "payload": {"input": payload_input},
        }

    def _client_user_id(self):
        # 智能体维度优先（Java getAgentModels 下发 agent_id）：百炼侧会话/
        # 上下文按智能体归并，同一智能体多设备共享人设语境；未下发（旧版
        # Java / need_bind / 试听无 conn）时逐级兜底到设备 MAC，与历史行为
        # 完全兼容
        agent_id = getattr(self.conn, "agent_id", None) if self.conn is not None else None
        if agent_id:
            return str(agent_id)[:36]
        if self.conn is not None:
            device_id = self.conn.headers.get("device-id") if self.conn.headers else None
            return (device_id or "yuhe-device")[:36]
        return "tts-preview"

    def _persona_text(self):
        """传给百炼控制台提示词占位符（如 ${prompt}）的智能体人设。

        取 conn.config["prompt"]（Java 下发的智能体原始 systemPrompt）：
        duplex 会话建立阶段增强提示词尚未生成（且 duplex 链路本地 LLM 已
        旁路，增强/记忆注入不参与），统一用原始人设。连接缺失或人设未
        下发（试听/本地开发）返回 None——不发送 biz_params 块，百炼应用
        沿用控制台默认提示词。
        """
        if self.conn is None:
            return None
        persona = (self.conn.config or {}).get("prompt")
        if not persona or not str(persona).strip():
            return None
        return str(persona)

    # ------------------------------------------------------------------
    # 流式路径（DUAL_STREAM）
    # ------------------------------------------------------------------

    def tts_text_priority_thread(self):
        """流式TTS文本处理线程：分段缓冲 → 标点切段 → 每段一次 RequestToRespond。"""
        while not self.conn.stop_event.is_set():
            try:
                message = self.tts_text_queue.get(timeout=1)

                if self.conn.client_abort:
                    if self.full_duplex:
                        # duplex 长驻会话：打断只停当前轮（等价 RequestToSpeak），
                        # 不 Stop 会话。音频队列由 clear_queues 清空。
                        try:
                            asyncio.run_coroutine_threadsafe(
                                self._abort_duplex_turn(),
                                loop=self.conn.loop,
                            )
                        except Exception as e:
                            logger.bind(tag=TAG).error(f"duplex 打断失败: {str(e)}")
                    else:
                        try:
                            logger.bind(tag=TAG).info("收到打断信息，终止TTS文本处理线程")
                            asyncio.run_coroutine_threadsafe(
                                self.finish_session(self.conn.sentence_id),
                                loop=self.conn.loop,
                            )
                        except Exception as e:
                            logger.bind(tag=TAG).error(f"取消TTS会话失败: {str(e)}")
                    continue

                # 过滤旧消息：检查sentence_id是否匹配
                if message.sentence_id != self.conn.sentence_id:
                    continue

                logger.bind(tag=TAG).debug(
                    f"收到TTS任务｜{message.sentence_type.name} ｜ {message.content_type.name} | 会话ID: {message.sentence_id}"
                )

                if message.sentence_type == SentenceType.FIRST:
                    self.reset_stream_state()
                    self.current_sentence_id = message.sentence_id
                    self.tts_text_buff = []
                    self.processed_chars = 0
                    self.is_first_sentence = True
                    try:
                        if not getattr(self.conn, "sentence_id", None):
                            self.conn.sentence_id = uuid.uuid4().hex
                        if self.full_duplex:
                            # duplex 长驻会话：不重建，仅确保在线（断线则重连）
                            if not (self.ws and self.activate_session):
                                future = asyncio.run_coroutine_threadsafe(
                                    self.start_duplex_session(),
                                    loop=self.conn.loop,
                                )
                                future.result(timeout=self.tts_timeout + 20)
                        else:
                            future = asyncio.run_coroutine_threadsafe(
                                self.start_session(self.conn.sentence_id),
                                loop=self.conn.loop,
                            )
                            future.result(timeout=self.tts_timeout + 20)
                        self.before_stop_play_files.clear()
                    except Exception as e:
                        logger.bind(tag=TAG).error(f"启动TTS会话失败: {str(e)}")
                        continue

                elif ContentType.TEXT == message.content_type:
                    if message.content_detail:
                        self.tts_text_buff.append(message.content_detail)
                        segment_text = self._get_segment_text()
                        if segment_text:
                            self._speak_stream_segment(segment_text)

                elif ContentType.FILE == message.content_type:
                    logger.bind(tag=TAG).info(
                        f"添加音频文件到待播放列表: {message.content_file}"
                    )
                    if message.content_file and os.path.exists(message.content_file):
                        if self.full_duplex:
                            # duplex 长驻会话永不 Stop，靠 Stopped 事件 flush 的
                            # before_stop_play_files 通道永远不会触发（音乐帧
                            # 全滞留内存，设备只听到引导语——2026-10-23 实录）。
                            # 改为独立句子直发：FIRST → 转码帧流 MIDDLE → LAST。
                            self._play_local_file_duplex(
                                message.content_file, message.content_detail
                            )
                        else:
                            self._process_audio_file_stream(
                                message.content_file,
                                callback=lambda audio_data: self.handle_audio_file(
                                    audio_data, message.content_detail
                                ),
                            )

                if message.sentence_type == SentenceType.LAST:
                    # 发送剩余无标点尾巴后结束会话
                    full_text = "".join(self.tts_text_buff)
                    remaining = full_text[self.processed_chars:]
                    if remaining:
                        segment_text = self._strip_for_tts(remaining)
                        if segment_text:
                            self._speak_stream_segment(segment_text)
                        self.processed_chars += len(full_text)
                    if self.full_duplex:
                        # duplex 长驻会话：不 Stop。音频 LAST 由 monitor 的
                        # RespondingEnded/Listening 状态机推（本地文本播报的
                        # LAST 已在上面 _speak_stream_segment 等待中由
                        # RespondingEnded 推送过，这里不重复）
                        continue
                    try:
                        future = asyncio.run_coroutine_threadsafe(
                            self.finish_session(self.conn.sentence_id),
                            loop=self.conn.loop,
                        )
                        future.result(timeout=self.tts_timeout + 20)
                    except Exception as e:
                        logger.bind(tag=TAG).error(f"结束TTS会话失败: {str(e)}")
                        continue

            except queue.Empty:
                continue
            except Exception as e:
                logger.bind(tag=TAG).error(
                    f"处理TTS文本失败: {str(e)}, 类型: {type(e).__name__}, 堆栈: {traceback.format_exc()}"
                )
                continue

    def _strip_for_tts(self, text):
        from core.utils import textUtils

        return textUtils.get_string_no_punctuation_or_emoji(text)

    def _speak_stream_segment(self, segment_text):
        """把一个标点段发送到多模态服务合成（阻塞直到本段音频下发完成）。"""
        try:
            future = asyncio.run_coroutine_threadsafe(
                self._speak_stream_segment_async(segment_text),
                loop=self.conn.loop,
            )
            future.result(timeout=self.respond_timeout + self.tts_timeout + 20)
        except Exception as e:
            logger.bind(tag=TAG).error(f"发送TTS文本失败: {str(e)}")

    async def _speak_stream_segment_async(self, segment_text):
        filtered_text = MarkdownCleaner.clean_markdown(segment_text)
        if not filtered_text:
            return

        # 连接被服务端超时断开时重建（Start→Listening 全流程）
        if self.ws is None or not self.activate_session:
            if self.full_duplex:
                await self.start_duplex_session()
            else:
                logger.bind(tag=TAG).info("连接不可用，重建多模态会话...")
                await self.start_session(self.conn.sentence_id)

        confirmed_texts, self._pending_prefix = self._match_stream_text(filtered_text)
        for txt in confirmed_texts:
            if not txt or not self.ws:
                continue
            # 字幕显示用还原后的原文
            self._segment_text = self._restore_original_text(txt)
            # duplex 下记录本次本地合成的文本（SpeechContent prompt 回声比对）
            if self.full_duplex:
                self._last_local_prompt = txt
            if not self.full_duplex:
                # duplex 下 FIRST 由 monitor 的 RespondingStarted 推送
                pass
            self._responding_ended_event = asyncio.Event()
            # 本地合成 transcript 在途标记：此轮 Thinking 空响应由段超时
            # 逻辑兜底，不触发语音空响应恢复
            self._local_transcript_inflight = True
            respond_msg = self._continue_task(
                self.conn.sentence_id,
                {
                    "directive": "RequestToRespond",
                    "dialog_id": self.dialog_id,
                    "type": "transcript",
                    "text": txt,
                },
            )
            await self.ws.send(json.dumps(respond_msg))
            try:
                await asyncio.wait_for(
                    self._responding_ended_event.wait(), timeout=self.respond_timeout
                )
            except asyncio.TimeoutError:
                logger.bind(tag=TAG).warning(f"等待段音频超时: {txt[:32]}")
            finally:
                self._responding_ended_event = None
                self._local_transcript_inflight = False
            if self._session_error:
                raise RuntimeError(f"多模态合成失败: {self._session_error}")
            # 让服务端回到 Listening，才能继续下一段
            # （duplex 下同样需要：服务端从 Responding 回 Listening 后才能接下一段）
            if self.ws and self.dialog_id:
                local_end = self._continue_task(
                    self.conn.sentence_id,
                    {"directive": "LocalRespondingEnded", "dialog_id": self.dialog_id},
                )
                await self.ws.send(json.dumps(local_end))

    async def start_session(self, session_id):
        """启动多模态会话：建连 → Start → 等 DialogStateChanged(Listening)。
        duplex 下多个入口（tts 线程/上行泵/节流重建）可能并发调用，
        必须串行化——曾因并发重入：A 协程 finally 清 _listening_event
        时 B 协程正 wait() → 'NoneType' object has no attribute 'wait'，
        三次重试全炸同一错误，duplex 会话死亡，语音链路静默回退本地
        ASR+LLM（2026-10-23 18:21 实录）。"""
        async with self._session_lock:
            logger.bind(tag=TAG).debug(f"开始会话～～{session_id}")
            listening_event = asyncio.Event()
            self._listening_event = listening_event
            try:
                # 拆旧会话必须走 close()（关 ws + 停 monitor + 清 activate_
                # session）。上一版只查 activate_session：被并发 rebuild
                # 置 False 后跳过清理，_ensure_connection 的 if self.ws:
                # return 复用跑过任务的旧连接重发 run-task → 百炼按协议
                # 拒绝 Invalid action → task-failed → 泵 1007 → 再触发
                # rebuild → 死循环（2026-10-23 18:39 实录 11 连）。
                if self.activate_session or self.ws:
                    await self.close()

                self.activate_session = True
                self.dialog_id = None
                self._session_error = None
                self._segment_text = None

                await self._ensure_connection()

                if self._monitor_task is None or self._monitor_task.done():
                    self._monitor_task = asyncio.create_task(self._start_monitor_tts_response())

                start_msg = self._build_start_message(
                    session_id, self.conn.sample_rate, self._client_user_id()
                )
                await self.ws.send(json.dumps(start_msg))
                # 排障可观测：Start 帧关键参数（user_id 维度 + 人设注入与否），
                # 人设全文可能很长，只记前 60 字
                _bp = start_msg["payload"]["parameters"].get("biz_params")
                _persona_head = ""
                if _bp:
                    _v = _bp.get("user_prompt_params", {}).get(self.prompt_variable, "")
                    _persona_head = f", persona[:60]={str(_v)[:60]!r}"
                logger.bind(tag=TAG).info(
                    f"duplex Start 已发送: user_id={start_msg['payload']['parameters']['client_info']['user_id']}"
                    f", biz_params={'有' if _bp else '无'}{_persona_head}"
                )

                # 协议红线：必须等 Listening 才能发 RequestToRespond
                await asyncio.wait_for(listening_event.wait(), timeout=self.tts_timeout + 10)
                if self._session_error:
                    # task-failed 在等待期间已到（如 run-task 被拒）：
                    # _notify_waiters 会 set 事件伪装成功，这里显式判死
                    raise RuntimeError(f"会话启动被拒: {self._session_error}")
            except Exception as e:
                logger.bind(tag=TAG).error(f"启动会话失败: {str(e)}")
                # 只在本次会话事件未被消费时清理；若 Listening 已到
                # （事件已 set 且被其他逻辑使用）则保留会话
                if self._listening_event is listening_event and not listening_event.is_set():
                    await self._close_ws_quietly()
                    self.activate_session = False
                raise
            finally:
                if self._listening_event is listening_event:
                    self._listening_event = None

    async def finish_session(self, session_id):
        """结束多模态会话：Stop → 等 Stopped（monitor 收到后推音频 LAST）。
        duplex 一条龙模式下会话长驻，本方法只在连接关闭时调用。"""
        logger.bind(tag=TAG).debug(f"关闭会话～～{session_id}")
        try:
            if not (self.ws and self.activate_session):
                # 连接已断：monitor 无法收尾，这里保底推 LAST，避免设备一直等
                self._process_before_stop_play_files()
                self.activate_session = False
                return
            self._stopped_event = asyncio.Event()
            stop_msg = self._finish_task(
                session_id,
                {"directive": "Stop", "dialog_id": self.dialog_id},
            )
            await self.ws.send(json.dumps(stop_msg))
            try:
                await asyncio.wait_for(self._stopped_event.wait(), timeout=5)
            except asyncio.TimeoutError:
                logger.bind(tag=TAG).warning("等待 Stopped 超时，直接收尾")
                self._process_before_stop_play_files()
                self.activate_session = False
                await self.close()
        except Exception as e:
            logger.bind(tag=TAG).error(f"关闭会话失败: {str(e)}")
            self._process_before_stop_play_files()
            self.activate_session = False
            await self.close()
            raise
        finally:
            self._stopped_event = None

    # ------------------------------------------------------------------
    # duplex 全双工一条龙（full_duplex=True 时启用）
    # ------------------------------------------------------------------

    async def start_duplex_session(self):
        """建立长驻 duplex 会话并启动上行任务（设备接入时调用一次）。
        dashscope 偶发握手超时（实测一天多次），失败必须重试——否则设备
        音频上行全部丢弃且无任何日志（排障盲区，2026-10-23 16:45 实录）。"""
        if not self.full_duplex:
            return
        if self.activate_session and self.ws:
            return
        last_err = None
        for attempt in range(3):
            try:
                # duplex 会话与设备连接同生命周期：复用 session_id 线程安全
                await self.start_session(self.conn.session_id)
                self._start_upstream_task()
                return
            except Exception as e:
                last_err = e
                logger.bind(tag=TAG).warning(
                    f"duplex 会话建立失败(第{attempt + 1}次): {e}"
                )
                await asyncio.sleep(2)
        logger.bind(tag=TAG).error(f"duplex 会话建立最终失败: {last_err}")

    def _start_upstream_task(self):
        if self._upstream_task is None or self._upstream_task.done():
            self._upstream_task = asyncio.create_task(self._upstream_loop())

    async def receive_upstream_audio(self, pcm_frame: bytes):
        """设备 PCM 帧入口（connection 解码后分流调用）。
        无 AEC 设备播报期回声会被百炼服务端 VAD 当人声（自打断循环），
        用静音帧替代真实上行；duplex 20s 必须上行约束由静音帧兜底。
        AEC 板（conn.client_aec）回声已消除，豁免静音保留语音打断。"""
        if not self.full_duplex:
            return
        if not (self.ws and self.activate_session):
            # 会话未就绪（建立失败/被断开）：丢弃真实语音帧，延迟触发重建
            # （start_duplex_session 内部含 3 次重试；节流防每帧都打日志）
            now = time.monotonic()
            if now - getattr(self, "_last_rebuild_attempt", 0) > 10:
                self._last_rebuild_attempt = now
                logger.bind(tag=TAG).warning(
                    "duplex 会话未就绪，音频被丢弃，触发重建"
                )
                asyncio.ensure_future(self._rebuild_duplex_session())
            return
        if not getattr(self.conn, "client_aec", False):
            # 播报期（含思考期）静音；播报结束后再留 1.5s 尾部回声窗
            speaking = self.conn.client_is_speaking
            if not speaking:
                ended_ms = getattr(self.conn, "client_speak_ended_ms", 0) or 0
                speaking = (time.time() * 1000 - ended_ms) < 1500
            if speaking:
                pcm_frame = self._silence_frame(len(pcm_frame))
                self._stat_upstream_muted = getattr(self, "_stat_upstream_muted", 0) + 1
        try:
            self._upstream_buffer.put_nowait(pcm_frame)
        except asyncio.QueueFull:
            # 上行阻塞（网络抖动）：丢弃最旧帧保实时性
            try:
                self._upstream_buffer.get_nowait()
                self._upstream_buffer.put_nowait(pcm_frame)
            except (asyncio.QueueEmpty, asyncio.QueueFull):
                pass

    def _silence_frame(self, size: int) -> bytes:
        if self._upstream_silence is None or len(self._upstream_silence) != size:
            self._upstream_silence = b"\x00" * size
        return self._upstream_silence

    async def _upstream_loop(self):
        """上行泵：每 100ms 合并缓冲 PCM 直发 dashscope；空闲发静音帧 + 周期心跳。
        duplex 模式要求任何状态 20s 内有上行，心跳防 ResponseTimeout（60s 无下行断连）。"""
        send_interval = 0.1
        silence = None
        last_heartbeat = 0.0
        stat_frames = 0        # 调试：实际语音帧计数
        stat_sent = 0          # 调试：已发送字节数
        stat_t0 = time.monotonic()
        try:
            while self.activate_session and not self.conn.stop_event.is_set():
                if not (self.ws and self.activate_session):
                    break
                chunks = []
                deadline = time.monotonic() + send_interval
                while time.monotonic() < deadline:
                    try:
                        remaining = max(0.0, deadline - time.monotonic())
                        item = await asyncio.wait_for(
                            self._upstream_buffer.get(), timeout=remaining
                        )
                        chunks.append(item)
                    except asyncio.TimeoutError:
                        break
                payload = b"".join(chunks)
                if not payload:
                    if silence is None:
                        silence = self._silence_frame(
                            int(_UPSTREAM_SAMPLE_RATE * 2 * send_interval)
                        )
                    payload = silence
                else:
                    stat_frames += len(chunks)
                stat_sent += len(payload)
                # 每 10s 打一次上行统计（debug 级，排障时开启）
                if time.monotonic() - stat_t0 >= 10:
                    muted = getattr(self, "_stat_upstream_muted", 0)
                    logger.bind(tag=TAG).debug(
                        f"duplex 上行统计: 语音帧={stat_frames} 已发={stat_sent}B "
                        f"静音替换={muted}"
                    )
                    stat_frames = stat_sent = 0
                    self._stat_upstream_muted = 0
                    stat_t0 = time.monotonic()
                try:
                    await self.ws.send(payload)
                except Exception as e:
                    logger.bind(tag=TAG).warning(f"上行音频发送失败，尝试重建: {e}")
                    await self._rebuild_duplex_session()
                    continue
                # 心跳：25s 一次（服务端 60s 无下行即断，留足余量）
                now = time.monotonic()
                if now - last_heartbeat >= 25:
                    last_heartbeat = now
                    try:
                        await self.ws.send(json.dumps(
                            self._continue_task(
                                self.conn.session_id,
                                {"directive": "HeartBeat", "dialog_id": self.dialog_id},
                            )
                        ))
                    except Exception:
                        pass
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.bind(tag=TAG).error(f"上行循环异常退出: {e}\n{traceback.format_exc()}")

    async def _rebuild_duplex_session(self):
        """duplex 会话断开后重建（新 dialog_id 新上下文——继承旧 id 会被
        百炼拒绝）。停旧上行泵再重建，避免旧泵攥着死 ws 反复 send 失败。

        约束（2026-10-23 18:39 死循环实录）：
        1. 拆毁动作必须拿 _session_lock——否则与并发的 start_session 交错：
           A 拿锁 connect 让出期间，B 在锁外把 activate_session 抹 False、
           A 回来后建连成功但泵已不认（activate_session=False）→ 僵尸会话。
        2. 上行泵调用本方法时禁止 task.cancel() 自己——cancel 会打断本协程
           自身的清理（半关 ws 残留），下次 _ensure_connection 复用死连接
           发 run-task 被拒。泵的退出交给循环条件（activate_session=False）。
        3. 并发触发单飞：多个等待者只让一个执行重建，其余等它完成后
           检查会话是否已就绪，是则直接返回。"""
        # 单飞：已有重建在途，直接返回（10s 节流的接收路径/泵失败路径
        # 会再次触发，天然形成重试）
        if self._rebuild_task and not self._rebuild_task.done():
            return

        async def _do_rebuild():
            try:
                # 设备已断开：不再重建（ws 泄漏等百炼超时自清）
                if self.conn.stop_event.is_set():
                    return
                # 拆毁在独立任务里执行：泵内联触发时 cancel 的不是自己
                # （旧版泵 cancel 自身会让清理半途夭折，半关 ws 残留）
                if self._upstream_task and not self._upstream_task.done():
                    self._upstream_task.cancel()
                self._upstream_task = None
                # 拆毁段持锁：与 start_session 严格串行，杜绝"连接活着但
                # 会话已死"的僵尸态被 _ensure_connection 复用
                async with self._session_lock:
                    # 等锁期间会话已被其他入口（hello/tts线程）重建成功：
                    # 直接采用，不拆了重来（hello 与设备音频同秒到达的
                    # 常态竞态——旧版无条件拆毁造成连接churn）
                    if (
                        self.ws
                        and self.activate_session
                        and self._monitor_task
                        and not self._monitor_task.done()
                    ):
                        return
                    await self._close_ws_quietly()
                    self.activate_session = False
                    self.dialog_id = None
                # 重建段锁外：start_session 内部拿锁（asyncio.Lock 不可重入）
                await self.start_duplex_session()
            except Exception as e:
                logger.bind(tag=TAG).error(f"重建 duplex 会话失败: {e}")
            finally:
                if self._rebuild_task is asyncio.current_task():
                    self._rebuild_task = None

        self._rebuild_task = asyncio.create_task(_do_rebuild())

    async def stop_duplex_session(self):
        """设备断开时收尾。"""
        if not self.full_duplex:
            return
        if self._upstream_task and not self._upstream_task.done():
            self._upstream_task.cancel()
        self._upstream_task = None
        try:
            await self.finish_session(self.conn.session_id)
        except Exception:
            pass

    async def _abort_duplex_turn(self):
        """duplex 打断当前轮：告知服务端本地播放已停（LocalRespondingEnded），
        语音流照常上行——用户下一句话会开启新轮回复。"""
        try:
            if self.ws and self.activate_session and self.dialog_id:
                await self.ws.send(json.dumps(
                    self._continue_task(
                        self.conn.session_id,
                        {"directive": "LocalRespondingEnded", "dialog_id": self.dialog_id},
                    )
                ))
        except Exception as e:
            logger.bind(tag=TAG).warning(f"duplex 打断通知失败: {e}")

    def _emit_first_sentence(self, text=None):
        """服务端开始 Responding：以设备协议推送 FIRST（sentence_start）。
        text 来自 RespondingContent 增量（intermediate_text 未配 dialog 时为 None）。
        duplex 下设备状态机仅 speaking 态收音频帧：上文 LAST 已让设备回
        listening（本地兜底 LLM 多段合成——段间 RespondingEnded 每段推 LAST，
        第二段起设备全在 listening 丢帧，2026-10-23 20:57 实录 4KB 丢弃）。
        统一置标志让播放线程在本 FIRST 前补 tts start（幂等：设备已
        speaking 时再收 start 仅重置计时，无害）。"""
        self._need_tts_start_before_next_first = True
        self.tts_audio_queue.put(
            (
                SentenceType.FIRST,
                [],
                text,
                getattr(self, "current_sentence_id", None),
            )
        )

    def _play_local_file_duplex(self, file_path, text=None):
        """duplex 下本地音频文件（音乐）作为独立句子直发设备：
        FIRST → 转码 opus 帧流 MIDDLE → LAST。
        转码同步执行（本就在 tts_priority 线程），帧经队列由播放线程按
        sendAudioMessage 流控节奏下发。"""

        def _frame_cb(opus_frame):
            self.tts_audio_queue.put(
                (SentenceType.MIDDLE, opus_frame, None, getattr(self, "current_sentence_id", None))
            )

        logger.bind(tag=TAG).info(f"duplex 本地文件直发: {file_path}")
        # 设备状态机协议：音频帧仅在 speaking 态入队（固件 application.cc
        # OnIncomingAudio 只认 kDeviceStateSpeaking），进 speaking 只由
        # tts start 触发。引导语轮 LAST 已发 tts stop 让设备回 listening，
        # 音乐作为独立句子到达时设备在 listening——帧全部被静默丢弃（真机
        # 2026-10-23 20:05 实录：只听到"请欣赏歌曲"没有音乐）。
        # tts start 不能在这里直接发（会抢跑到引导语 tts stop 之前——
        # 那个 stop 由播放线程在音频排空后才发，晚 1~2s，先发的 start
        # 会被它覆盖回 listening，20:27 实录）。置标志由播放线程在处理
        # 本音乐 FIRST 时按队列顺序补发，保证 wire 顺序：
        # 引导语帧 → tts stop → tts start → sentence_start → 音乐帧。
        self._need_tts_start_before_next_first = True
        # FIRST 带文件名作字幕（send_tts_message 对 text=None 的
        # sentence_start 直接吞掉，设备屏幕也该有歌名显示）
        if not text:
            text = f"♪ {os.path.splitext(os.path.basename(file_path))[0]}"
        self.tts_audio_queue.put(
            (
                SentenceType.FIRST,
                [],
                text,
                getattr(self, "current_sentence_id", None),
            )
        )
        try:
            self.audio_to_opus_data_stream(file_path, callback=_frame_cb)
        except Exception as e:
            logger.bind(tag=TAG).error(
                f"duplex 本地文件转码失败: {file_path}, {e}"
            )
        self._emit_last_sentence()

    def _emit_last_sentence(self):
        """服务端 Responding 结束：推 LAST 走设备 stop 流程。"""
        self.tts_audio_queue.put(
            (
                SentenceType.LAST,
                [],
                None,
                getattr(self, "current_sentence_id", None),
            )
        )

    async def _ensure_connection(self):
        try:
            if self.ws:
                return self.ws
            logger.bind(tag=TAG).debug("开始建立新连接...")
            await self._cancel_monitor_task()
            self.ws = await websockets.connect(
                self.ws_url,
                additional_headers=self.header,
                ping_interval=30,
                ping_timeout=10,
                close_timeout=10,
                **self.ws_connect_options,
            )
            logger.bind(tag=TAG).debug("WebSocket连接建立成功")
            return self.ws
        except Exception as e:
            logger.bind(tag=TAG).error(f"建立连接失败: {str(e)}")
            self.ws = None
            raise

    async def close(self):
        """清理资源"""
        await super().close()
        self.activate_session = False
        self.dialog_id = None
        await self._cancel_monitor_task()
        if self.ws:
            try:
                await self.ws.close()
            except Exception:
                pass
            self.ws = None

    async def _cancel_monitor_task(self):
        if self._monitor_task and not self._monitor_task.done():
            self._monitor_task.cancel()
            try:
                await self._monitor_task
            except asyncio.CancelledError:
                pass
            except Exception as e:
                logger.bind(tag=TAG).warning(f"取消监听任务错误: {e}")
        self._monitor_task = None

    async def _start_monitor_tts_response(self):
        """监听多模态下行：文本事件驱动状态，二进制 PCM 转下发队列。
        连接绑定：进入时快照本 monitor 负责的 ws——退出时只清理自己
        那条连接；并发 rebuild 已换新 ws 时绝不能碰（旧版退出清理
        self.ws 会把新会话的连接误关，新会话秒死）。"""
        my_ws = self.ws
        try:
            while not self.conn.stop_event.is_set():
                try:
                    if self.ws is not my_ws:
                        # 连接已被 rebuild/start_session 换掉：本 monitor
                        # 服务旧连接，静默退出（新 monitor 由新会话启动）
                        logger.bind(tag=TAG).debug("monitor: 连接已更换，旧 monitor 退出")
                        break
                    msg = await my_ws.recv()

                    if isinstance(msg, (bytes, bytearray)):
                        self.opus_encoder.encode_pcm_to_opus_stream(
                            msg, False, callback=self.handle_opus
                        )
                        continue

                    data = json.loads(msg)
                    header = data.get("header", {})
                    header_event = header.get("event")
                    output = data.get("payload", {}).get("output", {}) or {}
                    event = output.get("event")

                    if header_event == "task-failed":
                        error = f"{header.get('error_code')}: {header.get('error_message')}"
                        logger.bind(tag=TAG).error(f"多模态任务失败: {error}")
                        self._session_error = error
                        self._notify_waiters()
                        break

                    if event == "Started":
                        self.dialog_id = output.get("dialog_id")
                        logger.bind(tag=TAG).debug(f"多模态会话已启动: {self.dialog_id}")
                    elif event == "DialogStateChanged":
                        state = output.get("state")
                        logger.bind(tag=TAG).debug(f"多模态状态切换: {state}")
                        if state == "Listening" and self._listening_event:
                            self._listening_event.set()
                        if self.full_duplex and state == "Thinking":
                            # 新一轮开始：清 LLM 增量累积；快照本轮 ASR 文本
                            # 供空响应兜底（Thinking 直接回 Listening 且期间
                            # 无 RespondingStarted 时走本地对话链路）
                            self._responding_text = ""
                            if getattr(self, "_local_transcript_inflight", False):
                                # 本地合成路径自发的 transcript：空响应由该路径
                                # 的段超时逻辑兜底，不进空响应兜底
                                self._thinking_asr_snapshot = ""
                            else:
                                snapshot = getattr(self, "_duplex_asr_partial", "")
                                if not snapshot and getattr(
                                    self, "_round_had_asr_text", False
                                ):
                                    snapshot = getattr(
                                        self, "_last_speech_ended_text", ""
                                    )
                                self._thinking_asr_snapshot = (snapshot or "").strip()
                            self._thinking_had_responding = False
                        if (
                            self.full_duplex
                            and state == "Listening"
                            and getattr(self, "_thinking_asr_snapshot", "")
                            and not getattr(self, "_thinking_had_responding", True)
                        ):
                            # 空响应兜底：语音触发的轮次百炼侧未产生任何回复
                            # （Thinking ~1s 后直接回 Listening，实测音乐类请求
                            # 必现）。注意不能用 transcript 重发用户原话——该 app
                            # 的 transcript 路径是"读稿合成"（把文本念出来而非
                            # 对话应答），复读用户原话会被 AEC 泄漏回百炼形成
                            # 空响应-复读死循环（2026-10-23 16:29 实录 6 连循环）。
                            # 正确兜底：走本地对话链路（本地 LLM 生成回复，再经
                            # 本地合成路径 RequestToRespond transcript 合成语音）。
                            fallback_text = self._thinking_asr_snapshot
                            self._thinking_asr_snapshot = ""
                            logger.bind(tag=TAG).warning(
                                f"duplex 空响应检测：Thinking 后无回复直接回 Listening，"
                                f"本地对话兜底『{fallback_text[:40]}』"
                            )
                            conn = self.conn
                            # 复位打断标志（本地链路里它由 startToChat 尾部
                            # 复位，这里不复位的话上一轮 abort 残留会丢掉
                            # 兜底轮的全部音频）
                            conn.client_abort = False
                            try:
                                conn.executor.submit(conn.chat, fallback_text)
                            except Exception as e:
                                logger.bind(tag=TAG).error(
                                    f"空响应本地兜底提交失败: {e}"
                                )
                    elif event == "RespondingStarted":
                        if self.full_duplex:
                            # 一条龙：服务端开始下发回复音频。
                            # 实测事件序：Thinking → RespondingContent → Responding
                            # → RespondingStarted → 音频 → RespondingEnded，
                            # FIRST 字幕文本取已累积的 LLM 增量
                            self._responding_active = True
                            self._thinking_had_responding = True
                            self._round_had_asr_text = False
                            self._local_transcript_inflight = False
                            self.current_sentence_id = self.conn.sentence_id
                            self._emit_first_sentence(
                                getattr(self, "_responding_text", "") or None
                            )
                        else:
                            self.tts_audio_queue.put(
                                (
                                    SentenceType.FIRST,
                                    [],
                                    self._segment_text,
                                    getattr(self, "current_sentence_id", None),
                                )
                            )
                    elif event == "RespondingContent":
                        if self.full_duplex:
                            # LLM 增量文本：积累给上报/显示（ RespondingContent 的
                            # payload.output.text 为增量），设备字幕走 FIRST 消息
                            text_delta = output.get("text") or ""
                            if text_delta:
                                self._responding_text = (
                                    getattr(self, "_responding_text", "") + text_delta
                                )
                    elif event == "RespondingEnded":
                        if self.full_duplex:
                            # 音频已收完。LAST 已可推（设备侧还有在途音频，
                            # sendAudioMessage 的流控会按节奏发完）。
                            # 实测：duplex 下服务端状态机自治（Responding 结束
                            # 自动回 Listening），不发 LocalRespondingEnded
                            self._emit_last_sentence()
                            self._responding_active = False
                        if self._responding_ended_event:
                            self._responding_ended_event.set()
                    elif event == "SpeechContent":
                        if self.full_duplex:
                            # 服务端 ASR 结果 → 设备字幕。实测百炼 SpeechContent
                            # 为**全量模式**（每条都是当前句从头到当前位置的
                            # 完整文本：'给我' → '给我放一首' → '给我放一首音乐。'），
                            # 直接覆盖。此前按"增量/全量混合"用 startswith 判定，
                            # 对真实增量（如'《偏向》'与'给我唱一首《偏向》'无
                            # 公共前缀）误判拼接 → 字幕/兜底文本重复放大
                            # （2026-10-23 16:29 实录 4 连重复）。
                            asr_text = (output.get("text") or "").strip()
                            if asr_text:
                                logger.bind(tag=TAG).debug(f"duplex SpeechContent: {asr_text[:50]}")
                                self._round_had_asr_text = True
                                self._duplex_asr_partial = asr_text
                    elif event == "SpeechStarted":
                        if self.full_duplex:
                            # 服务端 VAD 检测到用户说话：重置本句 ASR 累积
                            self._duplex_asr_partial = ""
                            logger.bind(tag=TAG).debug("duplex: 检测到用户说话")
                    elif event == "SpeechEnded":
                        if self.full_duplex:
                            logger.bind(tag=TAG).debug(f"duplex: 用户说话结束 text={getattr(self, '_duplex_asr_partial', '')[:50]!r}")
                            final_text = getattr(self, "_duplex_asr_partial", "").strip()
                            self._duplex_asr_partial = ""
                            # 供空响应恢复取最近一句（_duplex_asr_partial 已清）
                            if final_text:
                                self._last_speech_ended_text = final_text
                            if not final_text or self.conn.client_is_speaking:
                                # 播报期收到的是回声残留（非 AEC 板理论上已被
                                # 静音拦住，AEC 板正常透传）：兜底丢弃
                                continue
                            # prompt 回声防护：本地意图命中后发的 RequestToRespond
                            # (prompt) 会被服务端 SpeechContent 原文带回，不处理
                            last_prompt = getattr(self, "_last_local_prompt", "")
                            if last_prompt and final_text == last_prompt:
                                continue
                            asyncio.ensure_future(
                                _handle_duplex_asr(self.conn, final_text)
                            )
                    elif event == "Stopped":
                        logger.bind(tag=TAG).debug("多模态会话已停止")
                        self.activate_session = False
                        if self._stopped_event:
                            self._stopped_event.set()
                        self._process_before_stop_play_files()
                        await self._close_ws_quietly()
                        break
                    elif event == "Error":
                        error = (
                            f"{output.get('error_name')}: {output.get('error_message')}"
                        )
                        logger.bind(tag=TAG).error(f"多模态错误事件: {error}")
                        self._session_error = error
                        self._notify_waiters()
                        break
                    elif event in ("HeartBeat", "RequestAccepted"):
                        pass
                    else:
                        logger.bind(tag=TAG).debug(f"未处理事件: {event or header_event}")
                except websockets.ConnectionClosed:
                    logger.bind(tag=TAG).warning("WebSocket连接已关闭")
                    break
                except asyncio.CancelledError:
                    raise
                except Exception as e:
                    logger.bind(tag=TAG).error(
                        f"处理TTS响应时出错: {e}\n{traceback.format_exc()}"
                    )
                    break

            if my_ws is self.ws:
                # 只清理自己绑定的连接（rebuild 已换新连接时不碰）
                await self._close_ws_quietly()
        finally:
            # 只清自己的引用：rebuild 后新 monitor 已顶上时不动它
            if self._monitor_task is asyncio.current_task():
                self._monitor_task = None

    def _notify_waiters(self):
        if self._responding_ended_event:
            self._responding_ended_event.set()
        if self._listening_event:
            self._listening_event.set()
        if self._stopped_event:
            self._stopped_event.set()

    async def _close_ws_quietly(self):
        if self.ws:
            try:
                await self.ws.close()
            except Exception:
                pass
            self.ws = None

    # ------------------------------------------------------------------
    # 独立合成（试听 / to_tts / to_tts_stream 共用）
    # ------------------------------------------------------------------

    async def text_to_speak(self, text, output_file):
        """独立建连合成整段文本：output_file 为空返回 WAV bytes，否则写文件。"""
        filtered_text = MarkdownCleaner.clean_markdown(text)
        if self._correct_words_pattern:
            filtered_text = self._correct_words_pattern.sub(
                lambda m: self.correct_words[m.group(0)], filtered_text
            )
        if not filtered_text:
            return b"" if output_file is None else None

        wav_bytes = await self._synthesize_standalone(filtered_text)
        if output_file is None:
            return wav_bytes
        with open(output_file, "wb") as f:
            f.write(wav_bytes)
        return None

    async def _synthesize_standalone(self, text):
        task_id = str(uuid.uuid4())
        pcm_chunks = []

        async with websockets.connect(
            self.ws_url,
            additional_headers=self.header,
            ping_interval=30,
            ping_timeout=10,
            close_timeout=10,
            **self.ws_connect_options,
        ) as ws:
            start_msg = self._build_start_message(
                task_id, self.sample_rate, self._client_user_id()
            )
            await ws.send(json.dumps(start_msg))

            dialog_id = None
            listening = False
            responded_ended = False

            while not (listening and responded_ended):
                msg = await asyncio.wait_for(ws.recv(), timeout=self.respond_timeout)
                if isinstance(msg, (bytes, bytearray)):
                    pcm_chunks.append(msg)
                    continue
                data = json.loads(msg)
                header = data.get("header", {})
                if header.get("event") == "task-failed":
                    raise RuntimeError(
                        f"多模态任务失败: {header.get('error_code')}: {header.get('error_message')}"
                    )
                output = data.get("payload", {}).get("output", {}) or {}
                event = output.get("event")
                if event == "Started":
                    dialog_id = output.get("dialog_id")
                elif event == "DialogStateChanged" and output.get("state") == "Listening":
                    listening = True
                    respond_msg = self._continue_task(
                        task_id,
                        {
                            "directive": "RequestToRespond",
                            "dialog_id": dialog_id,
                            "type": "transcript",
                            "text": text,
                        },
                    )
                    await ws.send(json.dumps(respond_msg))
                elif event == "RespondingEnded":
                    responded_ended = True
                elif event == "Error":
                    raise RuntimeError(
                        f"多模态错误: {output.get('error_name')}: {output.get('error_message')}"
                    )

            # 收尾：告知播放结束 + 停止会话（尽力而为，失败不影响结果）
            try:
                await ws.send(
                    json.dumps(
                        self._continue_task(
                            task_id,
                            {"directive": "LocalRespondingEnded", "dialog_id": dialog_id},
                        )
                    )
                )
                await ws.send(
                    json.dumps(
                        self._finish_task(
                            task_id, {"directive": "Stop", "dialog_id": dialog_id}
                        )
                    )
                )
            except Exception:
                pass

        if not pcm_chunks:
            raise RuntimeError("多模态合成返回空音频")
        return _pcm_to_wav(b"".join(pcm_chunks), self.sample_rate)

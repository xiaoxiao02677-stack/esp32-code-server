import time
import json
import asyncio
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.connection import ConnectionHandler
from core.utils.util import audio_to_data
from core.handle.abortHandle import handleAbortMessage
from core.handle.intentHandler import handle_user_intent
from core.utils.output_counter import check_device_output_limit
from core.handle.sendAudioHandle import send_stt_message, SentenceType

TAG = __name__

# 服务端打断的播放起始保护窗（毫秒）。TTS 刚开始时服务端 AEC（互相关+Wiener）
# 尚未收敛，设备自己的播报声会被 VAD 判成人声，导致播报被自己掐断。
# 与固件侧 kSpeakingInterruptGuardMs（CONFIG_YH_INTERRUPT_GUARD_MS=800）同语义。
SERVER_INTERRUPT_GUARD_MS = 800


async def handleAudioMessage(conn: "ConnectionHandler", pcm_frame):
    # 当前片段是否有人说话
    have_voice = conn.vad.is_vad(conn, pcm_frame)
    # 如果设备刚刚被唤醒，短暂忽略VAD检测
    if hasattr(conn, "just_woken_up") and conn.just_woken_up:
        have_voice = False
        # 设置一个短暂延迟后恢复VAD检测
        if not hasattr(conn, "vad_resume_task") or conn.vad_resume_task.done():
            conn.vad_resume_task = asyncio.create_task(resume_vad_detection(conn))
        return
    # 服务端AEC功能需要实时触发打断
    if conn.client_aec:
        if conn.client_is_speaking and conn.client_listen_mode != "manual":
            if have_voice:
                await _maybe_server_interrupt(conn)
            else:
                # 确认窗按"连续人声"计量：人声一断，计窗立即归零。
                # 不复位的话，"先说100ms、隔5秒再说100ms"会被拼成连续人声误打断
                # （模拟时序验证发现的缺陷）。保护窗不受影响（按播报起始时刻算）。
                if getattr(conn, "interrupt_voice_since_ms", 0):
                    conn.interrupt_voice_since_ms = 0
    # 设备长时间空闲检测，用于say goodbye
    await no_voice_close_connect(conn, have_voice)
    # 接收音频
    await conn.asr.receive_audio(conn, pcm_frame, have_voice)


async def _maybe_server_interrupt(conn: "ConnectionHandler"):
    """服务端人声打断（带灵敏度确认窗 + 起播保护窗）。

    灵敏度语义与固件完全一致：管理端 interrupt_threshold(0~100) × 20ms
    = 人声确认窗。0=立即打断，100=需连续 2000ms 人声才打断，15≈默认 300ms。
    确认窗防的是：设备扬声器残留回声经服务端 AEC 衰减后仍偶发过 VAD 阈值
    （单帧尖峰），持续确认可滤除；真正的用户说话轻松持续超过窗长。
    """
    now = time.time() * 1000

    # 起播保护窗：client_is_speaking 置位（tts start 下发）后的保护期内不判打断
    started_at = getattr(conn, "client_speaking_since_ms", 0)
    if started_at and now - started_at < SERVER_INTERRUPT_GUARD_MS:
        return

    # 人声确认窗：连续检测到人声须超过阈值设定才触发。
    # 0 档 = 立即打断（与固件语义一致：confirm_ms=0 任何 VAD 抬升即打断，
    # 只剩起播保护窗兜底）——必须当帧触发，"先记时再判"会把 0ms 窗拖成
    # 至少一帧（60ms），时序模拟验证发现的偏差。
    confirm_ms = getattr(conn, "interrupt_confirm_ms", 300)
    if confirm_ms <= 0:
        conn.interrupt_voice_since_ms = 0
        await handleAbortMessage(conn)
        return

    first_seen = getattr(conn, "interrupt_voice_since_ms", 0)
    if not first_seen:
        conn.interrupt_voice_since_ms = now
        return
    if now - first_seen < confirm_ms:
        return

    conn.interrupt_voice_since_ms = 0  # 触发即复位，下段播报重新计时
    await handleAbortMessage(conn)


def reset_interrupt_tracking(conn: "ConnectionHandler"):
    """播报结束/打断触发后清零人声确认计窗（下一轮重新累计）。"""
    if hasattr(conn, "interrupt_voice_since_ms"):
        conn.interrupt_voice_since_ms = 0


async def resume_vad_detection(conn: "ConnectionHandler"):
    # 等待2秒后恢复VAD检测
    await asyncio.sleep(2)
    conn.just_woken_up = False


async def startToChat(conn: "ConnectionHandler", text):
    # 检查输入是否是JSON格式（包含说话人信息）
    speaker_name = None
    actual_text = text

    try:
        # 尝试解析JSON格式的输入
        if text.strip().startswith("{") and text.strip().endswith("}"):
            data = json.loads(text)
            if "speaker" in data and "content" in data:
                speaker_name = data["speaker"]
                actual_content = data["content"]
                conn.logger.bind(tag=TAG).info(f"解析到说话人信息: {speaker_name}")

                # 仅在该说话人首次出现时保留 {"speaker":...} JSON，让模型自然称呼一次；
                # 后续轮降为纯文本，避免每轮重复出现名字诱导模型反复称呼
                if speaker_name not in conn.introduced_speakers:
                    conn.introduced_speakers.add(speaker_name)
                    actual_text = text
                else:
                    actual_text = actual_content
    except (json.JSONDecodeError, KeyError):
        # 如果解析失败，继续使用原始文本
        pass

    # 保存说话人信息到连接对象
    if speaker_name:
        conn.current_speaker = speaker_name
    else:
        conn.current_speaker = None

    if conn.need_bind:
        await check_bind_device(conn)
        return

    # 如果当日的输出字数大于限定的字数
    if conn.max_output_size > 0:
        if check_device_output_limit(
            conn.headers.get("device-id"), conn.max_output_size
        ):
            await max_out_size(conn)
            return

    # manual 模式下不打断正在播放的内容
    if conn.client_is_speaking and conn.client_listen_mode != "manual":
        await handleAbortMessage(conn)

    # 首先进行意图分析，使用实际文本内容
    intent_handled = await handle_user_intent(conn, actual_text)

    if intent_handled:
        # 如果意图已被处理，不再进行聊天
        return

    # 意图未被处理，继续常规聊天流程，使用实际文本内容
    await send_stt_message(conn, actual_text)

    # 准备开始新会话
    conn.client_abort = False

    conn.executor.submit(conn.chat, actual_text)


async def no_voice_close_connect(conn: "ConnectionHandler", have_voice):
    if have_voice:
        conn.last_activity_time = time.time() * 1000
        return
    # 只有在已经初始化过时间戳的情况下才进行超时检查
    if conn.last_activity_time > 0.0:
        no_voice_time = time.time() * 1000 - conn.last_activity_time
        close_connection_no_voice_time = int(
            conn.config.get("close_connection_no_voice_time", 120)
        )
        if (
            not conn.close_after_chat
            and no_voice_time > 1000 * close_connection_no_voice_time
        ):
            conn.close_after_chat = True
            conn.client_abort = False
            end_prompt = conn.config.get("end_prompt", {})
            if end_prompt and end_prompt.get("enable", True) is False:
                conn.logger.bind(tag=TAG).info("结束对话，无需发送结束提示语")
                await conn.close()
                return
            prompt = end_prompt.get("prompt")
            if not prompt:
                prompt = "请你以```时间过得真快```未来头，用富有感情、依依不舍的话来结束这场对话吧。！"
            await startToChat(conn, prompt)


async def max_out_size(conn: "ConnectionHandler"):
    # 播放超出最大输出字数的提示
    conn.client_abort = False
    text = "不好意思，我现在有点事情要忙，明天这个时候我们再聊，约好了哦！明天不见不散，拜拜！"
    await send_stt_message(conn, text)
    file_path = "config/assets/max_output_size.wav"
    opus_packets = await audio_to_data(file_path)
    conn.tts.tts_audio_queue.put((SentenceType.LAST, opus_packets, text))
    conn.close_after_chat = True


async def check_bind_device(conn: "ConnectionHandler"):
    if conn.bind_code:
        # 确保bind_code是6位数字
        if len(conn.bind_code) != 6:
            conn.logger.bind(tag=TAG).error(f"无效的绑定码格式: {conn.bind_code}")
            text = "绑定码格式错误，请检查配置。"
            await send_stt_message(conn, text)
            return

        text = f"请登录控制面板，输入{conn.bind_code}，绑定设备。"
        await send_stt_message(conn, text)

        # 播放提示音
        music_path = "config/assets/bind_code.wav"
        opus_packets = await audio_to_data(music_path)
        conn.tts.tts_audio_queue.put((SentenceType.FIRST, opus_packets, text))

        # 逐个播放数字
        for i in range(6):  # 确保只播放6位数字
            try:
                digit = conn.bind_code[i]
                num_path = f"config/assets/bind_code/{digit}.wav"
                num_packets = await audio_to_data(num_path)
                conn.tts.tts_audio_queue.put((SentenceType.MIDDLE, num_packets, None))
            except Exception as e:
                conn.logger.bind(tag=TAG).error(f"播放数字音频失败: {e}")
                continue
        conn.tts.tts_audio_queue.put((SentenceType.LAST, [], None))
    else:
        # 播放未绑定提示
        conn.client_abort = False
        text = f"没有找到该设备的版本信息，请正确配置 OTA地址，然后重新编译固件。"
        await send_stt_message(conn, text)
        music_path = "config/assets/bind_not_found.wav"
        opus_packets = await audio_to_data(music_path)
        conn.tts.tts_audio_queue.put((SentenceType.LAST, opus_packets, text))

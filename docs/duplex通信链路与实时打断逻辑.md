# yuhe duplex 全双工通信链路与实时打断逻辑（技术分析文档）

> **文档目的**：完整描述 yuhe 语音助手 duplex（全双工一条龙）模式下的三方通信架构、协议细节、线程/协程模型、音频数据流与实时打断机制，供后续 agent 做链路分析、问题排查、功能扩展时使用。  
> **事实来源**：本文所有内容均来自 2026-10-23 已部署验证的代码与真机实录。文中标注了源码文件与行号，可直接定位。  
> **适用版本**：yuhe-server（原 xiaozhi-esp32-server）full_duplex=true 模式 + yuhe-esp32 固件（application.cc 状态机）。
>
> **⚠️ 2026-10-23 22:28 重大状态更新——服务端打断桥已回滚**：因主力板为非 AEC 板（播报期上行被静音替换防回声，语音打断实际不可用），`_abort_local_audio_for_speech` 打断桥全套已从生产代码回滚移除（md5 e5be5845 已部署测试服）。**§6.2 路径 B（服务端打断桥）、§6.4 中断标志机制、坑 4/5 的打断桥修复均已不存在于当前代码**。本文对应章节保留作历史分析参考（设计思路与根因记录仍有效），但**分析当前代码时以本标注为准**：当前 duplex 下打断只剩百炼WS② 百炼协议    ┌──────────────────┐  
> │  yuhe-esp32 设备  │ ◄══════════════► │   yuhe-server     │ ◄══════════════► │  阿里云百炼        │  
> │  (ESP32 固件)     │  opus 双向流     │  (Python 异步)    │  PCM 双向流      │  multimodal-dialog │  
> │                  │  JSON 控制消息    │                  │  JSON 事件流     │  (ASR+LLM+TTS)    │  
> └──────────────────┘                  └──────────────────┘                  └──────────────────┘  
>      本地只做：                            本地只做：                          云端全做：  
>      · opus 编解码                         · 协议转换/桥接                      · VAD 打断检测  
>      · 音频播放队列                         · 本地曲库音乐直发                    · ASR（SpeechContent）  
>      · 设备状态机                           · 本地意图(音量等)                    · LLM 对话  
>      · (无本地VAD/ASR/LLM)                  · 空响应本地兜底                      · TTS 合成

**职责划分核心事实**：duplex 模式下，**打断检测完全在云端**（百炼服务端 VAD），**本地 VAD / ASR / LLM 全部旁路**。设备只负责持续上行音频与按状态机收帧，yuhe-server 做协议桥接与本地音频源（音乐/兜底合成）管理。

- **WS①**：设备 ↔ yuhe-server，路径 `/yuhe/v1/`（测试环境 nginx 8144 明文反代或直连 8000）。上行二进制 opus 帧（16k mono 60ms）+ JSON 控制消息；下行二进制 opus 帧 + `tts`/`stt` 等 JSON 消息。
- **WS②**：yuhe-server ↔ 百炼 `wss://dashscope.aliyuncs.com`（多模态交互套件 multimodal-dialog）。上行二进制 PCM（固定 **16k** mono）+ JSON 指令；下行二进制 PCM（`conn.sample_rate`，本环境 24k）+ JSON 事件。

---

## 2. 设备 ↔ 服务端协议（WS①）

### 2.1 服务端 → 设备 JSON 消息

| 消息                                                   | 结构        | 固件行为（application.cc）                                                                                                                  |
| ---------------------------------------------------- | --------- | ------------------------------------------------------------------------------------------------------------------------------------- |
| `{"type":"tts","state":"start"}`                     | —         | **SetDeviceState(Speaking)——进 speaking 态的唯一入口**，幂等（speaking 态再收仅重置计时、作废挂起的 stop）；见 application.cc:897-905                             |
| `{"type":"tts","state":"sentence_start","text":...}` | text=字幕文本 | 仅显示字幕，不改状态。**text=None 时服务端直接吞掉不发**（sendAudioHandle.py:288）                                                                           |
| `{"type":"tts","state":"stop"}`                      | —         | 不立即切状态：播放队列非空则挂起 `pending_tts_stop_`，等 PLAYBACK_DRAINED（音频真正放完）再 SetDeviceState(Listening)；队列已空则直接切。防止播报尾巴被掐；见 application.cc:908-930 |
| `{"type":"stt","text":...}`                          | text=用户话语 | 显示用户说话字幕；同时服务端置 `client_is_speaking=True` 起播保护窗                                                                                       |

### 2.2 设备 → 服务端

- **二进制 opus 帧**：麦克风音频，16k mono 60ms/帧。服务端 `connection._decode_opus_packet` 用 `opuslib_next.Decoder(16000,1)` 解码成 PCM 后分流给 `tts.receive_upstream_audio()`。
- JSON 控制消息：hello（握手/鉴权）、listen start/stop（手动模式）、abort 等。

### 2.3 固件状态机（音频帧收发的核心约束）

```
              tts start（唯一入口，幂等）
   ┌─────────┐ ─────────────────────► ┌─────────┐
   │Listening│                        │Speaking │
   │         │ ◄───────────────────── │         │
   └─────────┘   tts stop（播放排空后） └─────────┘
     ▲    OnIncomingAudio 仅 Speaking 态入队（application.cc:774-776）
     │    Listening 态收到的音频帧【静默丢弃，无任何提示】
```

**这是 duplex 链路所有"听不到声音"类问题的根源约束**：服务端必须在发音频帧之前保证设备处于 speaking 态（即先发过 `tts start` 且之后没有 `tts stop` 覆盖）。历史上三次实测翻车都源于违反此约束（见 §8 坑 5/6/7）。

---

## 3. 服务端 ↔ 百炼协议（WS②）

### 3.1 会话建立（run-task）

一个 WS 连接生命周期内**只能成功 run-task 一次**（协议红线，重发被拒 `Invalid action('run-task')` → task-failed）。

```json
{
  "header": {"action": "run-task", "task_id": "<session_id>", "streaming": "duplex"},
  "payload": {
    "task_group": "aigc",
    "task": "multimodal-generation",
    "function": "generation",
    "model": "multimodal-dialog",
    "input": {
      "directive": "Start",
      "workspace_id": "<workspace_id>",
      "app_id": "<app_id>"
    },
    "parameters": {
      "upstream":  {"type":"AudioOnly", "mode":"duplex", "audio_format":"pcm", "sample_rate":16000},
      "downstream": {"voice":"<音色>", "sample_rate":24000, "audio_format":"pcm",
                      "intermediate_text":"transcript",
                      "volume":0-100, "speech_rate":50-200, "pitch_rate":50-200},
      "client_info": {"user_id": "<device-id 前36位>"}
    }
  }
}
```

**采样率陷阱**：上行固定 **16000**（与设备 opus 解码器对齐）；下行是 `conn.sample_rate`（本环境 24000）。两者不同，声明错会导致音频错位、ASR 全废。

**协议约束**：Start 后必须等 `DialogStateChanged(Listening)` 事件才能发后续指令/音频（代码 `start_session` 中用 `_listening_event` 同步等待，超时 `tts_timeout+10`）。

### 3.2 会话内指令（continue-task）

| 指令                                           | 用途                                | 触发时机                   |
| -------------------------------------------- | --------------------------------- | ---------------------- |
| `RequestToRespond {type:"transcript", text}` | 本地文本送百炼"读稿合成"（注意：是**念出来**，不是对话应答） | 本地兜底 LLM 回复分段合成；本地意图回复 |
| `LocalRespondingEnded`                       | 告知百炼本地播放已结束（回到 Listening）         | 本地段合成音频下发完成            |
| `RequestToSpeak`                             | 抢占话语权（停百炼当前轮）                     | 本地意图命中后                |
| `HeartBeat`                                  | 保活                                | 上行泵每 25s 一次            |

### 3.3 会话结束（finish-task → Stop）

duplex 会话**长驻**（与设备连接同生命周期），仅在设备断开时 Stop。

### 3.4 事件流（百炼 → 服务端，monitor 消费）

典型一轮语音对话的完整事件序（实测）：

```
SpeechStarted                    ← 云端 VAD 检测到用户开口（★打断桥触发点）
SpeechContent (×N, 全量模式)      ← ASR 结果，每条都是当前句从头到当前的完整文本
                                   例："给我" → "给我放一首" → "给我放一首音乐。"
SpeechEnded                      ← 用户说完（_duplex_asr_partial 取终值）
DialogStateChanged: Thinking     ← 百炼进思考（LLM 推理）
RespondingContent (×N, 增量)      ← LLM 回复增量文本（拼接用于字幕/上报）
DialogStateChanged: Responding
RespondingStarted                ← 回复音频开始下发
<二进制 PCM 帧 ×N>                ← 回复语音
RespondingEnded                  ← 本轮音频下发完（服务端推 LAST → 设备 tts stop）
DialogStateChanged: Listening    ← 服务端状态机自治回 Listening
```

其他事件：`Started`（携带 dialog_id，会话建立成功）、`Stopped`（Stop 指令的响应）、`Error`、`RequestAccepted`/`HeartBeat`（忽略）、header 级 `task-failed`（致命错误，携带 error_code/error_message）。

### 3.5 保活约束

- **20s 无上行即断连**：上行泵空闲时每 100ms 发静音帧（`b"\x00" * 3200`，16k×2byte×0.1s）。
- **60s 无下行即 ResponseTimeout**：25s 周期 HeartBeat 指令兜底。

---

## 4. 服务端线程/协程模型

yuhe-server 是 asyncio 单事件循环 + 两个 TTS 工作线程的结构。理解"谁在哪个执行环境里跑"是分析一切竞态问题的前提：

```
┌─ asyncio 事件循环（conn.loop）────────────────────────────────────────┐
│                                                                       │
│  connection handler          _start_monitor_tts_response()            │
│  · 收设备 opus → 解码 PCM      · 收百炼 JSON 事件 → 状态驱动            │
│  · receive_upstream_audio()   · 收百炼二进制 PCM → opus 编码 → 音频队列 │
│       │                       · SpeechStarted → ★打断桥               │
│       ▼                              │                                │
│  _upstream_loop()（上行泵协程）        ▼                                │
│  · 100ms 合并 _upstream_buffer  tts_audio_queue（queue.Queue）         │
│    直发百炼（空闲发静音帧）      ▲▲▲ 生产者：monitor/音乐转码/兜底合成   │
│  · 25s HeartBeat               ────────────────────────────────       │
│  · 发失败 → _rebuild_duplex_session（单飞，持锁拆毁，锁外重建）          │
│                                                                       │
└───────────────────────────────────────────────────────────────────────┘
        ▲ run_coroutine_threadsafe                    ▲ run_coroutine_threadsafe
        │                                             │
┌─ tts 文本线程 ────────────────────┐   ┌─ 播放线程（base.py:518）──────────┐
│ tts_text_priority_thread()        │   │ _audio_play_priority_thread()     │
│ · 标点切段                        │   │ · 从 tts_audio_queue 取四元组      │
│ · 每段一次 RequestToRespond       │──►│ · FIRST 时按标志补发 tts start     │
│ · 阻塞等 RespondingEnded（可被打断 │   │ · sendAudioMessage（预缓冲+流控）  │
│   桥解卡）                         │   │ · LAST → tts stop                 │
│ · FILE 消息 → _play_local_file_   │   │ · 流控：AudioRateController       │
│   duplex（音乐转码，帧回调可中断）  │   │   （60ms 节奏后台 asyncio 任务）   │
└───────────────────────────────────┘   └───────────────────────────────────┘
```

**互斥锁**：`_session_lock`（asyncio.Lock，不可重入）串行化所有会话建立/拆毁。入口：hello 触发的 `start_duplex_session`、tts 线程 FIRST 确认、上行泵失败触发的 `_rebuild_duplex_session`。

---

## 5. 音频数据流（双队列下行 + 单缓冲上行）

### 5.1 下行：百炼 PCM → 设备 opus（双队列！）

```
百炼二进制 PCM (24k)
  → monitor: opus_encoder.encode_pcm_to_opus_stream (60ms 帧)
  → tts_audio_queue.put(MIDDLE, opus帧)          ← 队列①（queue.Queue，播放线程消费）
  → 播放线程 sendAudioMessage → sendAudio
      ├─ 预缓冲：前 5 包直接发（降延迟，sendAudioHandle.py:259）
      └─ 后续包 → AudioRateController.add_audio    ← 队列②（deque，60ms 节奏后台任务发）
  → conn.websocket.send(opus)  →  设备（仅 speaking 态入队）
```

**打断必须两个队列都清**（§7），这是历史上"打断后音乐继续响到曲终"的直接原因：音乐帧大部队早已从队列①转移到队列②。

### 5.2 上行：设备 opus → 百炼 PCM

```
设备二进制 opus (16k 60ms)
  → connection._decode_opus_packet (opuslib Decoder(16000,1))
  → tts.receive_upstream_audio(pcm)
      ├─ 会话未就绪 → 丢帧 + 节流(10s)触发 _rebuild_duplex_session
      ├─ 非AEC板 && 播报期（client_is_speaking 或结束后1.5s尾窗）
      │    → 替换为静音帧（防回声被云端 VAD 当人声 → 自打断循环）
      └─ _upstream_buffer (asyncio.Queue, maxsize=200)
           └─ _upstream_loop：每100ms 合并直发（满则丢最旧保实时）
                空闲发静音帧；25s HeartBeat
```

**AEC 板（`conn.client_aec=True`，如 yh-cam）豁免静音替换**——回声已在固件消除，保留播报期真实上行，语音打断全时可用。非 AEC 板播报期上行的是静音，打断只能发生在播报间隙/结束后（1.5s 尾窗过了才恢复真实上行）。

---

## 6. 实时打断逻辑（核心章节）

### 6.1 检测：完全在云端

**设备不做任何声学判断**。麦克风音频持续上行（AEC 板全程真实音频；非 AEC 板播报期静音），百炼服务端 VAD 在持续的 PCM 流上判定"用户开口"，下发 `SpeechStarted` 事件。判定灵敏度、阈值全在百炼侧配置，本地无参数。

### 6.2 执行：双路径并行

用户开口后，有两路"停播"同时发生，管辖不同的音频源：

**路径 A——百炼自治（管百炼自己的 Responding 轮）**：  
百炼检测到用户说话，自行停掉当前轮 TTS 下发（不再发剩余 PCM），状态机切新轮 Thinking。服务端无需干预，`RespondingStarted` 之前收到的剩余帧自然停止。

**路径 B——服务端打断桥（管本地音频源）**：  
百炼管不到服务端本地产生的音频（音乐文件帧、本地兜底合成帧）。monitor 收到 `SpeechStarted` 时同步调用 `_abort_local_audio_for_speech()`（aliyun_multimodal.py:865）：

```python
def _abort_local_audio_for_speech(self):
    # ① 置中断标志：本地段合成循环（_speak_stream_segment_async）和
    #    音乐转码回调（_frame_cb）检测到即放弃剩余输出
    self._local_respond_aborted = True
    # ② 解卡在途段合成：打断路径百炼【不发 RespondingEnded】（协议如此），
    #    _speak_stream_segment_async 的 wait_for(60s) 必须手动 set 事件解卡，
    #    否则 tts 线程被卡满 60s，打断后的新请求全部堵死（实测卡 55s）
    if self._responding_ended_event:
        self._responding_ended_event.set()
    # ③ 清队列①：tts_audio_queue 里所有排队帧（FIRST/MIDDLE/LAST）
    while True: self.tts_audio_queue.get_nowait() ...
    # ④ 清队列②：AudioRateController.reset() —— cancel 后台发送任务 +
    #    清 deque + set queue_empty_event（同时解卡播放线程在
    #    _wait_for_audio_completion 的等待）。不清这里，音乐继续响到曲终
    conn.audio_rate_controller.reset()
    # ⑤ 补 LAST：让设备收到 tts stop → 播放排空 → 回 Listening
    self._emit_last_sentence()
```


五个动作缺一不可，每个都对应一次真实事故（§8）。

### 6.3 打断后时序（实测 wire 顺序）

```
用户开口（对着正在放音乐的设备说话）
  │
  ├─ [云端] 百炼 VAD 检测 → 下发 SpeechStarted ──────┐
  │                                                  ▼
  │                                    monitor → 打断桥五件套（同步执行）
  │  [设备] 音乐停（打断后 ~1.4s 实测）            （丢帧+reset+补LAST）
  │
  ├─ [云端] SpeechContent ×N（ASR 全量）→ SpeechEnded
  ├─ [云端] Thinking → LLM → RespondingStarted → PCM 下发
  │    monitor: _emit_first_sentence()（置 tts start 补发标志 + FIRST 入队）
  │    播放线程: 补发 tts start → sentence_start(字幕) → 音频帧
  └─ [设备] 收 tts start → Speaking → 收帧入队播放（新轮回复 ~3.6s 实测）
```

### 6.4 打断后的本地合成放弃机制

`_local_respond_aborted` 标志的三个检查点：

1. `_speak_stream_segment_async` 段循环前（aliyun_multimodal.py:423）——放弃本轮剩余段落；
2. 段 `wait_for(RespondingEnded)` 返回后（:462）——不再发 `LocalRespondingEnded`（服务端已被用户新语音切轮，再发状态指令只会添乱），直接返回；
3. `_play_local_file_duplex` 的 `_frame_cb`（:809）——抛 `_Aborted` 异常终止音乐转码（设备侧队列已清，继续转码只是浪费 CPU/内存）。

标志复位时机：新一轮本地播放/合成开始时（`_speak_stream_segment_async` 入口、`_play_local_file_duplex` 入口）——上一轮被打断的事实不带入本轮。

### 6.5 设备主动打断路径（对照）

设备侧 listen start（手动打断按钮等）→ 服务端 `conn.client_abort=True` → tts 文本线程走 `_abort_duplex_turn()`（仅发 LocalRespondingEnded 告知百炼，会话不 Stop）。固件自己停本地播放。duplex 长驻会话设计下，打断**永远不停会话**，只停当前轮。

---

## 7. 本地音乐直发路径（play_music 兜底）

百炼控制台的音乐指令（play_music 等）是虾米系音源插件指令，与本地曲库无对接——**百炼侧音乐类请求必然空响应**（Thinking 后直接回 Listening，无 RespondingStarted）。空响应由 monitor 的兜底检测捕获，走本地链路：本地 LLM 生成"请欣赏"引导语 + 本地曲库搜歌 → `_play_local_file_duplex`（aliyun_multimodal.py:798）：

```
引导语段（RequestToRespond transcript → 百炼合成 PCM → 帧下发）
  → 段 RespondingEnded → _emit_last_sentence → 设备 tts stop → 回 Listening
音乐文件（mp3 → opus 转码）：
  FIRST("♪ 歌名") + _need_tts_start_before_next_first = True
  → 播放线程按队列顺序：补发 tts start → sentence_start(歌名) → 音乐帧 MIDDLE 流
  → 转码完 _emit_last_sentence → LAST → tts stop（整首歌发完）
```

**tts start 补发机制（wire 顺序保证）**：音乐 FIRST 紧跟引导语 LAST 之后，设备已回 Listening（固件状态机丢帧约束 §2.3）。`tts start` 不能在转码线程直接发——会抢跑到引导语的 `tts stop`（那个 stop 由播放线程在音频排空后才发，晚 1~2s）之前，被它覆盖回 Listening，音乐帧照样全丢。所以只置标志 `_need_tts_start_before_next_first=True`，由**播放线程**在处理该 FIRST 时按队列顺序补发（base.py:562-576），保证 wire 顺序：`引导语帧 → tts stop → tts start → sentence_start → 音乐帧`。

该机制已通用化：`_emit_first_sentence`（百炼新轮）与本地兜底多段合成（段间设备回 Listening）都走同一补发路径，幂等无害（speaking 态再收 start 仅重置计时）。

---

## 8. 协议红线与历史坑索引（供分析时对照）

每条都来自真机/模拟器实录，按踩坑时间排序：

| # | 坑 | 根因 | 修复/规避 |
|---|---|---|---|
| 1 | websockets 1011 连接错误 | `additional_headers` 塞 User-Agent 与库默认 UA 重复，服务端 `dict(headers)` 抛 MultipleValuesError | 用 `user_agent_header=` 参数（仅模拟器侧；服务端用 dashscope 域名直连不受影响） |
| 2 | run-task 死循环（11 连 Invalid action） | 一个连接只能 run-task 一次；并发 rebuild 抹掉状态后 `_ensure_connection` 复用旧连接重发被拒 → task-failed → 再 rebuild 循环 | start_session 拆旧条件加 `or self.ws`；rebuild 拆毁段持 `_session_lock` + 单飞去抖 + 独立 task 不自 cancel |
| 3 | task-failed 假成功 | `_notify_waiters` set 所有等待事件，`wait_for(Listening)` 误判成功 | 等待后显式判 `if self._session_error: raise`（aliyun_multimodal.py:511-514） |
| 4 | 打断后新请求卡 55s | 打断路径百炼不发 RespondingEnded，段合成 `wait_for` 干等满 60s 超时，tts 线程被阻塞 | 打断桥 set `_responding_ended_event` 解卡 + `_local_respond_aborted` 放弃剩余段 |
| 5 | 打断后音乐继续响（203KB 残流） | 只清了队列①，帧大部队已在 AudioRateController deque；播放线程还卡在 `_wait_for_audio_completion` | 打断桥调 `rc.reset()`（清 deque + cancel 后台任务 + set 事件解卡） |
| 6 | 真机音乐无声（"你所谓的兜底呢"） | 引导语 LAST → 设备回 Listening → 音乐帧全部被固件静默丢弃（§2.3 状态机约束） | v1 直接发 tts start 失败（抢跑被晚到的 stop 覆盖）；v2 标志位由播放线程按队列顺序补发（§7） |
| 7 | 本地兜底多段回复段间丢帧（4KB） | 每段 LAST → 设备回 Listening → 下一段帧被丢 | `_emit_first_sentence` 统一置标志，任何 FIRST 前按需补发 tts start（幂等） |
| 8 | 空响应死循环（6 连复读） | transcript 是"读稿合成"不是对话应答；用 transcript 重发用户原话 → AEC 泄漏回百炼 → 再空响应 → 再重发 | 红线：**绝不 transcript 重发用户原话**；空响应兜底走本地 LLM 对话链路（monitor 的 Thinking 后无 RespondingStarted 检测，aliyun_multimodal.py:1018-1048） |
| 9 | 字幕/兜底文本重复放大 | SpeechContent 是**全量模式**（每条都是整句从头到当前），按增量拼接导致重复 | 直接覆盖不拼接（:1091-1104） |
| 10 | dashscope SDK 不用 | 同步 threading / 保活不托管等缺陷；且换 SDK 后空响应依旧 | 直接 websockets 裸连 dashscope 域名 |
| 11 | monitor 误关新连接 | 旧 monitor 退出清理 `self.ws`（已被 rebuild 换成新连接） | monitor 绑定进入时的 ws 快照，只清理自己的连接（:956-1173） |
| 12 | 非AEC板自打断循环 | 播报回声被云端 VAD 当人声 | 播报期（+1.5s 尾窗）真实帧替换静音帧；AEC 板豁免 |

---

## 9. 会话生命周期与会话重建

```
设备 hello ──► start_duplex_session（3次重试，dashscope 偶发握手超时）
                ├─ start_session：持锁 → close旧 → connect → run-task → 等 Listening
                └─ _start_upstream_task：上行泵启动

会话存活期：设备音频持续上行（静音保活）+ HeartBeat + monitor 消费事件

触发重建的路径（全部汇入 _rebuild_duplex_session，单飞+持锁拆毁+锁外重建）：
  a) receive_upstream_audio 发现会话未就绪（10s 节流）
  b) 上行泵 ws.send 失败
  c) monitor 收 ConnectionClosed 退出

设备断开 ──► stop_duplex_session：cancel 上行泵 + finish_session（Stop 指令）
```

重建后 `dialog_id` 是新的（继承旧 id 会被百炼拒绝），上下文不保留。

---

## 10. 源码索引

| 文件 | 关键位置 | 内容 |
|---|---|---|
| `yh/yuhe-server/core/providers/tts/aliyun_multimodal.py` | :52-92 `_handle_duplex_asr` | duplex ASR 落地：字幕 + 本地意图 + 透传 |
| | :192-234 `_build_start_message` | run-task 消息构造（上/下行参数） |
| | :260-383 `tts_text_priority_thread` | tts 文本线程：切段/合成/音乐分发 |
| | :401-471 `_speak_stream_segment_async` | 本地段合成（RequestToRespond + 中断检查） |
| | :473-525 `start_session` | 会话建立（持锁、拆旧、假成功判定） |
| | :563-698 `start_duplex_session`/`_upstream_loop` | 长驻会话 + 上行泵（100ms 合并/静音/心跳） |
| | :700-752 `_rebuild_duplex_session` | 单飞重建（拆毁持锁、不自 cancel） |
| | :780-796 `_emit_first_sentence` | FIRST 入队 + tts start 补发标志 |
| | :798-852 `_play_local_file_duplex` | 音乐直发（可中断转码） |
| | :865-909 `_abort_local_audio_for_speech` | ★打断桥五件套 |
| | :956-1173 `_start_monitor_tts_response` | 百炼事件消费 + 连接绑定 + 空响应兜底 |
| `yh/yuhe-server/core/providers/tts/base.py` | :518-583 `_audio_play_priority_thread` | 播放线程（含 :562-576 tts start 队列顺序补发） |
| `yh/yuhe-server/core/handle/sendAudioHandle.py` | :23-57 `sendAudioMessage` | FIRST→sentence_start / LAST→tts stop |
| | :60-83 `_wait_for_audio_completion` | 播放线程在 LAST 后等待发送完成（打断 reset 解卡点） |
| | :121-283 `sendAudio` 系列 | 预缓冲 5 包 + AudioRateController 流控 |
| | :286-325 `send_tts_message` | tts 状态消息（text=None 的 sentence_start 吞掉 :288） |
| `hardware/sets/yuhe-esp32/main/application.cc` | :774-776 `OnIncomingAudio` | 仅 Speaking 态入队（丢帧约束） |
| | :897-905 | tts start → Speaking（幂等，作废挂起 stop） |
| | :908-930 | tts stop → 挂起等 PLAYBACK_DRAINED → Listening |

---

## 11. 当前状态与已知边界（2026-10-23）

**已验证闭环**（测试环境模拟器 + 状态机语义，ALL PASS，dropped=0B）：点歌出声、播放中实时打断（1.4s 停）、打断后立即换歌（2.3s）、未命中播报+随机、多段回复无吞字、打断后新轮回复 3.6s。

**已知边界/遗留**：

1. **真机最终验证待做**（模拟器已带固件状态机语义，但真机 AEC/网络实况未验）。
2. 测试 agent 百炼侧提示词异常（"不管说什么都回答哈哈哈"），百炼全空响应、全走本地兜底链路——验证数据的"百炼正常应答"部分说服力受限。
3. 非 AEC 板播报期（+1.5s 尾窗）上行静音：打断在播报中段不可用（回声防护的代价），仅播报间隙/结束后可打断；AEC 板无此限制。
4. 重建后对话上下文丢失（新 dialog_id，百炼协议限制）。
5. 打断检测灵敏度完全取决于百炼 VAD 配置，本地不可调。
6. 空响应兜底依赖"Thinking 后无 RespondingStarted"启发式，若百炼事件序变化需重新校准。

---

## 12. 2026-10-23 22:28 服务端打断桥回滚清单

**回滚原因**：主力设备为非 AEC 板——duplex 上行在播报期被静音替换（§5.2 回声防护），云端 VAD 根本收不到播报期语音，实时打断无实际收益；且回声泄漏时打断桥可能误杀正常音乐。用户决定回滚，等 AEC 板硬件到位后再恢复。

**回滚内容**（aliyun_multimodal.py，回滚后 md5 e5be5845，已部署测试服并重启验证）：

| 位置 | 回滚项 | 原功能 |
|---|---|---|
| `_abort_local_audio_for_speech` 方法 | 整体删除 | 打断桥五件套：置中断标志/解卡段合成/清队列①/清队列②(reset)/补 LAST |
| monitor SpeechStarted 分支 | 删除 `_abort_local_audio_for_speech()` 调用 | 用户开口时触发打断桥（ASR 重置与 debug 日志保留） |
| `_speak_stream_segment_async` 入口 | 删除 `_local_respond_aborted = False` 复位 | 新一轮合成前清打断标志 |
| `_speak_stream_segment_async` 段循环前 | 删除中断检查+return | 打断后放弃剩余合成段 |
| `_speak_stream_segment_async` 段等待后 | 删除中断检查+return（不发 LocalRespondingEnded 分支） | 打断后跳过 LocalRespondingEnded |
| `_play_local_file_duplex` | 删除 `_Aborted` 异常类、`_frame_cb` 中断检查、标志复位、`except _Aborted` 分支 | 音乐转码可中断终止 |
| `__init__` | 删除 `self._local_respond_aborted = False` 初始化 | 打断标志 |

**明确保留**（独立 bug 修复，与打断无关，回滚会复活更严重问题）：

| 保留项 | 理由 |
|---|---|
| run-task 死循环修复（start_session 拆旧条件/task-failed 假成功判定/rebuild 单飞持锁/monitor 连接绑定） | 11 连 Invalid action 死循环根因 |
| `_play_local_file_duplex` 音乐直发 + `_need_tts_start_before_next_first` 标志 + 播放线程队列顺序补发 tts start（base.py :562-576） | 真机"只播引导语没有音乐"根因（固件 speaking 态收帧约束） |
| `_emit_first_sentence` 统一置补发标志 | 本地兜底多段回复段间丢帧根因 |
| SpeechContent 全量覆盖逻辑 | 字幕重复放大根因 |
| 上行静音替换 + AEC 豁免（receive_upstream_audio） | 非 AEC 板回声防护（本次回滚决策的依据本身） |
| 手动打断路径（listen start → client_abort → `_abort_duplex_turn` :750） | 设备按钮打断，独立于打断桥，未动 |

**回滚后的打断现状**：duplex 下语音打断只剩路径 A（百炼自治，管百炼自己的 Responding 轮）；本地音频源（音乐/本地兜底合成）播放期间**不可语音打断**——要么等播完，要么按设备上的打断按钮（listen start 路径，设备自己停本地播放 + 服务端 `_abort_duplex_turn` 发 LocalRespondingEnded 切轮）。

**回滚副作用须知**：打断桥曾一并解决的"打断后新请求卡 55s"（坑 4）与"打断后音乐残流"（坑 5）两个问题**随打断场景一起消失**（不触发打断就不会触发这两个问题）；但若未来重新启用打断（AEC 板到位），这两个坑会随打断场景回归，需连同打断桥一起恢复——完整备份在 `aliyun_multimodal.py.bak-pre-rollback-20261023`（本地仓，md5 65bcd3dd 版本）。

**git 注意**：`aliyun_multimodal.py.bak-pre-rollback-20261023` 备份文件勿提交入库（含打断桥完整实现，仅作恢复参考）。

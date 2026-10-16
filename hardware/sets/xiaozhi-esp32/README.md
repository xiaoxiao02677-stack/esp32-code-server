# xiaozhi-esp32 项目解读与魔改指南

> 面向想魔改此项目的开发者。先讲清楚"它是怎么运作的"，再重点拆解**语音链路（ASR/LLM/TTS）**，最后给出魔改入口。

---

## 1. 一句话架构

ESP32 固件本身**只是一个"瘦客户端"**：采集麦克风音频 → Opus编码 → 推给服务器；接收服务器的 Opus 音频 → 解码 → 扬声器播放。**所有智能（唤醒词除外）、ASR、LLM、TTS 全在服务端**。固件用 ESP-IDF C/C++ 编写，一次构建只选择一块板子（board）。

```
┌─────────────── ESP32 固件 ───────────────┐      ┌────────── 服务端 ──────────┐
│ 麦克风 → AFE引擎(回声消除/唤醒词) → Opus编码 │ ───> │ ASR → LLM → TTS → Opus封装 │
│ 扬声器 ← 音频输出任务 ← Opus解码 ←──────────│ <─── │                            │
└──────────────────────────────────────────┘      └────────────────────────────┘
```

---

## 2. 目录导览（魔改最常碰的目录）

| 目录 | 职责 | 魔改场景 |
|---|---|---|
| `main/application.cc/.h` | 主事件循环、协议生命周期、状态机驱动 | 改交互逻辑、加新消息类型 |
| `main/device_state_machine.*` | 设备状态机（合法状态跳转） | 加新状态 |
| `main/audio/` | 编解码器驱动、音频管线、唤醒词引擎 | 改音质、改采样率、改音频处理 |
| `main/protocols/` | WebSocket / MQTT+UDP 双传输实现 | 自建服务器对接 |
| `main/boards/**/` | 每块开发板的引脚和外设初始化 | 移植新硬件 |
| `main/display/` `main/led/` | 屏幕 UI、表情灯 | 改外观表现 |
| `main/mcp_server.*` | 设备端 MCP 工具（IoT 控制） | 给 AI 加"手" |
| `main/assets/` | 多语言提示音(.ogg)、语言包 | 换开机音/提示音 |
| `main/notify/` | HTTP 音频通知播放器 | 推送播报功能 |

---

## 3. 运作主流程：一次完整对话

### 3.1 状态机

`main/device_state.h` 定义了核心状态：

```
Idle → Connecting → Listening → Speaking → Listening → ... → Idle
```

另有 `WifiConfiguring / Notifying / Upgrading / Activating / AudioTesting / FatalError` 等旁路状态。所有跳转必须经 `Application::SetDeviceState()` → `DeviceStateMachine::TransitionTo()`，非法跳转会被拒绝。状态变化会同步驱动屏幕/LED 更新和音频引擎开关。

### 3.2 对话时序（关键！）

```
用户说话 "你好小智"
  1. [设备] 唤醒词引擎(WakeNet/MultiNet, 本地) 命中 → 进入 Connecting
  2. [设备] 打开音频通道: WebSocket 或 MQTT+UDP (由 OTA 配置决定用哪个)
  3. [设备→服务器] hello 握手 (声明音频参数: opus/16kHz/mono/60ms)
  4. [设备→服务器] listen start (auto/manual/realtime 三种模式)
  5. [设备→服务器] 二进制 Opus 音频流持续上传
  6. [服务器→设备] {"type":"stt","text":"..."}          ← 识别结果上屏
  7. [服务器→设备] {"type":"llm","emotion":"happy"}      ← 表情更新
  8. [服务器→设备] {"type":"tts","state":"start"}        ← 设备进入 Speaking
  9. [服务器→设备] 二进制 Opus 音频流持续下发            ← TTS 语音
 10. [服务器→设备] {"type":"tts","state":"sentence_start","text":"..."} ← 字幕
 11. [服务器→设备] {"type":"tts","state":"stop"}         ← 播完回 Listening/Idle
```

打断（说话时喊唤醒词）：设备发 `{"type":"abort","reason":"wake_word_detected"}`，清空播放队列，直接跳回 Listening。实时模式（`kListeningModeRealtime`）依赖 AEC，可边播边听。

### 3.3 JSON 消息分发中枢

`Application::InitializeProtocol()` 里注册的 `OnIncomingJson` 回调（`main/application.cc:579` 附近）是**所有服务器消息的入口**，按 `type` 分发：`tts` / `stt` / `llm` / `mcp` / `system` / `notify` / `alert` / `custom`。想加自定义消息协议，就从这里下手。

---

## 4. TTS 链路深度拆解（魔改重点）

### 4.1 先纠正一个认知：TTS 合成不在固件里

固件里**没有任何 TTS 引擎**。服务器把 TTS 合成结果编码成 Opus 帧（默认 24kHz/mono/60ms）流式下发，设备只负责：

```
服务器 Opus 帧
  → Protocol 收包 (websocket.cc / mqtt_protocol.cc)
  → OnIncomingAudio 回调 (仅 Speaking 状态才接收! 见 application.cc:554)
  → AudioService::PushPacketToDecodeQueue()          [audio_decode_queue_]
  → OpusCodecTask 解码成 PCM + 按需重采样(24k→codec输出率) [audio_service.cc:381]
  → audio_playback_queue_
  → AudioOutputTask 写入 AudioCodec → 功放 → 喇叭
```

**所以：想换音色/换TTS厂商 = 改服务器配置，不用动固件。** 官方服务端有开源复刻（如 xiaozhi-esp32-server 社区项目），自建后可接 EdgeTTS / 火山引擎 / GPT-SoVITS / CosyVoice 等任意 TTS。

### 4.2 设备端能魔改的音频点

| 想改什么 | 改哪里 | 说明 |
|---|---|---|
| 上行采样率/帧长 | `main/audio/audio_service.h:40` `OPUS_FRAME_DURATION_MS`、`AS_OPUS_ENC_CONFIG()` | 上行固定 16kHz；帧长改动需与服务器协商（hello 里会声明） |
| 下行采样率 | 不用改 | 服务器 hello 里声明 `sample_rate`(默认24000)，设备 `SetDecodeSampleRate()` 动态适配并自动重采样（`esp_ae_rate_cvt`），喇叭输出率由 codec 决定 |
| 播放缓冲深度 | `MAX_DECODE_PACKETS_IN_QUEUE`(约1.2s) / `MAX_SEND_PACKETS_IN_QUEUE`(约2.4s) | 调大更抗网络抖动，延迟变大 |
| 打断响应速度 | `Application::OnAudioOutput` / abort 流程 | 打断即刻 `ResetDecoder()` 清队列 |
| 回声消除 | Kconfig: `CONFIG_USE_DEVICE_AEC`（设备端AEC）/ `CONFIG_USE_SERVER_AEC`（服务器端AEC） | S3/P4/S31 用 AFE 前端 AEC，其它芯片靠服务器 AEC |

### 4.3 三条独立的"发声"通道（容易混淆！）

固件里有**三条不同的播放路径**，魔改时别搞混：

1. **TTS 流播放**（如上）：网络 Opus → 解码队列 → 播放。状态机控制。
2. **本地提示音** `AudioService::PlaySound()`（`audio_service.cc:764`）：播放固件**内嵌**的 .ogg 资源（`main/assets/locales/<语言>/*.ogg`，编译时 `EMBED_FILES` 进固件，`Lang::Sounds::OGG_POPUP` 等引用）。OggDemuxer 解出 Opus 包后**复用同一条解码→播放管线**。换提示音 = 替换 ogg 文件重新编译。
3. **通知播放** `NotifyPlayer`（`main/notify/notify_player.h`）：服务器发 `{"type":"notify","audio_url":"http://..."}` + 字幕，设备起独立任务 HTTP 拉流（Opus）塞进解码队列，设备进入 `Notifying` 状态，按 `start_ms` 时间轴同步字幕。这是**设备端唯一主动从网络拉音频**的场景。

### 4.4 音频任务与队列模型

`AudioService`（`main/audio/audio_service.cc`）内有三个专用 FreeRTOS 任务：

- `AudioInputTask`：读 codec 输入 → 喂给音频引擎（AFE 或 Lite）
- `AudioOutputTask`：把解码后的 PCM 写到 codec
- `OpusCodecTask`：双向 Opus 编/解码（一个任务干两件事，靠队列+条件变量调度）

队列全部是**编译期定容**的 `FixedQueue`，满了丢旧包（实时语音宁可丢也不要迟到）。音频引擎按芯片分两档：

| 芯片 | 引擎 | 能力 |
|---|---|---|
| ESP32-S3 / P4 / S31 | `AfeAudioEngine`（ESP-SR AFE） | 前端AEC + VAD + WakeNet（或自定义 MultiNet 唤醒词） |
| ESP32 / C3 / C5 / C6 | `LiteAudioEngine` | 裸 PCM 上传 + 独立 WakeNet（可选） |

唤醒词命中前 2 秒音频缓存在 64KB PSRAM 环形缓冲（`WakeWordAudioCache`），命中后连同唤醒词音频一起编码上传给服务器做声纹校验。

---

## 5. 服务器对接与协议

- **WebSocket**（`docs/websocket.md`）：单连接，文本帧=JSON 控制，二进制帧=Opus。逻辑最简单，自建服务器首选。
- **MQTT+UDP**（`docs/mqtt-udp.md`）：MQTT 走控制，UDP 走音频（AES-CTR 加密），延迟更低但实现复杂。
- 用哪个由 **OTA 接口下发的配置**决定（`Application::InitializeProtocol()`，`application.cc:531`），不是编译期写死。设备首次启动需激活流程，服务器地址烧在 `config.json`/OTA 默认值里。
- 二进制协议有 v1(裸Opus)/v2(带时间戳,服务器AEC用)/v3 三种版本。

**自建服务器最小集**：实现 hello 握手 + 收 Opus + 下发 `tts start/stop` JSON + 下发 Opus 流，设备就能说话。参考 `docs/websocket.md` 逐字段对齐即可。

---

## 6. 魔改常见目标速查

| 目标 | 路径 |
|---|---|
| 换 TTS 音色/厂商 | 改服务器（设备零改动） |
| 完全离线跑 LLM+TTS | 不现实（ESP32 算力），但可局域网自建服务器，或只做本地命令词(MultiNet)替代部分对话 |
| 自定义唤醒词 | S3/P4/S31：`main/audio/wake_words/custom_wake_word.cc`（MultiNet 自定义短语）；或官方唤醒词工具 |
| 换提示音 | 替换 `main/assets/locales/<lang>/*.ogg`（保持 Opus-in-OGG 格式） |
| 加新屏幕/表情 | `main/display/`，字体与 glyph 推送见 `docs/glyph-push.md` |
| 给 AI 加设备控制能力 | `main/mcp_server.*` 注册 MCP 工具，见 `docs/mcp-usage.md` |
| 新板子移植 | `main/boards/` + `docs/custom-board.md`（config.json→build.py→Kconfig→CMakeLists 链条都要动） |
| 改对话状态/交互流 | `main/application.cc` 的 `OnIncomingJson` 与状态机 |

## 7. 构建备忘

```sh
# 需要 ESP-IDF ≥ v6.0.1（推荐 v6.1），IDF 5.x 不支持
source /path/to/esp-idf/export.sh
python3 scripts/build.py --list-boards          # 列出所有板子
python3 scripts/build.py <board-directory> --name <variant>   # 标准构建
python3 -m unittest discover -s scripts/tests   # 主机端测试
```

构建脚本会改写本地 `sdkconfig`，切板子后 build 目录不代表旧目标。不要手改 `build/ managed_components/ sdkconfig*` 等生成物。

## 8. 延伸阅读

- 官方音频架构文档：`main/audio/README.md`
- WebSocket 协议全文：`docs/websocket.md`（自建服务器必读）
- MCP 设备控制：`docs/mcp-protocol.md`、`docs/mcp-usage.md`
- 新板子指南：`docs/custom-board.md`

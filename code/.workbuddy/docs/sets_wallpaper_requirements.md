# sets 固件 1:1 复刻 + 服务端壁纸下发 —— 具体需求规格

| 项 | 值 |
|---|---|
| 版本 | v1.0 |
| 日期 | 2026-10-17 |
| 基线（上游 A） | `G:/demo/21_xiaozhi/hardware/small_secreen/xiaozhi-esp32` |
| 目标（B） | `G:/demo/21_xiaozhi/hardware/sets/xiaozhi-esp32` + `hardware/sets/boards/*` |
| 控制台 | `G:/demo/21_xiaozhi/yh/console-v2` |
| 服务端 | `G:/demo/21_xiaozhi/yh/manager-api`（Java）、`yh/xiaozhi-server`（Python） |
| 性质 | 需求规格（不含代码实现），全程只读核查 |

---

## 0. 结论摘要（先看这 6 条）

1. **"1:1 复刻"不是逐文件抄。** A 与 B 的 `main/` 实测只有 **13 项差异**（10 个文件内容不同 + 3 项目录增删），其中 **6 项是 B 领先**（人声打断播放保护窗、VAD 下降沿过滤、AEC 生效判定、websocket host 前缀解析修复）。这些**绝不可回退**。
2. **真正的复刻缺口只有一处：圆屏 UI 皮肤没有落地到 sets 版型。** `RoundScreenDisplay`（240×240 圆屏皮肤，`round_screen_display.cc`，330 行）在 B 的 `main/boards/my-s3-tft/` 里存在，但 **sets 的四套版型没有一套使用它**；硬件引脚完全相同的 `yh-n16r8-st7789` 用的是裸 `SpiLcdDisplay`（板实现仅 128 行）。
3. **服务端"下发"基础设施已建好约 80%。** `GET /ota/config/version`、`GET /ota/config/download`、`DeviceConfigFileService`（按设备返回任意 `device_config` JSON）、`POST /otaMag/uploadAssetsBin`（上传资源包返回一次性下载 URL）**均已存在**。缺的是固件端把 `config_download_url_` 这条死路径接上。
4. **壁纸推荐"单图 RGB565 + device_config 下发"**：避开 LVGL 解码器（仅 `LODEPNG`，无 JPEG）、单图 112.5 KB 放 PSRAM、即时生效；整包 assets 方案作为二期备选。
5. **控制台入口零路由改动**：`DockNav.vue` 内新增一个 `<button class="dock-item">`（**不是** `<router-link>`）+ `<Teleport to="body">` 浮层，满足"放在总控制台导航栏、禁止跳转新页面"。
6. **顺带发现 3 个必改缺陷**：① `Kconfig.projbuild:1078` 的 AEC 板型白名单漏了 `BOARD_TYPE_YUHE_SET_CAM` → `yh-cam` 勾了 AEC 也被静默丢弃；② 圆屏按**字节**截断 96（中文约 32 字，且可能切断 UTF-8）；③ YH `SEND_NOTIFY` 忙碌时仍回 `ACK ok`。

---

## 1. 范围与术语

| 术语 | 定义 |
|---|---|
| **A（基线）** | `hardware/small_secreen/xiaozhi-esp32`，用户认定的"功能与 UI 黄金标准" |
| **B（目标）** | `hardware/sets/xiaozhi-esp32` 固件副本 + `hardware/sets/boards/<id>` 版型源 |
| **`<FW>`** | B 的固件源码副本，即 `hardware/sets/xiaozhi-esp32` |
| **版型（set）** | `hardware/sets/boards/<id>/`，由 `sets/build.py` 同步进 `<FW>/main/boards/yuhe/<id>/` |
| **圆屏皮肤** | `RoundScreenDisplay`，240×240 安全区布局，深紫渐变 + 单气泡 + 中心 emoji + 顶栏时间/电量 |
| **壁纸** | 设备主屏背景图，当前是编译进固件的 `bg_good`（`good.jpg` → RGB565 C 数组） |

**不在本次范围**：
- 把 A 的 `main/boards/zhengchen/` 四个板目录整体搬进 B（B 的 `main/boards/yuhe/` 已**逐字节保留**这四个板，另加 4 个产品版，见 §2.4）。
- 修改 A 的源码（A 保持冻结，仅作比对基准）。
- 修改 `sets/build.py` / `flash.py` / `diag.py` 的编译烧录逻辑。

---

## 2. 现状核查（事实基线，全部带 file:line）

### 2.1 源码差异：13 项，其中 6 项 B 领先

`diff -rq A/main B/main`（排除 `managed_components`）结果：

| # | 文件 | 改动量 | 性质 | 处置 |
|---|---|---|---|---|
| 1 | `main/application.cc` | 44 行 | **B 领先**：`kSpeakingInterruptGuardMs` 播放保护窗 + `IsVoiceDetected()` 下降沿过滤 + `IsDeviceAecEffective()` 判定 + 去掉打断提示音 | **保留 B** |
| 2 | `main/audio/audio_service.h` | 11 行 | **B 领先**：`GetPlaybackElapsedMs()`、`IsDeviceAecEffective()`、`playback_start_us_` | **保留 B** |
| 3 | `main/audio/audio_service.cc` | 24 行 | 同上实现 | **保留 B** |
| 4 | `main/audio/audio_engine.h` | 4 行 | **B 领先**：`virtual bool IsAecEffective() const` | **保留 B** |
| 5 | `main/audio/engines/afe_audio_engine.h` | 13 行 | 同上实现 | **保留 B** |
| 6 | `main/audio/engines/afe_audio_engine.cc` | 50 行 | 同上实现 | **保留 B** |
| 7 | `main/protocols/websocket_protocol.cc` | 4 行 | **B 领先**：`host.erase(0, scheme_pos + 3)` 修正 `ws://` 前缀裁剪 bug | **保留 B** |
| 8 | `main/CMakeLists.txt` | **真实 39 行**（`diff` 报 2808 行是 **B=CRLF / A=LF** 造成的伪差异） | 4 处 `zhengchen`→`yuhe` 改名 + B 特有 `SETS-BOARDS-BEGIN/END` 块（B:885-906） | 机制差异，见 §2.5 |
| 9 | `main/Kconfig.projbuild` | **真实 90 行**（同样 CRLF 伪差异） | ①B 新增 `menu "YH Voice Interrupt Tuning"`（B:30-86，6 个 VAD/打断调参项）②改名 ③SETS-BOARDS 块（B:716-729） | B 领先 + 机制差异 |
| 10 | `main/boards/lckfb/szpi-esp32s3/config.json` | — | 版型元数据差异 | 记录，不处理 |
| 11 | `main/boards/yuhe/` | 仅 B 有 | sets 四套版型（yh-154tft-wifi / yh-big-ili9341 / yh-cam / yh-n16r8-st7789） | B 自有 |
| 12 | `main/boards/zhengchen/` | 仅 A 有 | A 的四块原始板（1.54tft-wifi / 1.54tft-ml307 / cam / cam-ml307） | 见 §2.4 等价性 |
| 13 | `main/boards/lckfb/szpi-esp32s3/README.md` | 仅 B 有 | 文档 | 忽略 |

**关键结论**：`main/boards/my-s3-tft/`（圆屏皮肤所在目录）**两边逐字节完全一致**（已 `diff -rq` 验证返回 IDENTICAL）。

### 2.2 硬件等价性：`yh-n16r8-st7789` ≡ `my-s3-tft`

| 项 | `my-s3-tft`（A） | `yh-n16r8-st7789`（B） | 是否一致 |
|---|---|---|---|
| LCD | SDA47 / SCL21 / RES45 / DC40 / CS41 / BL42 | 同左 | ✅ 完全一致 |
| 麦克风 INMP441 | WS4 / SCK5 / DIN6 | 同左 | ✅ |
| 功放 MAX98357A | DOUT7 / BCLK15 / LRCK16 | 同左 | ✅ |
| 屏幕 | ST7789 240×240 | ST7789 240×240 | ✅ |
| 音频架构 | `NoAudioCodecSimplex` 直驱 I2S | 同左 | ✅ |
| BOOT 键 | GPIO0 | GPIO0 | ✅ |
| **显示类** | **`RoundScreenDisplay`**（330 行板实现） | **`SpiLcdDisplay`**（128 行） | ❌ **UI 缺口** |
| SSD1306 备用屏回退 | 有（I2C 9/8，0x3C，可切 SH1106） | 无 | ❌ |
| 按键三事件（短按/双击/长按） | 有（`HandleKeyEvent`） | 无 | ❌ |
| 待机表情彩蛋（`NextEasterEgg`） | 有 | 无 | ❌ |
| 1 秒节拍 `Tick1s`（夜间睡觉/早晨问好/低电量） | 有（`esp_timer` 1s） | 无 | ❌ |
| PWM 背光 | 有（`PwmBacklight`，`GetBacklight()`） | 无 | ❌ |

> **这就是需求一的核心**：`yh-n16r8-st7789` 与 `my-s3-tft` 是**同一块硬件的两个名字**，但 UI 完全是两套。

### 2.3 圆屏 UI 规格（复刻目标参数）

来自 `round_screen_display.h:5-13` 与 `round_screen_display.cc`：

| 元素 | 参数（实测，非注释） | 行号 |
|---|---|---|
| 背景 | 垂直渐变 `0x2A1633` → `0x120B18`，叠 `bg_good` 图（240×240 RGB565） | :61-64 |
| 时间 | `LV_ALIGN_TOP_MID, 0, 10`，**16px**（`font_noto_sans_basic_16_4`，头文件注释写"14 号字"是**过时的**） | :67-72 |
| 电量 | `LV_ALIGN_TOP_MID, 0, 28`，16px | :74-79 |
| 中心表情 | `avatar_container` `LV_ALIGN_CENTER, 0, -15`；`emoji_label_` 用 `emoji_font()`；`emoji_image_` 默认隐藏 | :84-102 |
| 气泡 | `200×50`，`LV_ALIGN_BOTTOM_MID, 0, -55`，圆角 16，1px `#FF7AA2` 边框，底色 `#3A2440` @80%，`pad_all=4`，无滚动条 | :111-120 |
| 气泡文字 | 宽 180（**内容区仅 172**：200 − 2×4 pad − 2×1 border），`LV_LABEL_LONG_WRAP`，居中，16px，`#FFF7FB` | :122-129 |
| 底部提示 | `LV_ALIGN_BOTTOM_MID, 0, -12`，"短按说话  长按菜单"，`#8B7A99` | :132-136 |
| 隐藏占位族 | `container_` 1×1 隐藏、network/mute/battery/status/notification/low_battery/preview_image/chat_message_label | :143-188 |
| 文本截断 | **超 96 字节（非字符）静默截断** | :235-243 |
| 清屏语义 | 气泡恢复"我在呢"，不调基类（防 `bubble_label_` 悬空） | :246-255 |

**几何余量核算**：气泡底边 = 240 − 55 = **y=185**（绝对），气泡宽 200 在 y=185 处距屏幕外接圆边缘仅剩 **0.8 px** —— 换字体/加 padding 会直接溢出圆边。

**圆屏上恒为 `nullptr` 的基类对象**：`top_bar_` / `status_bar_` / `bottom_bar_` / `side_bar_` / `emoji_box_` —— 任何基类代码若解引用它们会崩溃，复刻时必须保持"不创建"这一事实并逐点回归。

颜色常量（`round_screen_display.h:57-63`）：

| 名称 | 值 | 用途 |
|---|---|---|
| `kColorBgTop` | `0x2A1633` | 渐变顶 |
| `kColorBgBottom` | `0x120B18` | 渐变底 |
| `kColorPrimary` | `0xFF7AA2` | 主粉（边框/强调） |
| `kColorBubbleBg` | `0x3A2440` | 气泡底（不透明度 80%） |
| `kColorTextMain` | `0xFFF7FB` | 主文字 |
| `kColorTextSub` | `0xC9B8D9` | 次文字 |
| `kColorTextHint` | `0x8B7A99` | 底部提示 |

#### 2.3.1 圆屏现有缺陷清单（复刻时必须明确"照抄还是修"）

| # | 缺陷 | 位置 | 实际影响 | 建议 |
|---|---|---|---|---|
| D1 | **按字节截断 96，不是按字符** | `:236-240` | 中文 ≈32 字；第 96 字节可能切半个 UTF-8 码点 → 显示乱码/空格 | **修**：改为按 UTF-8 码点截断，并提升到 ~72 字符（气泡实际容量） |
| D2 | 96 字节远超气泡可见容量 | `:235` | 180 宽 16px 每行约 11 汉字、3 行约 33 字 → 后 60 字节被裁在气泡外 | **修**：与 D1 合并处理 |
| D3 | 电量前缀 `⚡` 不在中文字库字符集 | `:334` | 部分固件显示豆腐块 | **修**：改用图标字体或纯数字 |
| D4 | `ClearChatMessages()` 把 `chat_message_label_` 置 `nullptr` | `:254` | 后续 `SetTheme` 若解引用会崩（与 2026-10-08 事故同源） | **修**：改为指向隐藏占位 |
| D5 | 底部提示 `y=-12` 在圆边可能被裁 | `:136` | 240×240 圆屏左下/右下切边 | **修**：缩短文案或内移到 `y=-18` |

> **需求裁定**：D1/D3/D4 属"会崩或会乱码"，**必须修**；D2/D5 属观感，可随壁纸需求一并优化。若坚持"像素级 1:1"，则 D1–D5 全部照抄——这是 §9.1 Q6 需要拍板的点。

### 2.4 板族等价性（`zhengchen` vs `yuhe`）

| A（zhengchen） | B（yuhe） | 关系 |
|---|---|---|
| `1.54tft-wifi` | `yuhe/1.54tft-wifi` + `yh-154tft-wifi` | 前者**逐字节改名保留**；后者是同硬件的产品版（多芯片高温弹窗） |
| `1.54tft-ml307` | `yuhe/1.54tft-ml307` | **逐字节改名保留**（含 4G 版） |
| `cam` | `yuhe/cam` + `yh-cam` | `cam` 逐字节保留；`yh-cam` 是产品版（PCA9557 + AEC） |
| `cam-ml307` | `yuhe/cam-ml307` | **逐字节改名保留** |

**审计实测**：4 对板的 `config.h` **逐字节完全相同**；`.cc` 归一化 `zhengchen→yuhe` 后差异为 **0 行**（仅 TAG/类名）；`config.json` 仅 `manufacturer/type/name` 改名。

> **结论**：`zhengchen/` 不需要搬进 B。B 的 `yuhe/` 是其**严格超集**（4 个原板逐字节保留 + 4 个产品版 yh-*），「1:1 复刻」在板级层面已满足。
>
> 但有一个**语义副作用**：板型名从 `zhengchen-*` 变成 `yuhe-*`，若服务端按 board type 下发配置/OTA，需同步映射（见 §9.1 Q7）。

### 2.5 sets 的架构硬约束（决定"怎么复刻"）

来自 `hardware/sets/SPEC.md`：

- `<FW>/main/` 由 `build.py` 统一维护，**禁止手工修改**（SPEC §6）。
- `sync_board()`（`build.py:429`）把 `boards/<id>/*.{c,cc,h,json}` 同步到 `<FW>/main/boards/yuhe/<id>/`。
- `register_boards()`（`build.py:692`）用 `# >>> SETS-BOARDS-BEGIN/END <<<` 标记块幂等维护 Kconfig/CMake。
- `config.json` 的 `type` / `builds[].name` **全局唯一**且 `type` 匹配 `^[a-z0-9.-]+$`。
- `config.json` 的 `sdkconfig_append` 是权威真源，`set.json` 的留 `[]`。

**因此"1:1 复刻"必须走两条腿**：
1. `<FW>/main/` 的公共源码保持与 A 同源（差异白名单见 §3.2）；
2. 版型差异（板实现、注册）走 `sets/boards/<id>/`，由 build.py 同步。

### 2.6 已知链路缺口（"复刻"前必须显式承认的 4 件事）

这 4 项在 A 里**就是残缺的**，1:1 复刻会把残缺一起复制过去。不做裁定就上线，会出现"以为有这个功能、实际跑不到"的误判。

| # | 缺口 | 证据 | 实际表现 | 建议 |
|---|---|---|---|---|
| **G1** | **MQTT 只有 Publish，没有 Subscribe** | `protocols/mqtt_protocol.cc` 仅实现发送，主题订阅未实现 | `mqtt_protocol.cc` 里的"协议实现"名存实亡，切到 MQTT 无法收指令；当前实际只有 WebSocket 可用 | **如实标注为"仅 WS 可用"**，MQTT 单独立需求 |
| **G2** | **人声打断默认不可达**（三条件串联） | ① `USE_DEVICE_AEC` 默认关（`Kconfig.projbuild:1078` 白名单不含 sets 板名，见 FR-1.5）② 默认 `listening_mode` 走 AutoStop 而非 Realtime ③ `application.cc:1330` 非 Realtime 或 AEC 未生效时 `EnableVoiceProcessing(false)` → VAD 关闭 | 默认配置下**说话打断不生效**，只能靠唤醒词打断。用户以为"打断已实现"，实测无效 | ① 修 FR-1.5；② 明确"要真打断 = 换有回采的板（yh-cam）+ 开 Realtime"；③ 在板上写死 `IsDeviceAecEffective()` 判据并在屏上给出提示 |
| **G3** | **`my-s3-tft` 板级无电量/充电/RTC/休眠** | `my_s3_tft_board.cc` 未实现 `GetBatteryLevel()`/`IsCharging()`/`GetBatteryVoltage()`/`SetPowerSaveLevel()` 覆写 | 圆屏顶部**电量永远不显示**；无低电量弹窗；无深度休眠 | 复刻时**不要假装有**：电量区按"无电池"隐藏；或另立需求加 ADC 检测 |
| **G4** | **YH `SEND_NOTIFY` 不校验设备状态** | `yh_protocol.cc:416-426` 只校验 `audio_url` 非空；MCP `ScheduleNotify` 会检查 idle | 忙碌时下发会被静默丢弃，且仍回 ACK `ok` → 服务端误判成功 | **修**：非 idle 时回 `NACK{reason:"busy"}`，与 MCP 语义对齐 |

> **需求裁定**：G1/G3 属"如实标注"，G2 属"必须修依赖 + 明确能力边界"，G4 属"必须修"（否则壁纸/通知的下发回执不可信，直接影响 §4 的 FR-2.5）。

---

## 3. 需求一：功能与 UI 的 1:1 复刻

### FR-1.1 公共源码同源（P0）

| 编号 | 需求 | 验收判据 |
|---|---|---|
| FR-1.1.1 | `<FW>/main/` 下除 `boards/`、`CMakeLists.txt` 注册块、`Kconfig.projbuild` 注册块外，所有文件必须与 A 的 `main/` 逐字节一致 | 提供只读比对脚本，输出差异数 = 0（白名单内除外） |
| FR-1.1.2 | 差异白名单**只允许** §2.1 表格中标注"机制差异/文档/版型元数据"的项 | 比对报告中无"内容不同"的业务代码文件 |
| FR-1.1.3 | B 领先的 6 项（打断加固、AEC 判定、websocket 修复）**禁止**被 A 覆盖 | 代码审查：`kSpeakingInterruptGuardMs`、`IsDeviceAecEffective`、`IsAecEffective`、`GetPlaybackElapsedMs`、`host.erase(0, scheme_pos + 3)` 均存在 |
| FR-1.1.4 | 不得通过手工编辑 `<FW>/main/` 实现复刻；如需改公共代码，须同时改 A 与 B 并记录 | git diff 中 `<FW>/main/` 无"仅 B 有"的业务改动 |

### FR-1.2 功能基线（P0）

以下功能必须在 B 的**可编译版型**上全部可用（与 A 同源，逐项验收）：

| 编号 | 功能域 | 功能点 | 实现位置 | 验收判据 |
|---|---|---|---|---|
| F01 | 通信 | WebSocket 文本 JSON + 二进制 Opus | `protocols/websocket_protocol.cc` | 能完成一轮 hello→listen→tts→goodbye |
| F02 | 通信 | MQTT 传输 | `protocols/mqtt_protocol.cc` | 切换后能连上 |
| F03 | 通信 | YH 旁路 TCP 12399（HELLO/ADVERTISEMENT/HEARTBEAT/COMMAND/ACK，白名单 SET_LED + SEND_NOTIFY） | `yh/yh_protocol.cc:50,210,416` | `nc` 手动发 COMMAND 收到 ACK |
| F04 | 唤醒 | 自定义唤醒词"你好小禾" | `config.json` 的 `CONFIG_CUSTOM_WAKE_WORD*` | 说唤醒词进 listening |
| F05 | 唤醒 | 服务器下发唤醒词（`device_config.wake_word`） | `application.cc:823+` | 改服务器配置后在线设备生效 |
| F06 | 打断 | 人声打断（VAD → AbortSpeaking → ResetDecoder → Listening） | `application.cc:323-350` | 播报中说话即停 |
| F07 | 打断 | 播放保护窗（前 N ms 忽略 VAD） | `application.cc:327-341` + `CONFIG_YH_INTERRUPT_GUARD_MS` | TTS 开头不被自己掐断 |
| F08 | 打断 | AEC 未生效时禁用"边播边听" | `application.cc:1330` | 无回采板不会自打断 |
| F09 | 通知 | WS `type:"notify"` + subtitles + priority | `application.cc:677-720` | 服务器下发即播报并显示字幕 |
| F10 | 通知 | 延迟/定时推送 `ScheduleNotify` + `NotifyTimerCallback` | `application.cc:1444-1482` | MCP 触发后延迟播报 |
| F11 | 通知 | 通知队列（容量 5，Normal/Urgent） | `notify/notify_player.h:18-19,74` | 连发 6 条按优先级播 |
| F12 | 通知 | YH `SEND_NOTIFY` | `yh/yh_protocol.cc:416-426` | 旁路命令触发播报 |
| F13 | 通知 | MCP `self.notify.send` | `mcp_server.cc` | 对话触发播报 |
| F14 | OTA | 启动版本检查 + 固件升级 + 进度显示 | `application.cc:523-575,1510+`；`ota.cc` | 服务器放新版本可升级 |
| F15 | OTA | assets 版本检查与整包下载 | `application.cc:463-521`；`assets.cc:489` | 设 `assets/download_url` 后启动会下载 |
| F16 | 音频 | 三任务拓扑 + Opus 编解码 + 播放代次防陈旧帧 | `audio/audio_service.cc` | 打断后无残留音频 |
| F17 | 音频 | AFE（AEC/VAD/WakeNet） | `audio/engines/afe_audio_engine.cc` | VAD 事件正常上报 |
| F18 | 状态机 | 全状态与合法转换 | `device_state_machine.cc` | 任意路径无非法转换日志 |
| F19 | MCP | 设备侧 JSON-RPC 工具集 | `mcp_server.cc` | 控制台能看到工具列表 |
| F20 | 按键 | BOOT 键短按/双击/长按 | `my_s3_tft_board.cc:193-251` | 三事件均有反馈 |
| F21 | 显示 | `SetChatMessage`/`SetStatus`/`SetEmotion`/`ShowNotification`/`SetTheme` | 见 FR-1.3 | 四类消息都能上屏 |
| F22 | 其他 | UDP 心跳、字形推送、多语言 | `application.cc` / `protocols/text_glyph_payload.cc` | 心跳有 ack；生僻字能显示 |

> **注意**：F02（MQTT）与 F06（人声打断）在 A 里即为**受限/不可达**状态，验收时按 §2.6 的口径判定（"如实标注"而非"必须可用"）。

### FR-1.3 UI 基线（P0）—— 圆屏皮肤必须在 sets 版型上可用

| 编号 | 需求 | 验收判据 |
|---|---|---|
| FR-1.3.1 | 至少一个可编译的 sets 版型使用 `RoundScreenDisplay` 作为主屏显示类 | 该版型 `config.h`/板 `.cc` 中 `new RoundScreenDisplay(...)`；串口日志 `RoundScreenDisplay` 初始化成功 |
| FR-1.3.2 | 布局参数与 §2.3 表格完全一致（时间/电量/表情/气泡/提示坐标与尺寸） | 截图与 A 设备逐像素比对（允许字体渲染 ±1px） |
| FR-1.3.3 | 颜色常量与 §2.3 表格一致 | 截图取色比对 RGB |
| FR-1.3.4 | 背景为 `bg_good` + 垂直渐变 | 待机截图背景与 A 一致 |
| FR-1.3.5 | 文本行为保持现状：气泡 200×50、宽 180、`LV_LABEL_LONG_WRAP`、**超 96 字符截断** | 输入 200 字文本，气泡显示前 96 字且完整落在气泡内 |
| FR-1.3.6 | 覆写函数行为与 A 一致：`SetChatMessage` 单气泡覆盖、`ClearChatMessages` 恢复"我在呢"、`ShowNotification` 落到气泡、`SetStatus` 映射气泡 | 逐项手测 |
| FR-1.3.7 | 隐藏占位族必须全部创建（防 `SetTheme` 空指针崩溃，2026-10-08 事故） | 激活/切换主题 10 次不崩溃 |
| FR-1.3.8 | `SetTheme` 重绑全部圆屏标签字体，并保留 `background_image()` 应用能力（为壁纸需求预留） | 切换 light/dark 无字体悬空崩溃 |

### FR-1.4 板级能力补齐（P0，针对 `yh-n16r8-st7789`）

| 编号 | 需求 | 说明 |
|---|---|---|
| FR-1.4.1 | `yh-n16r8-st7789` 改用 `RoundScreenDisplay` | 引脚与 `my-s3-tft` 完全一致，无需改 `config.h` 引脚 |
| FR-1.4.2 | 补齐 BOOT 键三事件处理（短按/双击/长按） | 双击 → `NextEasterEgg()`；长按 → 菜单/配网 |
| FR-1.4.3 | 补齐 1 秒节拍 `Tick1s()`（夜间睡觉/早晨问好/低电量提醒） | `esp_timer` 周期 1s |
| FR-1.4.4 | 补齐 PWM 背光（`PwmBacklight` + `GetBacklight()`） | 亮度可调、休眠关背光 |
| FR-1.4.5 | （可选，P2）SSD1306 备用屏回退 | 仅在需要兼容双屏硬件时实现 |
| FR-1.4.6 | 版型 `set.json` 的 `notes` 更新为"圆屏皮肤版" | build.py 选型时提示一致 |

### FR-1.5 修复 sets 自身的一处真实缺陷（P0，与复刻无关但必须一起修）

| 编号 | 需求 | 证据 | 验收 |
|---|---|---|---|
| FR-1.5.1 | `USE_DEVICE_AEC` 的 `depends on` 板型白名单必须包含 `BOARD_TYPE_YUHE_SET_CAM` | `main/Kconfig.projbuild:1078`：白名单只列了旧板名（`BOARD_TYPE_ZHENGCHEN_CAM` 等），**sets 的 `yh-cam` 勾选 AEC 会被静默丢弃** | menuconfig 里 `yh-cam` 版型能看到且能打开 `USE_DEVICE_AEC`；烧录后日志显示 AEC 生效 |
| FR-1.5.2 | `config.json` 里写了 `USE_DEVICE_AEC=y` 但 Kconfig 依赖不满足时，编译必须**报错或显式警告**，不能静默丢配置 | 同上 | 故意删依赖时编译输出出现警告 |

> 影响面：`yh-cam` 是四套版型里**唯一有 AEC 回采**的，此项失效会让它退化为"无 AEC"，直接导致 FR-1.2/F08（AEC 未生效时禁用边播边听）生效范围扩大、失去"边播边听"能力。

### FR-1.6 统一换行符（P1，工程卫生）

| 编号 | 需求 |
|---|---|
| FR-1.6.1 | `<FW>/main/CMakeLists.txt`、`main/Kconfig.projbuild` 统一为 **LF**（当前 B 是 CRLF，A 是 LF，导致每次 `diff` 报 2808/2245 行伪差异，掩盖真实改动） |
| FR-1.6.2 | 增加 `.gitattributes`（`*.cc/*.h/*.txt text eol=lf`；`*.py text eol=lf`），避免 Windows 端再次写入 CRLF |
| FR-1.6.3 | 换行统一后重新跑一次差异比对，真实差异应回落到 39/90 行 |

### NFR-1 复刻的非功能约束

| 编号 | 约束 |
|---|---|
| NFR-1.1 | **零回归**：B 现有的 6 项领先改动不得因复刻被删除或降级 |
| NFR-1.2 | **零破坏**：`application.cc` / 协议层 / MCP / 音频链路不做行为改动（只允许"读取 theme 背景"这类新增能力） |
| NFR-1.3 | 编译必须通过 `hardware/sets/build.py --board <id> --yes`；固件改动由用户手动编译烧录 |
| NFR-1.4 | 切换版型后必须删除 `<FW>/build` 全量重编（已知坑：半成品 build 会报 `component_requires.temp.cmake`） |
| NFR-1.5 | 复刻验收必须在**真机**上做（`flash.py` + `diag.py`），不能只看代码 |

---

## 4. 需求二：服务端下发自定义壁纸

### 4.1 能力现状（先说清楚哪些已经有了）

| 能力 | 是否已有 | 位置 |
|---|---|---|
| 按设备返回配置版本 + 下载地址 | ✅ **已有** | `OTAController.java:49-68` → `GET /ota/config/version?device_id=` |
| 按设备返回配置内容（任意 JSON） | ✅ **已有** | `OTAController.java:71-88` → `GET /ota/config/download` |
| 配置内容组装（`{device_id, server, device_config}`） | ✅ **已有** | `DeviceConfigFileServiceImpl.java:52-80` |
| 设备云端配置存库（自由 JSON） | ✅ **已有** | `DeviceConfigEntity.configJson` |
| 上传资源包并返回一次性下载 URL | ✅ **已有** | `OTAMagController.java:295-329` → `POST /otaMag/uploadAssetsBin` |
| 上传固件 | ✅ **已有** | `OTAMagController.java:244-293` → `POST /otaMag/upload` |
| 固件读取 `{version, download_url}` | ✅ **已有** | `ota.cc:252-292` `CheckConfigVersion` |
| **固件把 download_url 写进 NVS / 真正下载配置** | ❌ **缺（死路径）** | `ota.h:40` 的 `GetConfigDownloadUrl()` **无调用者**；`application.cc:440-445` 只有注释 |
| **壁纸字段** | ❌ 缺 | 全仓 grep `wallpaper` 零命中 |
| **圆屏应用壁纸** | ❌ 缺 | `round_screen_display.cc:61` 硬编码 `bg_good`；`container_` 是 1×1 隐藏占位（:143-146） |
| **壁纸管理接口/任务表** | ❌ 缺 | — |

### 4.2 功能需求

| 编号 | 需求 | 优先级 |
|---|---|---|
| FR-2.1 | 管理员可上传壁纸（PNG/JPG/WebP），服务端**统一转码**为设备可直接渲染的格式 | P1 |
| FR-2.2 | 可维护壁纸库（列表/预览/删除），带缩略图 | P1 |
| FR-2.3 | 可选择下发目标：单设备 / 设备组 / 全部 | P1 |
| FR-2.4 | 下发后**在线设备 5 秒内**背景变更，**无需重启、无需重烧固件** | P1 |
| FR-2.5 | 下发有结果回执（pending/sent/acked/failed + 原因），控制台可见 | P1 |
| FR-2.6 | 失败自动回退到 `bg_good`，不影响启动与对话 | P1 |
| FR-2.7 | 支持"恢复默认壁纸"指令 | P1 |
| FR-2.8 | 壁纸与 light/dark 主题可分别设置（对齐 assets 的 `skin.light/dark`） | P2 |
| FR-2.9 | 掉电/重启后壁纸保持 | P2 |
| FR-2.10 | 支持按设备配置（`device_config`）永久绑定，而非仅一次性推送 | P2 |

### 4.3 技术方案选择（三选一，推荐 B）

| 维度 | 方案 A：assets 整包 | **方案 B：单图下发（推荐）** | 方案 C：独立分区 |
|---|---|---|---|
| 传输量 | 数 MB（整包） | **112.5 KB（240×240 RGB565）** | 112.5 KB |
| 生效时机 | 仅开机（`CheckAssetsVersion` 每启动一次，`assets_version_checked_`） | **即时（WS 消息）** | 即时 |
| 持久化 | ✅ 天然（写分区） | ❌ 首期易失（PSRAM） | ✅ |
| 分区表改动 | 无 | 无 | **必须改，且现有分区表已用满 16 MB（`END = 0x1000000`，剩余 0 字节）→ 需把 assets 从 8M 缩到 7M** |
| 图像格式 | 任意（随包，工具预转） | RGB565 `.bin`（首选）或 PNG（需验证内存解码） | RGB565 |
| 回滚粒度 | 整包（坏图废掉字体/表情） | 单图 | 单图 |
| 存量设备兼容 | ✅ | ✅ | ❌（分区表随 bootloader 固化，需串口重烧） |

**推荐：B 首期 + C 二期（仅新批次设备）**，A 不单独做（换一张图要重下整包，触发时机最死）。

### 4.4 图像格式与内存（硬约束）

| 项 | 结论 |
|---|---|
| LVGL 解码器 | `sdkconfig` 仅 `CONFIG_LV_USE_LODEPNG=y`（PNG）；**无 TJPGD(JPEG)/SJPG/GIF**；`CONFIG_LV_BIN_DECODER_RAM_LOAD` 未开 |
| 首选格式 | **RGB565 raw `.bin`，240×240 = 115,200 字节**，配 MD5/CRC32 |
| 为什么不用 PNG | 需从内存缓冲解码到 RAM 再构造 `lv_image_dsc_t`，中间峰值高、路径未验证；RGB565 直接可用 |
| 现成渲染类型 | `LvglRawImage(void* data, size_t size)`（`lvgl_image.h:13-18`）—— 正是运行时原始图格式 |
| 内存 | PSRAM 已开（`CONFIG_SPIRAM=y` + `SPIRAM_MODE_OCT=y`），115 KB 无压力 |
| 服务端责任 | 上传时校验/裁剪为 240×240，转 RGB565，算 MD5，生成缩略图 |
| 大小上限 | 单图 ≤ 200 KB（防滥用）；PNG 源 ≤ 2 MB |

### 4.5 下发协议（推荐走现有 `device_config` 通道）

**为什么不用新 WS type？** `device_config` 已存在、已有版本语义（`cfg-<sha256前12位>`）、已按设备下发（`DeviceConfigFileServiceImpl`），复用它零新增协议面。

服务端在 `device_config` 里增加一个 `wallpaper` 对象：

```json
{
  "device_id": "AA:BB:CC:DD:EE:FF",
  "server": { "ota": "...", "websocket": "..." },
  "device_config": {
    "wallpaper": {
      "version": "3",
      "url": "http://host:8002/xiaozhi/otaMag/download/<uuid>",
      "md5": "9f2c...",
      "size": 115200,
      "width": 240,
      "height": 240,
      "format": "rgb565",
      "fit": "cover",
      "scope": "light"
    }
  }
}
```

可选：一次性即时推送（不等下次启动）用 WS 文本帧：

```json
{ "type": "wallpaper", "action": "set", "version": "3", "url": "...", "md5": "...", "size": 115200, "format": "rgb565" }
{ "type": "wallpaper", "action": "clear" }
```

设备回执：

```json
{ "type": "wallpaper", "action": "result", "version": "3", "status": "ok" }
{ "type": "wallpaper", "action": "result", "version": "3", "status": "fail", "reason": "md5_mismatch" }
```

### 4.6 设备端行为需求

| 编号 | 需求 |
|---|---|
| FR-2.11 | 收到 `wallpaper.set` 后：校验 version 是否已应用 → 下载 → 校验 MD5 与长度 → 载入 PSRAM → 应用 → 回执 |
| FR-2.12 | 下载期间不阻塞对话；若正在 Speaking，延后到 idle（或按 `applyMode` 决定） |
| FR-2.13 | 应用时持 `DisplayLockGuard`，通过 `lv_obj_set_style_bg_image_src(screen, dsc, 0)` 替换背景 |
| FR-2.14 | 任一步失败 → 不改屏幕，保持当前壁纸/`bg_good`，回执 `fail:<reason>` |
| FR-2.15 | `wallpaper.clear` → 恢复 `bg_good` + 渐变 |
| FR-2.16 | 版本号存 NVS（`wallpaper/version`、`wallpaper/url`、`wallpaper/md5`），重启后若 URL 可达则重拉 |
| FR-2.17 | 壁纸优先级：**用户壁纸 > `theme.background_image` > `bg_good`** |
| FR-2.18 | 壁纸不改动中心 emoji 容器与气泡，`SetEmotion`/`SetChatMessage` 行为不变 |

### 4.7 渲染点改造需求（圆屏）

| 编号 | 需求 |
|---|---|
| FR-2.19 | `RoundScreenDisplay` 新增 `void SetWallpaper(LvglImage* img)` 与 `void ClearWallpaper()` |
| FR-2.20 | `BuildMainScreen()` 中把 `:61` 的硬编码改为"有壁纸用壁纸，否则 `bg_good`" |
| FR-2.21 | `SetTheme()` 末尾（`:271-296`）重新应用壁纸（主题切换后不丢） |
| FR-2.22 | 壁纸图生命周期由 `WallpaperManager` 持有，`RoundScreenDisplay` 只持裸 `lv_img_dsc_t*`，析构前必须 `ClearWallpaper()`（防悬空） |
| FR-2.23 | 240×240 圆屏安全区：壁纸按 `cover` 裁剪显示，不做圆角遮罩（屏本身是圆的） |

### 4.8 接口契约（manager-api）

| # | 端点 | 方法 | 请求 | 响应 `data` | 状态 |
|---|---|---|---|---|---|
| 1 | `/wallpaperMag/upload` | POST | multipart `file`、`name` | `{id,name,url,thumbUrl,md5,size,width,height,format}` | 新增 |
| 2 | `/wallpaperMag` | GET | `page,limit,keyword` | `{list:[...],total}` | 新增 |
| 3 | `/wallpaperMag/{id}` | DELETE | — | — | 新增 |
| 4 | `/wallpaperMag/dispatch` | POST | `{wallpaperId,targetType:"devices"\|"group"\|"all",deviceIds[],agentIds[],applyMode:"immediate"\|"next_boot"}` | `{taskId}` | 新增 |
| 5 | `/wallpaperMag/task/{taskId}` | GET | — | `{status,total,sent,success,failed,devices:[{deviceId,mac,status,error}]}` | 新增 |
| 6 | `/wallpaperMag/task/{taskId}/retry` | POST | `{deviceIds[]}` | `{taskId}` | 新增 |
| 7 | `/ota/config/version` | GET | `device_id` | `{version,download_url}` | **已有** |
| 8 | `/ota/config/download` | GET | `device_id` | `{device_id,server,device_config}` | **已有** |
| 9 | `/otaMag/uploadAssetsBin` | POST | multipart `file` | 一次性下载 URL | **已有**（方案 A 用） |

鉴权：`Authorization: Bearer <sys_user_token>`；上传/下发需 `sys:role:normal` 以上（沿用 `OTAMagController` 的 `@RequiresPermissions`）。
错误码：`0` 成功 / `401` 未登录 / `403` 越权 / `10230` 参数非法；建议新增 `10401` 壁纸不存在、`10402` 设备不可达、`10403` 格式或大小超限。

### 4.9 数据模型（建议）

```sql
-- 壁纸库
ai_wallpaper(id, name, url, thumb_url, md5, size, width, height, format,
             scope ENUM('light','dark','both'), creator, create_date)

-- 下发任务
ai_wallpaper_task(id, wallpaper_id, target_type, target_ids JSON,
                  apply_mode, status, total, sent, success, failed,
                  creator, create_date)

-- 任务明细
ai_wallpaper_task_device(id, task_id, device_id, status, error, ack_time)
```

设备绑定：复用 `ai_device_config.config_json`，写入 `{"wallpaper":{"version":..,"url":..}}` —— **无需新表**即可实现 FR-2.10。

---

## 5. 需求三：控制台导航栏壁纸入口

### 5.1 硬约束

| 编号 | 约束 |
|---|---|
| FR-3.1 | 入口必须在**总控制台导航栏**（`src/components/DockNav.vue`）内 |
| FR-3.2 | **禁止跳转新页面**：不得新增路由、不得 `router.push`、不得新增 `views/` 下的页面文件、不得改变 `route.path` |
| FR-3.3 | 点击后在**就地浮层**完成全部操作 |
| FR-3.4 | 仅管理员可见（`hasAdminRole(userState)`，已含 `superAdmin===1`） |
| FR-3.5 | 不改 `global.css`、不改 `main.js`、不改 `TopBar.vue`（避免污染与路由映射） |

### 5.2 入口落位与元素

| 项 | 规格 |
|---|---|
| 位置 | `DockNav.vue` 第 21 行（"固件烧录"）之后、`.dock-foot`（第 22 行）之前 |
| 元素 | `<button type="button" class="dock-item" :class="{active: open}" @click="open = true">` |
| 图标 | `🎨`（`🖼` 已被"展示配置"占用，不复用） |
| 文案 | 「壁纸下发」 |
| 折叠态 | 保留 `<span class="dock-label">壁纸下发</span>`（靠 `global.css:334` 隐藏，**不能用 `v-if`**，否则 `.dock` 宽度塌陷）+ `title` 提示 |
| 窄屏 | ≤900px 自动只剩图标（`global.css:348-349`），点击区约 40×40 |
| 可见条件 | `role === 'admin' && hasAdminRole(userState.value)`，用 `computed` 实时判断（`userState` 是登录后异步补全的），未知态**不显示**（fail-closed） |
| 路由 | **零改动**：不进 `adminItems` 数组、不包 `<router-link>`、不注册 route、不进 TopBar 搜索映射 |

### 5.3 浮层面板

| 项 | 规格 |
|---|---|
| 形式 | 居中 Modal，**`<Teleport to="body">`**（必须：`.dock` 有 `backdrop-filter: blur(18px)` + `overflow-y: auto`，会成为 fixed 定位的包含块，写在 `<nav>` 内会被裁成 56–140px 宽） |
| 尺寸 | `width: min(920px, 94vw); max-height: 88vh`，body 双栏 `320px | 1fr` |
| z-index | **140**（压住 dock=50，放行 Toasts=200，让 App 全局确认框 150 可覆盖） |
| 关闭 | `@click.self` + `ESC`；下发中关闭需二次确认（"任务已提交，关闭不影响后台下发"） |
| 样式 | 自带 `<style scoped>` 的 `.modal-overlay/.modal-header/.modal-body/.modal-footer`（`PushScheduler.vue:406-412` 是 scoped，不可跨组件复用），底色用 `var(--surface)` 不用 `#fff`（暗色主题） |

**三步流程（同一浮层内切换，不分页）**：

1. **选择目标**：Tab「按设备 / 按组 / 全部」；远程搜索（`GET /admin/device/all`）+ 勾选；底栏「已选 N 台，在线 M 台」。
2. **选择壁纸**：Tab「服务器库 / 上传新图」；4 列卡片（缩略图 + 名称 + 分辨率 + 大小）；上传 `input[type=file]`（沿用 `Ota.vue:9-12` 范式）；右侧 240×240 预览 + `cover/contain` 选择。
3. **下发与结果**：汇总条（总数/成功/失败/处理中）+ 进度条（`PushScheduler.vue:47-51`）+ 每设备状态行；失败可单条/批量重试。

**状态机**：`idle → target（空态/加载/有数据）→ wallpaper（空库/上传中/已选）→ dispatching（2s 轮询，90s 超时）→ done（全成功 | 部分失败）`；`done` 可「再来一次」重置。

### 5.4 改动文件清单

| 文件 | 类型 | 改动点 |
|---|---|---|
| `src/components/DockNav.vue` | 修改 | ① 模板插入 1 个 `<button>`；② 引入 `WallpaperDispatch`、`wallpaperOpen = ref(false)`、`canManageWallpaper` computed；③ 样式不动 |
| `src/components/WallpaperDispatch.vue` | **新增** | 全部浮层逻辑（预计 500–600 行，超出再拆 `WallpaperPicker.vue` / `DevicePicker.vue`） |
| `src/lib/api.js` | 修改 | 新增独立导出 `wallpaperApi = { page, upload, remove, dispatch, task, retry, cancel }`（**不再塞进已 490 行的 `adminApi`**） |
| `src/lib/apiCatalog.js` | 修改（可选） | 登记 6 条新端点，供 `/admin/apis` 调试页展示 |
| `src/main.js` | **不改** | 硬约束：不新增路由 |
| `src/styles/global.css` | **不改** | 新样式全部留在组件 scoped 内 |

---

## 6. 非功能需求（NFR）

| 编号 | 类别 | 要求 |
|---|---|---|
| NFR-2 | 中断 | 壁纸下载不得阻塞语音链路；下载期间允许正常对话 |
| NFR-3 | 内存 | 峰值增量 ≤ 256 KB（RGB565 115 KB + 校验缓冲），全部走 PSRAM |
| NFR-4 | 时延 | 在线设备从"下发"到"屏幕变更" ≤ 5 s（含 115 KB 下载） |
| NFR-5 | 幂等 | 同一 `version` 重复下发不重复下载/重复写 NVS |
| NFR-6 | 容错 | 服务端不可达、MD5 不符、尺寸不符、内存不足 → 全部回退 `bg_good`，**不得重启或崩溃** |
| NFR-7 | 安全 | 上传鉴权 + 单图大小上限 + 格式白名单（PNG/JPG/WebP）+ 服务端强制转码 |
| NFR-8 | 可观测 | 设备端打印 `wallpaper: download/verify/apply` 三段日志；服务端记录任务与失败原因 |
| NFR-9 | 兼容 | 老固件（无壁纸能力）收到 `wallpaper` 字段必须忽略，不报错、不影响对话 |
| NFR-10 | 编译 | 固件改动由用户手动 `idf.py build`；不得由脚本代跑 |

---

## 7. 验收标准（可勾选）

### 7.1 复刻

- [ ] AC-01 `<FW>/main/` 与 A 的差异仅剩白名单项（比对脚本报告 0 个业务文件差异）
- [ ] AC-02 `yh-n16r8-st7789` 版型编译通过，串口日志显示 `RoundScreenDisplay` 初始化
- [ ] AC-03 待机界面与 A 设备截图逐像素一致（时间/电量/表情/气泡/提示/渐变背景）
- [ ] AC-04 说唤醒词 → 进 listening → 气泡显示识别文本
- [ ] AC-05 TTS 播报中说话 → 立即中断（保护窗生效，开头 800ms 内不自打断）
- [ ] AC-06 服务器 notify 下发 → 播报 + 气泡显示字幕
- [ ] AC-07 长按/短按/双击 BOOT 键均有对应反馈，双击触发表情彩蛋
- [ ] AC-08 放置 1 小时，`Tick1s` 的夜间/低电量提示按时触发
- [ ] AC-09 切换 light/dark 主题 10 次不崩溃、气泡字体正常
- [ ] AC-10 6 项 B 领先改动全部在位（代码审查 + 行为验证）
- [ ] AC-11 `yh-cam` 版型在 menuconfig 中可勾选 `USE_DEVICE_AEC` 且烧录后日志确认 AEC 生效（FR-1.5）
- [ ] AC-12 `CMakeLists.txt` / `Kconfig.projbuild` 为 LF，差异比对真实行数回落到 39/90（FR-1.6）
- [ ] AC-13 圆屏 D1/D3/D4 缺陷已修：中文长文本无乱码、电量无豆腐块、切换主题 10 次不崩
- [ ] AC-14 YH `SEND_NOTIFY` 在忙碌时回 `NACK{busy}` 而非 `ACK ok`（G4）
- [ ] AC-15 无电池的板上电量区按"隐藏"处理，不显示 `0%`（G3）

### 7.2 壁纸

- [ ] AC-21 控制台导航栏出现「壁纸下发」入口，点击**不跳转路由**（URL 不变）
- [ ] AC-22 上传一张 240×240 图 → 下发到 1 台在线设备 → 5 s 内屏幕背景变更
- [ ] AC-23 设备回执 `ok` 出现在任务详情，控制台显示"已确认"
- [ ] AC-24 断网/篡改 MD5 下发 → 屏幕不变、回执 `fail:<reason>`、设备不重启
- [ ] AC-25 下发 `clear` → 恢复 `bg_good` 渐变背景
- [ ] AC-26 连续换 3 张图 → 每次都正确切换（证明非一次性）
- [ ] AC-27 下发壁纸后说唤醒词对话，气泡与表情显示正常（壁纸不影响 UI 层）
- [ ] AC-28 非管理员账号看不到入口；customer 端看不到入口
- [ ] AC-29 导航栏折叠态显示 `🎨` 图标 + tooltip，点击仍可打开浮层
- [ ] AC-30 浮层打开时 URL 不变、无新页面加载、按 ESC 可关闭

---

## 8. 实施顺序建议

| 阶段 | 内容 | 依赖 | 风险 |
|---|---|---|---|
| **P0-1** | `yh-n16r8-st7789` 改用 `RoundScreenDisplay` + 补齐按键/节拍/背光（FR-1.3、FR-1.4） | 无 | 中（需真机验证布局） |
| **P0-2** | 修 `USE_DEVICE_AEC` 白名单（FR-1.5）+ 统一 LF（FR-1.6） | 无 | 低（但影响 yh-cam 能否真打断） |
| **P0-3** | 修圆屏 D1/D3/D4 缺陷 + YH `SEND_NOTIFY` 忙碌回 NACK（§2.6 G4） | 无 | 低 |
| **P0-4** | `<FW>/main/` 同源核对，产出差异比对脚本（FR-1.1） | 无 | 低 |
| **P1-1** | 固件：`WallpaperManager` + `SetWallpaper` + `SetTheme` 重设（FR-2.19~2.23） | P0-1 | 中（图生命周期） |
| **P1-2** | 固件：`device_config.wallpaper` 解析 + WS `wallpaper` 消息（FR-2.11~2.18） | P1-1 | 中 |
| **P1-3** | 服务端：壁纸 CRUD + 转码 + 任务表 + `device_config` 注入（§4.8/4.9） | 无 | 中 |
| **P1-4** | 控制台：DockNav 入口 + `WallpaperDispatch.vue`（§5） | P1-3 | 中（Teleport/权限/轮询） |
| **P2-1** | 持久化（方案 C：assets 7M + wallpaper 1M 分区） | 新批次硬件 | **高**（存量设备需串口重烧） |
| **P2-2** | light/dark 双壁纸、按设备永久绑定 | P1 全通 | 低 |

---

## 9. 风险与开放问题

### 9.1 必须先拍板的 8 个问题

| # | 问题 | 影响 |
|---|---|---|
| Q1 | **"1:1 复刻"是否允许保留 sets 的 6 项领先改动？** | 若要求"逐字节一致"，则要回退打断加固（会重现"播到一半被自己掐断"的故障）—— 建议不允许 |
| Q2 | **壁纸是否要求掉电保持？** | 要求 → 必须做方案 C（改分区表，assets 8M→7M，存量设备串口重烧）；不要求 → 首期 PSRAM 即可 |
| Q3 | **壁纸是"整机一张"还是"每设备可不同"？** | 影响数据模型（是否要 `ai_wallpaper_bind` 表） |
| Q4 | **目标设备是 `yh-n16r8-st7789` 还是 `yh-154tft-wifi`？** | 前者与 `my-s3-tft` 引脚完全一致，可零硬件改动复刻；后者屏幕/按键/电池都不同，布局要重算 |
| Q5 | **壁纸是否要支持 GIF/多帧轮播？** | 当前 `CONFIG_LV_USE_GIF` 未开，做轮播需额外开功能并占 RAM |
| Q6 | **圆屏 D1–D5 缺陷照抄还是修？** | D1/D3/D4 会乱码或崩溃，建议必修；D2/D5 是观感，可修可留 |
| Q7 | **板型名从 `zhengchen-*` 改为 `yuhe-*`，服务端是否按 board type 做过匹配？** | 若 OTA/配置下发按 `board.type` 匹配，改名会让老设备匹配不到新固件包 |
| Q8 | **人声打断是否要做成"默认可用"？** | 现状默认不可达（§2.6 G2）。要做成默认可用 = 必须上有回采的板（yh-cam）+ 开 Realtime，或在软件上另做 VAD 方案 |

### 9.2 技术风险清单

| 风险 | 说明 | 缓解 |
|---|---|---|
| R1 | `.dock` 的 `backdrop-filter` 使浮层被裁切 | 强制 `<Teleport to="body">` |
| R2 | 入口误写成 `<router-link>` → 跳 404 | 用 `<button type="button">`，代码审查 |
| R3 | 折叠态用 `v-if` 隐藏文字 → dock 宽度塌陷 | 保留 `.dock-label` span |
| R4 | `userState` 异步 → 入口闪一下或误显示 | 用 `computed` + fail-closed |
| R5 | 轮询未清理 → 内存/请求泄漏 | `onUnmounted` + 关闭时 `clearInterval` + 90s 超时 |
| R6 | 壁纸 `lv_img_dsc_t` 悬空导致死机 | `WallpaperManager` 持所有权，析构前 `ClearWallpaper()` |
| R7 | 壁纸写 assets 分区 → 与整包管理冲突 | **禁止**写 assets，走 PSRAM 或独立分区 |
| R8 | 分区表已用满 16 MB（`END = 0x1000000`，剩余 0 字节） | 方案 C 必须把 assets 从 8M 缩到 7M，并接受存量设备重烧 |
| R9 | 老固件收到未知 `wallpaper` 字段 | 服务端注入字段前先按固件版本白名单；固件侧未知字段忽略 |
| R10 | 切换版型后未删 `<FW>/build` → 编译报 `component_requires.temp.cmake` | 每次切版型删 build 目录（已知坑） |

---

## 10. 附：可直接复用的既有资产

| 资产 | 位置 | 用途 |
|---|---|---|
| 圆屏皮肤实现 | `main/boards/my-s3-tft/round_screen_display.{h,cc}` | 直接复制进 `sets/boards/yh-n16r8-st7789/` 后改名 |
| 板实现（含按键/节拍/背光/SSD1306） | `main/boards/my-s3-tft/my_s3_tft_board.cc`（330 行） | 复制后改类名为 `YhSetN16R8Board` |
| 背景图 | `main/boards/my-s3-tft/good_bg.c`（`bg_good`，240×240 RGB565） | 作为默认壁纸 |
| 运行时图像类型 | `main/display/lvgl_display/lvgl_image.h:13` `LvglRawImage` | 壁纸解码后的载体 |
| 设备配置通道 | `DeviceConfigFileServiceImpl.java:52` | `device_config` 注入壁纸字段 |
| 资源上传接口 | `OTAMagController.java:295` `/otaMag/uploadAssetsBin` | 方案 A 的资源包上传 |
| 弹窗样式范式 | `views/admin/PushScheduler.vue:406-412` | 浮层样式复制源 |
| 进度条范式 | `views/admin/PushScheduler.vue:47-51` | 下发进度 |
| 设备列表接口 | `GET /admin/device/all`（`api.js:349`） | 目标选择器数据源 |

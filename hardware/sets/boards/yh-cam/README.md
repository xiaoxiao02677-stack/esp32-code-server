# 屿禾 AI Camera（摄像头版）· `yh-cam`

> 目录：`hardware/sets/boards/yh-cam`
> 同步目标：`<FW>/main/boards/yuhe/yh-cam`
> Kconfig 符号：`BOARD_TYPE_YUHE_SET_CAM`（menuconfig 显示 `Yuhe AI Camera (sets)`）
> 类名：`YhSetCamBoard` ｜ 迁移自 `<FW>/main/boards/yuhe/cam`（原 `YuheCamBoard`）

---

## 1. 版型简介

ESP32-S3（N16R8，必须带 PSRAM）+ OV2640 摄像头 + ES8311（播放）/ ES7210（麦克风阵列，带 AEC 回采）
+ ST7789 320×240 SPI 屏，功放与摄像头电源由 PCA9557 IO 扩展控制。
屿禾科技小智 AI 魔改版，支持语音唤醒、对话打断、拍照识物、OTA。

编译产物名：`yh-cam`。

---

## 2. 文件清单

| 文件 | 说明 |
|---|---|
| `set.json` | build.py 菜单元数据 |
| `config.json` | 固件 `scripts/build.py` 读取；`type`/`builds[0].name` = `yh-cam` |
| `config.h` | 全部引脚与参数宏 |
| `yh_set_cam_board.cc` | 板实现，末尾 `DECLARE_BOARD(YhSetCamBoard);` |
| `power_manager.h` | 电池 ADC / 充电检测 / 片内温度传感器 |
| `mcp_controller.cc` | AEC 模式切换与重启的 MCP 工具注册 |
| `README.md` | 本文件 |

---

## 3. GPIO 全表（ESP32-S3 → 外设）

| GPIO | 外设 | 信号 | 方向 | 备注 |
|:---:|---|---|:---:|---|
| **0** | 按键 | BOOT / 配网键 | IN | Strapping，上电勿拉低 |
| **1** | I2C1 | SDA | I/O | 音频 codec + PCA9557 + 摄像头 SCCB **共用** |
| **2** | I2C1 | SCL | I/O | 同上 |
| **3** | 按键 | VOLUME_UP | IN | Strapping（JTAG 源选择） |
| **4** | 摄像头 | D1（Y3） | IN | |
| **5** | 摄像头 | D2（Y4） | IN | |
| **6** | 摄像头 | D3（Y5） | IN | |
| **7** | 摄像头 | D0（Y2） | IN | |
| **8** | 摄像头 | D4（Y6） | IN | |
| **9** | 摄像头 | D5（Y7） | IN | |
| **10** | 电池检测 | ADC1_CH9 | AIN | 电池电压采样 |
| **11** | 摄像头 | D6（Y8） | IN | |
| **12** | I2S | DIN（麦克风数据入） | IN | ESP32 ← codec |
| **13** | I2S | WS（LRCK） | OUT | |
| **14** | I2S | BCLK | OUT | |
| **15** | 摄像头 | D7（Y9） | IN | |
| **16** | 摄像头 | PCLK | IN | |
| **17** | 摄像头 | XCLK | OUT | 24 MHz（LEDC 产生，S3 实际不用 LEDC） |
| **18** | 摄像头 | HREF | IN | |
| 19 | — | USB D- | — | 保留 |
| 20 | — | USB D+ | — | 保留 |
| **21** | 摄像头 | VSYNC | IN | |
| 26–37 | — | — | — | **禁用**：Flash / PSRAM 总线 |
| **38** | I2S | MCLK | OUT | ES8311/ES7210 主时钟 |
| **39** | LCD | DC | OUT | |
| **40** | LCD | MOSI | OUT | SPI3 |
| **41** | LCD | SCLK | OUT | SPI3 |
| **42** | LCD | BL 背光 | OUT | PWM，**反相**（低电平点亮） |
| **45** | I2S | DOUT（喇叭） | OUT | Strapping |
| **46** | 按键 | VOLUME_DOWN | IN | Strapping |
| **47** | 电源管理 | 充电检测 | IN | 高电平 = 充电中 |
| **48** | LED | 板载指示灯 | OUT | 单色 LED |

---

## 4. 外设明细

### 4.1 显示屏 —— ST7789（SPI3）

| 信号 | GPIO | 说明 |
|---|:---:|---|
| SCLK | 41 | SPI3_CLK |
| MOSI | 40 | SPI3_MOSI（`miso` 未接） |
| DC | 39 | 数据/命令 |
| CS | — | **不接**（`GPIO_NUM_NC`） |
| RST | — | **不接**，由 PCA9557 P0 控制 |
| BL | 42 | PWM，**输出反相** |
| 总线 | — | `SPI3_HOST`，DMA 自动通道 |

- 像素时钟 80 MHz，RGB 顺序，16 bpp，偏移 X=0 / Y=0，`invert_color = true`
- 方向由 NVS 命名空间 `lcd_display` 的 `lcd_mode` 切换：

| 模式 | 宽×高 | SWAP_XY | MIRROR_X | MIRROR_Y |
|---|:---:|:---:|:---:|:---:|
| 横屏（默认 `lcd_mode=1`） | 320 × 240 | `true` | `true` | `false` |
| 竖屏（`lcd_mode=0`） | 240 × 320 | `false` | `false` | `false` |

### 4.2 音频 —— ES8311（播放）+ ES7210（麦克风阵列）

| 项 | 值 |
|---|---|
| 控制总线 | I2C1（SDA=1, SCL=2） |
| ES8311 地址 | **0x30**（8-bit 写地址形式；7-bit = 0x18） |
| ES7210 地址 | **0x82**（8-bit 形式；7-bit = 0x41） |
| 采样率 | 输入 / 输出均 24000 Hz |
| AEC 回采 | `AUDIO_INPUT_REFERENCE = true` |
| PA 使能 | PCA9557 **P1**（`CustomAudioCodec::EnableOutput()` 里控制） |

I2S 引脚：MCLK=38，BCLK=14，WS=13，DIN=12，DOUT=45。
`AUDIO_CODEC_USE_PCA9557` 已启用 —— 播报前必须先把 P1 置 1，否则无声。

### 4.3 摄像头 —— OV2640（DVP 8-bit）

| 信号 | GPIO | 信号 | GPIO |
|---|:---:|---|:---:|
| XCLK | 17 | D7 | 15 |
| PCLK | 16 | D6 | 11 |
| VSYNC | 21 | D5 | 9 |
| HREF | 18 | D4 | 8 |
| SIOD (SDA) | 1 | D3 | 6 |
| SIOC (SCL) | 2 | D2 | 5 |
| PWDN | 未接 (-1) | D1 | 4 |
| RESET | 未接 (-1) | D0 | 7 |

- XCLK 24 MHz；SCCB 复用 **I2C1**（`pin_sccb_sda = -1` + `sccb_i2c_port = 1`）
- `PIXFORMAT_RGB565`、`FRAMESIZE_VGA`(640×480)、JPEG 质量 9
- `fb_count = 1`、`CAMERA_FB_IN_PSRAM`、`CAMERA_GRAB_WHEN_EMPTY`
- 供电由 PCA9557 **P2** 控制（初始化前置 0 打开电源）

### 4.4 IO 扩展 —— PCA9557

| 项 | 值 |
|---|---|
| I2C 地址 | **0x19**（**7-bit**，`I2C_ADDR_BIT_LEN_7`） |
| 总线 | I2C1（SDA=1, SCL=2） |

初始化：
```c
WriteReg(0x01, 0x03);   // Output Port：P0=1, P1=1
WriteReg(0x03, 0xf8);   // Config Port：P0/P1/P2 输出，P3~P7 输入
```

| 位 | 方向 | 用途 | 有效电平 |
|:---:|:---:|---|---|
| **P0** | 输出 | LCD 复位 / 使能 | 0（`SetOutputState(0, 0)`） |
| **P1** | 输出 | 功放（PA）使能 | 1 = 开启 |
| **P2** | 输出 | 摄像头电源 | 0 = 打开 |
| P3–P7 | 输入 | 未使用 | — |

### 4.5 电源管理 —— PowerManager（`power_manager.h`）

| 项 | 值 |
|---|---|
| 充电检测 | GPIO47（输入，高 = 充电中） |
| 电池采样 | ADC1_CH9 → GPIO10，12 dB 衰减，12 bit |
| 采样策略 | 1 秒定时器；每 60 tick 读一次 ADC；滑动 3 次取平均 |
| 低电量阈值 | 20% |
| 电量曲线 | 2030→0%，2134→20%，2252→40%，2370→60%，2488→80%，2606→100%（线性插值，采样值 +80 补偿） |
| 温度 | ESP32-S3 片内温度传感器（10~80 °C，每 10 秒读一次，变化 ≥3.5 °C 才回调） |

`IsCharging()` 在电量 = 100% 时强制返回 false（满电不再显示充电中）。
`GetBatteryLevel()` 上报时用 `std::max(level, 20)` 保底 20%。

### 4.6 按键

| 按键 | GPIO | 交互 |
|---|:---:|---|
| BOOT | 0 | 单击：启动中→进配网 / 运行中→打断对话；双击：首次启动拍照（后续切换 AEC 打断模式）；长按：进 Wi-Fi 配网 |
| VOLUME_UP | 3 | 单击 +10 音量；长按 = 100 |
| VOLUME_DOWN | 46 | 单击 −10 音量；长按 = 0（静音） |

### 4.7 LED

单色 LED（`SingleLed`），GPIO48。

### 4.8 MCP 工具

`mcp_controller.cc` 注册：
`self.AEC.set_mode`、`self.AEC.get_mode`、`self.res.esp_restart`。
（连同固件公共部分共：`self.get_device_status`、`self.audio_speaker.set_volume`、
`self.screen.set_brightness`、`self.screen.set_theme`、`self.gif.set_gif_mode`、
`self.display.set_mode`、`self.camera.take_photo` 等。）

---

## 5. 总线拓扑

```
ESP32-S3
├── SPI3 ────────── ST7789 屏 (SCLK=41, MOSI=40, DC=39)
│                              └─ RST 由 PCA9557 P0 软控 / BL 由 GPIO42 反相 PWM
│
├── I2C1 (SDA=GPIO1, SCL=GPIO2)   ← 一条总线挂多个设备
│     ├── ES8311  @ 0x30 (8-bit 形式，7-bit=0x18)  音频 DAC/播放
│     ├── ES7210  @ 0x82 (8-bit 形式，7-bit=0x41)  麦克风 ADC
│     ├── PCA9557 @ 0x19 (7-bit)                   IO 扩展
│     └── OV2640 SCCB（与上同总线，port=1）
│
├── I2S ─────────── MCLK=38, BCLK=14, WS=13, DIN=12, DOUT=45
│
├── DVP 摄像头 ──── XCLK=17, PCLK=16, VSYNC=21, HREF=18, D0~D7=7,4,5,6,8,9,11,15
│
├── ADC ─────────── GPIO10 电池电压
├── GPIO 输入 ───── GPIO47 充电检测
└── GPIO 按键/LED ─ GPIO0 / GPIO3 / GPIO46 / GPIO48
```

---

## 6. 移植注意事项（来自硬件资料）

1. **ESP32-S3 必须带 PSRAM**。VGA@RGB565 单帧 614 KB，帧缓冲放 PSRAM（`CONFIG_CAMERA_PSRAM_DMA=y`）。
2. **GPIO 26–37 绝对不能用**（Flash / PSRAM 总线占用）；GPIO 19/20 是 USB。
3. **I2C 地址位宽不一致，最容易踩坑**：
   - PCA9557 用 **7-bit**（0x19）—— 走 IDF `i2c_master` 的 `device_address`
   - ES8311 用 **8-bit 形式**（0x30）—— `esp_codec_dev` 内部右移 1 位得 7-bit 0x18
   - ES7210 用 **8-bit 形式**（0x82）—— 对应 7-bit 0x41
4. **摄像头 SCCB 与音频 codec 共用 I2C1**。若把 I2C1 挪作他用摄像头会失联；要么保持共用，要么改 `sccb_i2c_port` 并单独初始化。
5. **LCD 没有 CS 和 RST 引脚**。CS 恒不选（SPI3 单设备），RST 由 PCA9557 P0 软控 —— 换到其它 ST7789 板必须改回硬件 RST/CS。
6. **背光反相**（`DISPLAY_BACKLIGHT_OUTPUT_INVERT = true`），换成非反相驱动电路要改。
7. **功放电源受 PCA9557 控制**，播放前必须把 P1 置 1，否则无声。
8. **Strapping 脚**：GPIO0（BOOT）、GPIO3（VOL+）、GPIO45（I2S DOUT）、GPIO46（VOL−）。GPIO45/46 兼作 strapping，上电瞬间电平会影响 VDD_SPI 电压与 ROM 日志输出，改用途前需确认上电电平无害。
9. 按键与 LED 均可软件重映射，改 `config.h` 对应宏即可。

---

## 7. 迁移/集成注意点（版型适配中心专用）

### 7.1 重命名点

| 原（`<FW>/main/boards/yuhe/cam`） | 现（`sets/boards/yh-cam`） |
|---|---|
| `yuhe_cam_board.cc` | `yh_set_cam_board.cc` |
| `class YuheCamBoard` | `class YhSetCamBoard` |
| `YuheCamBoard()` 构造函数 | `YhSetCamBoard()` |
| `DECLARE_BOARD(YuheCamBoard)` | `DECLARE_BOARD(YhSetCamBoard)` |
| TAG `"YuheCamBoard"` | TAG `"YhSetCamBoard"` |
| `config.json` 的 `type` / `builds[0].name` = `yuhe-cam` | `yh-cam` |
| `power_manager.h`、`mcp_controller.cc`、`config.h`、`config.json` | 同名保留（内容不变） |

功能上未做任何删减：摄像头（OV2640）、PCA9557（0x19）、ES8311(0x30) + ES7210(0x82)、
ST7789、PowerManager、三按键、单色 LED、MCP 工具全部保留。

### 7.2 ⚠ 全局符号冲突风险：`InitializeMCPController()`

`mcp_controller.cc` 定义了一个**全局非 static 函数**：

```cpp
void InitializeMCPController() { ... }   // 非 static，外部链接
```

同时文件里还有一个文件内 `static` 的 `g_mcp_controller`，这个不冲突。

**当前结论：不冲突，保持原样即可，无需改函数名。**
`<FW>/main/CMakeLists.txt` 用 `file(GLOB boards/${BOARD_DIR}/*.cc)` 只编译**当前选中版型目录**下的
源文件，各版型目录彼此隔离。目前 4 个 sets 版型里只有 `yh-cam` 搬了 `mcp_controller.cc`，
因此不存在重名问题。

风险（仅在以下情况出现）：若 `boards/` 下**同时参与编译**的其它版型目录也带一份同名的
`InitializeMCPController()`（例如其它队员把屿禾 cam 系列的 `mcp_controller.cc`
原样搬到 `yh-cam-ml307` 等版型，且两套目录被放进同一次编译），链接阶段会出现
`multiple definition of InitializeMCPController`。

> ⚠ **若后续新版型也要用 MCP 控制器，需改名以避免与其它版型共存时的维护混淆。**
> 建议改名成带版型后缀的形式（如 `InitializeYhCamMCPController()`），
> 并同步 `yh_set_cam_board.cc` 顶部声明（第 29 行）与 `InitializeController()`（第 275 行）。

按 SPEC 要求本文件**保持原样未改**。若后续报链接冲突，解决方式（任选其一，届时需改动本文件）：

1. 把函数与 `MCPController` 类一起包进匿名命名空间：`namespace { ... }`；
2. 改成 `static void InitializeMCPController()`，并把调用方
   （`yh_set_cam_board.cc` 里的 `void InitializeController() { InitializeMCPController(); }`）
   改为让 `.cc` 直接包含 `mcp_controller.cc`（`#include "mcp_controller.cc"`）后再调用；
3. 给本版型重命名（如 `InitializeYhCamMCPController()`），并把
   `yh_set_cam_board.cc` 顶部声明与调用处同步改名。

`class Pca9557`、`class CustomAudioCodec`、`class MCPController` 都定义在 `.cc` 内且本目录唯一，
若同一版型目录下只有一个 `.cc` 引用它们就不会冲突；但**若两个版型目录的 `.cc` 被放进同一次编译**，
这些类也会因为同名而 ODR 冲突（它们是类定义，冲突表现为 ODR violation 而非链接报错，更隐蔽）。
建议：同一时刻只让一个版型目录参与编译（`<FW>/main/CMakeLists.txt` 的 `BOARD_DIR` 机制已保证）。

### 7.3 `config.json` 的 `sdkconfig_append`（31 条全部保留，勿删）

保留原 `yuhe/cam` 的全部 31 条 `sdkconfig_append`，**一条都不要删**。
逐条分组说明见第 8 节。要点：

- 其中「语音打断防护组」（`CONFIG_YH_VAD_*` / `CONFIG_YH_INTERRUPT_GUARD_MS`）是今天上午
  「TTS 自打断修复」的参数化配置，**删掉就会退回 bug**；本版型是四套 sets 版型里唯一带 codec
  回采、唯一走 Realtime 边播边听的板，也是唯一会被该 bug 命中的。
- `CONFIG_USE_DEVICE_AEC=y` 与上面那组保护窗是**配套的**（AEC 打开 → `kListeningModeRealtime`，
  必须有保护窗兜底），不要只留一个。
- 全部 31 条符号均已核实有效：`YH_*` 系列定义在 `<FW>/main/Kconfig.projbuild:30-86`
  （menu "YH Voice Interrupt Tuning"）；`CONFIG_CAMERA_PSRAM_DMA` 定义在
  `managed_components/espressif__esp32-camera/Kconfig:233`。
- 若 sets 的 `build.py` 会覆盖/重生成 `config.json`，务必保证这 31 条被保留下来，
  否则 16 MB 分区表、`CONFIG_CAMERA_PSRAM_DMA`、屿禾协议、唤醒词都会丢。

> **不变式**：`set.json` 的 `sdkconfig_append` 与 `config.json` 的 `sdkconfig_append`
> **必须始终保持一致**（前者给 `hardware/sets/build.py` 展示/覆盖用，后者给固件
> `scripts/build.py` 消费）。当前 `set.json` 为 `[]`、`config.json` 为 31 条 —— 是否要同步成
> 两份都写 31 条，待 team-lead 指示；在此之前请勿单独改动其中一份。

### 7.4 其它

- `pca9557_handle_` 成员在原实现里声明但未使用，保留原样未动。
- camera 的 `ledc_channel = LEDC_CHANNEL_2` / `ledc_timer = LEDC_TIMER_2` 在 ESP32-S3 上不产生 XCLK，
  保留原值仅为与原版行为一致。
- 编译日志里若出现 `ESC` 未定义的提示，不用管：那是 ESP-IDF 自带的 ANSI 转义宏，
  由 IDF 头在编译期提供，与本版型无关。

---

## 8. 本版型的 sdkconfig 关键项（`config.json` 的 31 条，按组归类）

> **总原则：这 31 条全部有定义、全部有效、全部必要，一条都不要删。**

### 8.1 屿禾协议与 OTA 组

| 项 | 值 | 说明 |
|---|---|---|
| `CONFIG_YH_PROTOCOL_ENABLED` | `y` | 启用屿禾私有协议 |
| `CONFIG_YH_SERVER_HOST` | `"sandyun.top"` | 协议服务器 |
| `CONFIG_YH_SERVER_PORT` | `12399` | 协议端口 |
| `CONFIG_OTA_URL` | `"http://sandyun.top:8002/xiaozhi/ota/"` | OTA 地址 |

### 8.2 语音打断防护组 ⚠ 不要随意删除

| 项 | 值 | 说明 |
|---|---|---|
| `CONFIG_YH_VAD_MODE` | `2` | AFE VAD 档位（0 最灵敏 / 4 最难触发） |
| `CONFIG_YH_VAD_MIN_SPEECH_MS` | `200` | 最短人声时长 |
| `CONFIG_YH_VAD_MIN_NOISE_MS` | `100` | 最短噪声时长 |
| `CONFIG_YH_VAD_SPEECH_CONFIRM_MS` | `300` | 应用层二次去抖：连续人声确认窗 |
| `CONFIG_YH_VAD_SILENCE_CONFIRM_MS` | `300` | 连续静音确认窗 |
| `CONFIG_YH_INTERRUPT_GUARD_MS` | `800` | 播放起始保护窗 |

**这组用于抑制 TTS 自打断（TTS 播到一半被自己打断、伴随一声「滴」）。调大 = 更难打断。不要随意删除。**

代码消费点（均已确认存在且生效）：
- `<FW>/main/audio/engines/afe_audio_engine.h:89-90` → `kVadSpeechConfirmMs`
- `<FW>/main/audio/engines/afe_audio_engine.cc:157-158` → `vad_mode`、`vad_min_speech_ms`
- `<FW>/main/application.cc:33` → `kSpeakingInterruptGuardMs`

符号定义在 `<FW>/main/Kconfig.projbuild:30-86`（menu `"YH Voice Interrupt Tuning"`）。

### 8.3 AEC 组（与 8.2 配套，不要拆开）

| 项 | 值 | 说明 |
|---|---|---|
| `CONFIG_USE_DEVICE_AEC` | `y` | 决定 `aec_mode_ = kAecOnDeviceSide` → `GetDefaultListeningMode()` 返回 `kListeningModeRealtime`（日志 `mode=2`）。删掉会退化成 AutoStop，等于放弃边播边听 |
| `CONFIG_USE_SERVER_AEC` | `n` | 不用服务端 AEC |
| `CONFIG_USE_AUDIO_PROCESSOR` | `y` | 音频处理链路 |

### 8.4 唤醒词组

> **唤醒词开关就是 `CONFIG_USE_CUSTOM_WAKE_WORD`（定义在 `<FW>/main/Kconfig.projbuild:1013`）。**
> **不存在 `YH_CUSTOM_WAKE_WORD_ENABLED` 这个符号** —— 它既未在 Kconfig 中定义，也无任何代码消费。
> 若误写进 `sdkconfig_append`，固件 `scripts/build.py` 会报 **Kconfig rejected** 导致编译失败，切勿添加。

| 项 | 值 | 说明 |
|---|---|---|
| `CONFIG_USE_CUSTOM_WAKE_WORD` | `y` | **唤醒词总开关** |
| `CONFIG_CUSTOM_WAKE_WORD` | `"ni hao xiao he"` | 唤醒词拼音 |
| `CONFIG_CUSTOM_WAKE_WORD_DISPLAY` | `"你好小禾"` | 界面显示 |
| `CONFIG_CUSTOM_WAKE_WORD_THRESHOLD` | `40` | 触发阈值 |
| `CONFIG_SR_MN_CN_MULTINET7_QUANT` | `y` | MultiNet，动态唤醒词的前提 |
| `CONFIG_SR_WN_WN9_NIHAOXIAOZHI_TTS` | `n` | 关闭默认「你好小智」 |

### 8.5 Flash 与分区组（容量与分区表必须同时改，只改一个会烧录失败）

| 项 | 值 | 说明 |
|---|---|---|
| `CONFIG_ESPTOOLPY_FLASHSIZE_16MB` | `y` | 16 MB Flash |
| `CONFIG_PARTITION_TABLE_CUSTOM` | `y` | 自定义分区表 |
| `CONFIG_PARTITION_TABLE_CUSTOM_FILENAME` | `"partitions/v2/16m.csv"` | 与上一条配套 |
| `CONFIG_ESPTOOLPY_FLASHMODE_DIO` | `y` | DIO 模式 |
| `CONFIG_ESPTOOLPY_FLASHMODE_QIO` | `n` | 关 QIO |

### 8.6 摄像头 / 屏 / 网络组

| 项 | 值 | 说明 |
|---|---|---|
| `CONFIG_CAMERA_PSRAM_DMA` | `y` | 摄像头帧缓冲走 PSRAM（定义在 `managed_components/espressif__esp32-camera/Kconfig:233`） |
| `CONFIG_LV_USE_FONT_COMPRESSED` | `y` | LVGL 压缩字体 |
| `CONFIG_LV_USE_FONT_PLACEHOLDER` | `y` | LVGL 占位字体 |
| `CONFIG_LWIP_TCPIP_RECVMBOX_SIZE` | `48` | 网络收包邮箱 |
| `CONFIG_ESP_WIFI_DYNAMIC_RX_BUFFER_NUM` | `32` | Wi-Fi 动态 RX 缓冲 |
| `CONFIG_ESP_WIFI_TASK_PINNED_TO_CORE_0` | `n` | Wi-Fi 任务绑核 |
| `CONFIG_ESP_WIFI_TASK_PINNED_TO_CORE_1` | `y` | 同上（配 8.2 的打断防护，避免被网络任务拖慢） |

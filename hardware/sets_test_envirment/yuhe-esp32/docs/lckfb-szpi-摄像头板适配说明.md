# 立创实战派 S3（lckfb/szpi-esp32s3）摄像头板适配说明

> 面向后续维护者。记录"为什么切板、切了什么、每个决定为什么这么做、还有哪些坑要实机验证、怎么回滚"。
> 硬件规格的唯一权威仍是 `G:\demo\21_xiaozhi\hardware\small_screen_camera\camera板子信息.md`；本文只解释**适配决策**。
> 固件基线：yuhe-esp32 v2.5.1 / ESP-IDF v6.1 / ESP32-S3。

---

## 1. 为什么要切板、切了什么

### 1.1 背景

原工程长期编译小屏板 `my-s3-tft`（240×240 圆屏、无摄像头、INMP441 + MAX98357A、WS2812@GPIO48、SSD1306 备用屏）。
该板**没有摄像头**，无法承载"看图 / 拍照"类能力，因此整体切换到自带 DVP 摄像头 + 触摸屏 + 编解码器的立创实战派 S3。

| 维度 | 旧：my-s3-tft | 新：lckfb/szpi-esp32s3 |
| --- | --- | --- |
| 屏幕 | ST7789 240×240 圆屏 | ST7789 320×240 横屏 + FT5x06 触摸 |
| 摄像头 | 无 | 8-bit DVP QVGA RGB565 |
| 音频 | INMP441 + MAX98357A | ES8311 DAC + ES7210 ADC，24kHz，设备端 AEC |
| 控制 | 直接 GPIO | PCA9557@0x19（LCD 复位 / PA 使能 / 摄像头上电） |
| 按键 | BOOT + 音量键 | 仅 BOOT（音量脚被摄像头占用） |
| LED | WS2812@48（板级驱动） | WS2812@48（改为系统状态灯） |

### 1.2 改动文件清单

| # | 文件 | 改动性质 | 说明 |
| --- | --- | --- | --- |
| 1 | `main/boards/lckfb/szpi-esp32s3/config.h` | 修改 | 全部硬件引脚宏（唯一硬件事实来源）：音频 I2S、PCA9557、显示/背光、摄像头 DVP、BOOT/LED |
| 2 | `main/boards/lckfb/szpi-esp32s3/config.json` | 修改 | 板身份 `lckfb/lichuang-dev/esp32s3`；`sdkconfig_append` 注入 AEC、摄像头 DMA、YH、OTA、唤醒词等 |
| 3 | `main/boards/lckfb/szpi-esp32s3/lichuang_dev_board.cc` | 修改 | 板级实现：`Pca9557`、`CustomAudioCodec`、ST7789、FT5x06、BOOT 按键语义、`Esp32Camera`、`GetLed()` 覆写 |
| 4 | `main/boards/lckfb/szpi-esp32s3/README.md` | 修改 | 板级说明（Flash 模式、构建方式、已知限制） |
| 5 | `build_lckfb_s3.bat` | 新增 | 编译脚本（IDF 环境 + `python scripts\build.py lckfb/szpi-esp32s3`） |
| 6 | `HARDWARE_GUIDE.md` | 重写 | 旧内容（旧路径 / 240×240 / MAX98357A / INMP441）全部作废 |
| 7 | `docs/lckfb-szpi-摄像头板适配说明.md` | 新增 | 本文 |

> 未改动：`main/CMakeLists.txt`、`main/Kconfig.projbuild`（`BOARD_TYPE_LICHUANG_DEV_S3` 分支本已存在）、`partitions/v2/16m.csv`、`scripts/build.py`。
> `my-s3-tft/` 目录**原样保留**，未删除、未修改，可随时回滚。

### 1.3 构建链四处必须一致

| 环节 | 值 |
| --- | --- |
| `scripts/build.py` 参数 | `lckfb/szpi-esp32s3` |
| `config.json` | `manufacturer=lckfb`、`type=lichuang-dev`、`target=esp32s3` |
| `main/Kconfig.projbuild` | `BOARD_TYPE_LICHUANG_DEV_S3` |
| `main/CMakeLists.txt` | `BOARD_DIR = "lckfb/szpi-esp32s3"` |
| 产物名 | `lckfb-lichuang-dev` |

---

## 2. 逐项决策与理由

| # | 决策 | 理由 / 权衡 |
| --- | --- | --- |
| 1 | **LED 归属：GPIO48 用 `SingleLed(BUILTIN_LED_GPIO)` 覆写 `GetLed()`** | 本工程 `main/boards/common/board.cc:167` 的 `Board::GetLed()` 默认返回 `NoLed()`，不覆写则板载灯完全不亮、无状态反馈。用 `SingleLed` 而非 `CircularStrip`：板上只有 1 颗 WS2812，环形灯带驱动会多占 RMT 通道且无意义。 |
| 2 | **YH 的 WS2812 设为 `GPIO_NUM_NC`（空操作）** | YH 协议（`CONFIG_YH_PROTOCOL_ENABLED=y`）带独立的 `YhWs2812Led` 句柄，若仍绑 GPIO48 会与状态灯**抢同一个 RMT 通道 / 同一颗灯**，导致两边互相覆盖、颜色乱跳。设为 NC 后 YH 的 `SET_LED` 指令走空实现（日志提示忽略），状态灯独占 GPIO48。YH 协议本身的 TCP 通道不受影响。 |
| 3 | **I2C 速率：按设备侧 400kHz，不在总线结构体里设** | 总线 port1 上同时挂 ES8311、ES7210、PCA9557、FT5x06 和摄像头 SCCB。**IDF 6.1 的 `i2c_master_bus_config_t` 没有 `scl_speed_hz` 字段**（曾误加，会编译报 `has no member named 'scl_speed_hz'`，已移除），速率由各 device 指定：`main/boards/common/i2c_device.cc`（codec / PCA9557）与 `InitializeTouch()`（FT5x06）均为 400kHz，与档案 §3 一致。代价见"风险清单"。 |
| 4 | **按键映射取舍：只保留 BOOT(GPIO0)** | 原板的音量键 GPIO3 / GPIO46 已被摄像头 VSYNC / HREF 占用（见 `config.h`），物理冲突不可调和，故 `VOLUME_UP/DOWN_BUTTON_GPIO = GPIO_NUM_NC`。功能上改为：单击=开始/打断、双击=AEC 开关、长按=PressToTalk 按住说话。 |
| 5 | **BOOT 单击配网加"仅开机 30s 内长按才配网"防呆** | 原逻辑"Starting 态单击即进配网"在配网失败重启后会造成**死循环**（重启→单击→配网→失败→重启）。加时间窗后只有开机 30 秒内的长按才触发配网，正常单击始终走"开始/打断"。 |
| 6 | **Flash 用 DIO @80MHz** | 按板卡档案显式指定，保证与实测一致、避免 QIO 起不来变砖。若实测该批硬件支持 QIO，改回 QIO 可提升吞吐——已在板 README 注明。改之前务必整片擦除后重刷。 |
| 7 | **唤醒词 / OTA / YH 从 `config.json` 注入** | 均为"定制服务"而非"板级硬件能力"，放在 `config.json` 的 `sdkconfig_append` 可随板型一键切换，不污染 `sdkconfig`（`sdkconfig` 由 build.py 生成、不手工维护），也便于回滚时自动失效。 |
| 8 | **显式关闭 `CONFIG_SR_WN_WN9_NIHAOXIAOZHI_TTS`** | 自定义唤醒词"你好小禾"（`ni hao xiao he`，Multinet7 量化，阈值 40）与内置"你好小智"同族，同时开启会增大模型体积、且容易互相误触发。 |
| 9 | **不迁移圆屏皮肤** | 圆屏 240×240 的 `RoundScreenDisplay` / 表情皮肤是按 240×240 圆屏裁剪的位图与布局，直接套到 320×240 横屏会错位、溢出；本板走通用 `SpiLcdDisplay`（`CONFIG_USE_EMOTE_MESSAGE_STYLE` 时才走 `EmoteDisplay`）。 |
| 10 | **不迁移 SSD1306 备用屏** | 旧板 SSD1306 用 SCL=GPIO9 / SDA=GPIO8，这两个脚在本板已被 DVP 的 **D7 / D2** 占用（见 `config.h`），物理上无法复用。且本板主屏带触摸、可用性远高于 128×64 OLED，备用屏价值下降。 |
| 11 | **摄像头 `fb_count=1` + PSRAM + `CAMERA_GRAB_WHEN_EMPTY`** | 320×240 RGB565 单帧 150KB，片内 DRAM 放不下多帧；单帧在 PSRAM 配合 `WHEN_EMPTY` 抓取，是内存与帧率的最小可行解。`jpeg_quality=12` 平衡 MCP 上传体积与清晰度。 |

---

## 3. 风险与待实机验证项

| # | 风险点 | 影响 | 验证 / 处置建议 |
| --- | --- | --- | --- |
| 1 | **PCA9557 bit0（LCD/触摸复位）极性** | 极性与预期相反会黑屏或触摸不应答 | **已定案：高有效复位（1=复位中，0=释放）**——实机 LCD 已点亮即反证（开机默认输出 `0x03`，bit0 被置 0 后屏亮）。曾误加"LCD init 后再置 1"，等于重新把芯片按进复位 → 黑屏 + 触摸失效，**已回退**：现在 init 后只打印观测值、不再改写 bit0（`InitializeSt7789Display()`）。待实机确认：bit0=0 释放后触摸 0x38 是否在扫描中出现 |
| 2 | **摄像头上电 bit2 极性** | 极性错了摄像头永远探测不到 | **已改为自适应极性探测**：`PowerOnCameraWithPolarityProbe()` 先试 `bit2=1` 扫 SCCB 候选地址，无命中再试 `bit2=0`，以"摄像头 SCCB 地址是否 ACK"为唯一判据，定案后全程不再翻转；**且已提前到触摸/显示初始化之前**（bit2 那一路疑似摄像头与触摸的共用电源域）。待实机确认日志 `Camera power polarity resolved: PCA9557 bit2=?`（详见 §4.4） |
| 3 | **FT5x06 与 ES8311 / ES7210 同总线跑 400kHz** | 高速下触摸丢点、codec 寄存器写失败、SCCB 偶发 NACK | 长时间压测（连续触摸 + 播放 + 拍照）；不稳则把触摸降到 100kHz 或拆总线 |
| 4 | **24kHz + 设备端 AEC 效果** | 回声消除不充分 → 播放时误唤醒 / 自听回声 | 播放音乐时对话，用双击切 AEC 开/关对比 |
| 5 | **assets 变大后 app 分区余量** | 表情/字体资源膨胀会挤压资源包自身分区；app 单槽约 3.9MB，当前约 2.7MB，余量 ~30% | 每次加资源后看 `build/generated_assets.bin` 是否仍在 8MB 内、app 是否仍 <3.9MB |
| 6 | **首建报 `sdkconfig was not generated`** | 首次构建失败 | 已知现象，**重跑一次** `build_lckfb_s3.bat` 即可 |
| 7 | **Flash DIO 假设** | 若该批硬件实际支持 QIO 而用了 DIO，只是吞吐略低；反过来会起不来 | 保守用 DIO；如需 QIO 先单独验证再改，并整片重刷 |
| 8 | **音量键缺失** | 无硬件调音量 | 走 MCP / App 侧控音量；后续若换无摄像头板可恢复 GPIO3/46 |
| 9 | **配网 30s 窗口** | 用户开机很久后才想配网会失败 | 提示用户重启设备，或用 MCP `self.system.reconfigure_wifi` |
| 10 | **PSRAM Octal @80MHz** | PSRAM 不稳会随机崩溃 / 摄像头 DMA 花屏 | 跑 PSRAM 压力测试；不稳降频验证 |

---

## 4. 验收 / 排障清单

### 4.1 串口关键日志（115200）

启动阶段应依次看到（顺序与板级初始化一致）：

| 阶段 | 预期日志要点 |
| --- | --- |
| I2C / PCA9557 | I2C port1 初始化成功；PCA9557 @0x19 配置寄存器写成功，无 `ESP_ERR_TIMEOUT` / NACK |
| SPI | SPI3_HOST 初始化成功 |
| 显示 ST7789 | `LichuangDevBoard` 标签下 `Install panel IO` → `Install LCD driver`（`ESP_LOGD`，需开 Debug 日志级别）；随后屏点亮 |
| 触摸 FT5x06 | 找到 FT5x06 @0x38；未找到时应出现 `FT5x06 touch controller not found, continuing without touch`（**非致命**） |
| 音频 | ES8311(0x18) / ES7210(0x82) 探测成功，24kHz 输入/输出建立 |
| 摄像头 | 摄像头 probe 成功、分辨率 QVGA、`fb_count=1` 于 PSRAM；失败时看 PCA9557 bit2 与 XCLK |
| 网络 | Wi-Fi 连上并进入 `Idle` |
| YH | `[YH]` 标签下连接 `sandyun.top:12399`、HELLO / HEARTBEAT 正常 |
| LED | 状态灯随状态变化；YH 下发 SET_LED 时日志提示本板无独立 WS2812（预期，因置 NC） |

### 4.2 功能验收

| 项 | 操作 | 预期 |
| --- | --- | --- |
| 屏幕 | 上电 | 320×240 横屏正常显示，方向正确（swap_xy + mirror_x） |
| 背光 | 调亮度 | GPIO42 低电平有效，亮度可调且掉电记忆（`RestoreBrightness`） |
| 触摸校准 | 四角点按 | 触点与手指一致；偏移则核对 `swap_xy=1 / mirror_x=1 / x_max=240 / y_max=320` |
| 摄像头 MCP 拍照 | 让服务端调用摄像头 MCP 工具取图 | 返回 JPEG（quality 12）且画面正常、不花屏 |
| 播放 | 播放 TTS / 音乐 | ES8311 出声，PA（PCA9557 bit1）已使能 |
| 录音 | 对话 | ES7210 采到数据，波形正常 |
| AEC 双击切换 | Idle 态双击 BOOT | AEC 在 device-side / off 间切换，日志可见模式变化；播放中对话不再自触发 |
| 单击 | 单击 BOOT | 开始/打断对话；Starting 态不再无限进配网（30s 窗口） |
| PressToTalk | MCP 开启后长按 BOOT | 按下开始听、松开结束 |
| YH 协议连通性 | 观察 `[YH]` 日志 / 服务端设备上线 | HELLO → ADVERTISEMENT → HEARTBEAT 持续，COMMAND 可下发并 ACK |
| OTA | 触发 OTA | 从 `http://sandyun.top:8002/yuhe/ota/` 拉取成功；**OTA 不刷 assets** |
| 唤醒词 | 说"你好小禾" | 唤醒成功；"你好小智"不再响应 |

### 4.3 排障速查

| 现象 | 优先检查 |
| --- | --- |
| 黑屏 | 背光极性（低有效）→ PCA9557 bit0 → I2C 是否通 → Flash 模式是否 DIO |
| 触摸无效/偏移 | FT5x06 是否被探测到 → 400kHz 稳定性 → 映射参数 |
| 摄像头失败 | PCA9557 bit2 极性 → XCLK 20MHz → `sccb_i2c_port=1` → PSRAM |
| 无声 | PA 使能 bit1 → ES8311 地址 → I2S 引脚 |
| 录不进 | ES7210 0x82 → DIN=GPIO12 → 24kHz 一致性 |
| 界面乱码/缺字 | **assets 0x800000 是否刷过**（OTA 不会刷） |
| 灯不亮 | `GetLed()` 是否覆写为 `SingleLed(GPIO48)` → YH LED 是否 NC 未抢 RMT |

### 4.4 实机首跑故障与处置（2026-10-16 首次上电）

> 配套操作手册见 `docs/lckfb-实机首跑排障.md`。本节只记录**已发生的事实与已落地的代码处置**，作为后续维护的决策依据。

**实机现象**（板型 `lckfb/szpi-esp32s3`，编译烧录成功）：

```
I (382) LcdDisplay: Turning display on / Initialize LVGL library / Added 2560KB LVGL pool in PSRAM
E ×9  lcd_panel.io.i2c: panel_io_i2c_tx_buffer(197): i2c transaction failed
E (462) FT5x06: esp_lcd_touch_new_i2c_ft5x06(161): FT5x06 init failed
E (472) FT5x06: Error (0x108)! Touch controller FT5x06 initialization failed!
I (492) cam_hal: cam init ok
E (502) camera: Detected camera not supported.
E (502) camera: Camera probe failed with error 0x106(ESP_ERR_NOT_SUPPORTED)
I (622) BoxAudioCodec: BoxAudioDevice initialized （ES8311/ES7210 四麦 TDM 正常）
I (632) SystemInfo: free sram: 186927 minimal sram: 85400
```

**七条定论与已做处置**：

| # | 结论 | 已落地的代码处置 |
| --- | --- | --- |
| 1 | 摄像头 `0x106` **不是**"驱动没编进去"。真正门控是 esp32-camera 的 `CONFIG_<型号>_SUPPORT`（本工程 15 个全 `=y`）；`CONFIG_CAMERA_<型号>`（esp_cam_sensor，全 `n`）与本故障**无关**——legacy `esp_camera_init()` 路径绕开它。`0x106` 的真实含义是 **SCCB 对所有候选地址（0x30/0x3C/0x21/0x6E/0x68/0x2A…）全部 NACK** | `InitializeCamera()` 失败日志已改写，不再误导为"驱动未编译"，改为直接指出 0x106 = 全地址 NACK + 打印实测 bit2/SCCB/XCLK |
| 2 | bit2 供电极性**极可能是高有效（1=上电）**。若 0=上电，则开机默认输出 `0x03`（bit2=0）时摄像头即带电，SCCB 必然应答，与实测全 NACK 矛盾 | 新增 `PowerOnCameraWithPolarityProbe()`：**先试 bit2=1 扫 SCCB，无命中再试 bit2=0**，以"摄像头地址是否 ACK"为唯一判据，定案后不再翻转；两轮皆无 → 保留 bit2=0 并报"检查排线/供电/XCLK" |
| 3 | bit0 是**高有效复位（1=复位中，0=释放）**，LCD 已点亮可反证 | 已回退"LCD init 后置 bit0=1"的误改（那会把芯片重新按进复位 → 黑屏 + 触摸失效）；现在 init 后只打印观测值 |
| 4 | 触摸 `0x108` = **地址 NACK**（`ESP_ERR_INVALID_RESPONSE` 只由 NACK 产生；超时是 `0x107`；格式/速率问题不会让地址字节 NACK）。概率分布：未焊/未供电/被复位钳住 ~80%、实际型号是 CST816S(0x15)/GT911(0x5D) ~15%、速率 ~3% | 已在 `esp_lcd_touch_new_i2c_ft5x06` 前加 `i2c_master_probe(0x38)` 前置探测（消除 9 条 `panel_io_i2c_tx_buffer` 刷屏）；失败时打印"0x38 NACK + CST816S/GT911 换驱动"提示 |
| 5 | bit2 那路电源可能是**摄像头与触摸共用域**，原流程触摸探测发生在摄像头上电之前 → 触摸可能因此没电 | 构造顺序改为 `InitializeI2c()` → **`PowerOnCameraWithPolarityProbe()`** → SPI/LCD → `InitializeTouch()` → … → `InitializeCamera()` |
| 6 | 其余一切正常 | 无需处置。`I2S rx switched master→slave` 是全双工预期；`Resampling 16000→24000` 是开机提示音解码、不是配置错；内存/LVGL/按键/状态灯(`SingleLed` GPIO48)/YH(nc no-op) 均正常；启动停在 `starting` 是日志被截断，约 2.2s 会进配网 |
| 7 | 陷阱：日志 `camera=ready` 曾**不可信**（`esp32_camera.cc` init 失败仍保留非空指针）；`Backlight: Set brightness to 75` 是**默认值**不是 NVS 恢复 | `Board init done` 的 camera 字段改为真实状态：`camera=ready` 或 `camera=DISABLED(probe failed)` |

**新增的诊断日志锚点**（排障时按 stage 标签检索）：

| stage 标签 | 产生位置 | 用途 |
| --- | --- | --- |
| `after-i2c-init` | `InitializeI2c()` 末尾 | 未上电基线：摄像头/触摸此刻应都不在 |
| `cam-pwr-bit2=1` | `PowerOnCameraWithPolarityProbe()` 分支 1 | 判定 bit2 是否高有效上电 |
| `cam-pwr-bit2=0` | `PowerOnCameraWithPolarityProbe()` 分支 2 | 判定 bit2 是否低有效上电 |
| `pre-camera-init` | `InitializeCamera()` 内 | `esp_camera_init` 前的最终确认 |

---

## 5. 回滚方法

| 目标 | 命令 |
| --- | --- |
| 切回旧圆屏板 | `python scripts\build.py my-s3-tft` |
| 切回摄像头板 | `python scripts\build.py lckfb/szpi-esp32s3` |
| 一键脚本 | `build_my_s3_tft.bat` / `build_lckfb_s3.bat` |

要点：

1. 两块板目录 `main/boards/my-s3-tft/` 与 `main/boards/lckfb/szpi-esp32s3/` **互不影响**，`config.h` / `config.json` / 板级 .cc 各自独立，切换只需换 `build.py` 的板参数。
2. `sdkconfig` 由 `build.py` 按板型重新生成；手工改过的项在切板后会丢失——定制项（OTA / 唤醒词 / YH）**必须写在 `config.json` 的 `sdkconfig_append` 里**，不要写进 `sdkconfig`。
3. 切板后**必须全量重烧**：分区表与 assets 都可能变，`yh_flash.bat`（`@flash_args`）只刷 app 相关分区，需补刷 `generated_assets.bin` 到 `0x800000`：
   ```batch
   python -m esptool --chip esp32s3 -p COM3 -b 460800 write-flash 0x800000 build\generated_assets.bin
   ```
4. 板型 identity（`config.json` 的 `type`）一旦发布**不可再改**，改了等于换设备（OTA / 服务端按此识别）。

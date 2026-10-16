# 立创实战派 S3（LCKFB SZPI-ESP32S3）

> ❌ **2026-10-16 07:55 更正：本板不是 lckfb/szpi-esp32s3！**
> 权威文档 `hardware/small_screen_camera/camera硬件信息.md` 给出的板级标识是 **`yuhe/cam`**，
> 且仓库中 `main/boards/yuhe/cam` 与该文档**逐项吻合**。工程已切换到该板型，
> 编译请改用 `build_yuhe_cam.bat`。详见 `docs/yuhe-cam-板型切换说明.md`。
> 本目录的代码已回退为上游原始版本，不再使用。

> ⚠️ **2026-10-16 04:29 已回退**：本文件是排查期间的说明文档，其中描述的**改动已全部撤销**，
> 同目录的 `config.h` / `lichuang_dev_board.cc` 现为**上游原始版本**。
> 备份见 `hardware/small_screen_camera/_revert_backup_20261016_0429/`。

本工程内的**摄像头板**：2.4/2.8 类 ST7789 SPI TFT 屏（FPC `AFC01-S14FCC-00`）+ 8-bit DVP 摄像头 + ES8311/ES7210 音频（设备端 AEC）；
触摸按"多型号自动识别"处理（本屏 FPC 无触摸线，预期全 NACK，见下）。
外设硬件事实以 `camera板子信息.md` 为唯一权威；**屏幕侧以 TFT 接口原理图为准**（覆盖档案文字与现象反推），本目录只做它们的固件表达。

- 板型：`CONFIG_BOARD_TYPE_LICHUANG_DEV_S3`
- 身份：`manufacturer=lckfb` / `type=lichuang-dev` / `target=esp32s3` / 产物名 `lckfb-lichuang-dev`
- 初始化顺序：`InitializeI2c → InitializeSpi → InitializeSt7789Display → InitializeTouch → InitializeButtons → InitializeCamera → InitializeTools → GetBacklight()->RestoreBrightness()`

## 引脚总表

### 音频（§3）

| 项目 | 值 |
| --- | --- |
| 采样率 | 输入 24kHz / 输出 24kHz |
| DAC（扬声器） | ES8311，I2C 地址默认（`ES8311_CODEC_DEFAULT_ADDR`，0x18） |
| ADC（麦克风阵列） | ES7210，I2C 地址 0x82（8-bit 写法，7-bit 0x41） |
| 回声消除 | `AUDIO_INPUT_REFERENCE=true`（ES7210 采集回路参考）＋ `CONFIG_USE_DEVICE_AEC=y` |
| 功放/编解码控制 | PCA9557 IO 扩展器 @0x19：bit1=PA 使能，bit0=LCD 复位，bit2=摄像头电源 |
| I2C 总线 | port1，SDA=GPIO1，SCL=GPIO2，400kHz，内部上拉 |

I2S 引脚：

| 信号 | GPIO |
| --- | --- |
| MCLK | 38 |
| WS/LRCK | 13 |
| BCLK | 14 |
| DOUT（→ES8311） | 45 |
| DIN（←ES7210） | 12 |

### 显示与触摸（§4）

> 屏幕侧引脚与极性以 **TFT 接口原理图**为最终权威（FPC 座 `AFC01-S14FCC-00`，FPC4，供电 3V3，16pin 座实际用 15 脚），
> 覆盖此前基于档案文字/现象反推的结论。排障见 `docs/lckfb-实机首跑排障.md` §2。

| 项目 | 值 |
| --- | --- |
| 屏幕驱动 | ST7789V，SPI（SPI3_HOST），16-bit RGB565 |
| 分辨率 | 320×240（swap_xy=true, mirror_x=true, mirror_y=false） |
| SPI | MOSI=GPIO40（FPC8，LCD_MOSI），SCLK=GPIO41（FPC9，LCD_SCK）；**MISO/CS=NC（原理图无 CS，硬件接地；无 MISO）** |
| DC | GPIO39（FPC7，LCD_DC） |
| SPI 时钟 | 80MHz，mode 2 |
| 复位 | 无独立 GPIO 复位脚；RESET（FPC6）经 **R76(10k) 上拉至 3V3**，由 PCA9557 **bit0** 驱动 —— **低电平复位**，释放态 bit0=1。原理图备注 RESET 未直连 ESP32 |
| 反色 | invert_color(true) |
| 背光 | GPIO42（LCD_BL），PWM，**高电平有效**（Q2 MOS 高导通点亮）→ `DISPLAY_BACKLIGHT_OUTPUT_INVERT=false` |
| 背光电路 | GPIO42 PWM → R23(1k) 栅/基极限流 → Q2 MOS；栅极 R21(10k) 上拉 3V3；LEDA(FPC5) 经 R20(10Ω) 限流 |
| 屏供电 | 3V3 = FPC10 / FPC11；GND = FPC15 |
| 触摸 | **多型号自动识别**：0x38 FT5x06 / 0x5D·0x14 GT911 / 0x15 CST816S / 0x55 ST7123 / 0x5A CST9217，挂在音频 I2C 总线（400kHz）；全失败不阻塞开机 |
| 本屏是否有触摸 | **本屏 FPC 无任何触摸信号线（无 SDA/SCL/INT）→ 该屏不带触摸**；故 6 地址全 NACK 属**预期，不是故障**（BOOT 键 + 语音可用）。若板上另有触摸排线/芯片，代码会按日志自动识别 |
| 触摸映射 | swap_xy=1，mirror_x=1；x_max=240 / y_max=320 |
| 触摸中断/复位 | INT 为 NC；复位与 LCD 共享 PCA9557 bit0（低电平复位） |

FPC 引脚映射（原理图权威）：

| FPC 脚号 | 信号 | 连接 |
| --- | --- | --- |
| FPC4 | 座型号 `AFC01-S14FCC-00` | FPC 16pin 座，实际用 15 脚 |
| FPC5 | LEDA | 背光阳极，经 R20(10Ω) 限流，由 Q2 驱动 |
| FPC6 | RESET | 经 R76(10k) 上拉 3V3，低电平复位；原理图未直连 ESP32 |
| FPC7 | LCD_DC | GPIO39 |
| FPC8 | LCD_MOSI | GPIO40 |
| FPC9 | LCD_SCK | GPIO41 |
| FPC10 / FPC11 | 3V3 | 屏供电 |
| FPC15 | GND | 地 |
| —（非 FPC） | LCD_BL | GPIO42 → Q2 背光驱动级 |

### 摄像头 DVP（§5）

| 项目 | 值 |
| --- | --- |
| 接口 | 8-bit DVP，RGB565，QVGA（320×240） |
| XCLK | **GPIO17**，20MHz（⚠ **2026-10-16 按 V1.0.1 全板原理图修正**；旧值 GPIO5 在原理图上是 **NC**，等于没接时钟） |
| SCCB | SCL=GPIO2（与音频 I2C 共总线，`sccb_i2c_port=1`），SDA=GPIO1 |
| 帧缓冲 | PSRAM 内 1 个 fb，`grab_mode=CAMERA_GRAB_WHEN_EMPTY` |
| 电源 | 摄像头模拟电源 = **2V8**（ME6211C28M5G-N，常供）；掉电由 **PCF8557 bit2 = DVP_PWDN** 控制，**bit2=0 才使能** |
| JPEG 质量 | 12（配置项） |
| PWDN / RESET | 均为 `GPIO_NUM_NC`（不是 ESP32 原生脚，走 IO 扩展 bit2） |

数据/时序引脚（**2026-10-16 按原理图全量重映射**，括号内为旧值）：

| 信号 | GPIO | 信号 | GPIO |
| --- | --- | --- | --- |
| D0 | **7**（旧 16） | D4 | **8**（旧 15） |
| D1 | **4**（旧 18） | D5 | **9**（旧 6） |
| D2 | **10**（旧 8，⚠ 原理图未列，暂定） | D6 | **11**（旧 4） |
| D3 | **6**（旧 17） | D7 | **15**（旧 9） |
| VSYNC | **21**（旧 3） | HREF | **18**（旧 46） |
| PCLK | **16**（旧 7） | XCLK | **17**（旧 5） |

> **为什么这条最重要**：`esp_camera.c` 里 `cam_init()`(L303) 早于 `camera_probe()`(L310)，
> S3 的 XCLK 由 `ll_cam.c:414 gpio_matrix_out(pin_xclk, CAM_CLK_IDX, ...)` 输出（可走任意输出脚）。
> 即 **SCCB 探测时 XCLK 已经在跑**。旧配置把 XCLK 放到 NC 脚 → 传感器没有工作时钟 →
> SCCB 从机不回应 → 17 个候选地址全 NACK → `Detected camera not supported` + **0x106**。
> 这与实测现象完全吻合，是摄像头不识别的**第一根因**。
>
> **D2=GPIO10 是暂定值**：原理图只给了 D0/D1/D3~D7，D2 缺失。GPIO10 是 4~18 段里唯一
> 既未被占用又避开 USB(19/20)/I2S(12/13/14) 的空脚。**D2 不参与 SCCB 探测**，
> 猜错也不会导致 0x106，只影响图像位序（颜色/条纹异常）。拿到原理图后只改 `config.h` 一行。

### 按键与指示灯（§6）

| 项目 | 值 |
| --- | --- |
| BOOT 键 | GPIO0：单击=开始/打断对话（启动期单击进 Wi-Fi 配网模式）；长按说话（PressToTalk MCP 工具开启时）；双击=切换 AEC 开/关（`CONFIG_USE_DEVICE_AEC` 时） |
| 音量键 | 无（原版 GPIO3/46 与摄像头 VSYNC/HREF 冲突，已移除——复用到无摄像头的板子可恢复） |
| 板载 LED | GPIO48（`BUILTIN_LED_GPIO`，状态指示） |

除上表外：**长按 BOOT ≥1s 且在开机 30s 内**进 Wi-Fi 配网；超时或已联网则忽略，避免"按键即重配网"循环。

## 与本工程定制项的关系

- **YH 协议开、指示灯让给状态机**：`CONFIG_YH_PROTOCOL_ENABLED=y`，但 `YH_WS2812_GPIO=NC`。
  GPIO48 已被 `GetLed()`（`SingleLed`，小智状态灯）占用，不能两路 WS2812/两个 RMT 句柄同刷一脚，
  因此 YH 的 `SET_LED` 为空操作，TCP 通道与其余指令不受影响。
- **OTA 与唤醒词从 `config.json` 注入**（不在代码里硬编码）：`CONFIG_OTA_URL`、`CONFIG_YH_SERVER_HOST/PORT`、
  `CONFIG_CUSTOM_WAKE_WORD="ni hao xiao he"`（开关 `CONFIG_USE_CUSTOM_WAKE_WORD=y`，显示"你好小禾"，阈值 40）、并关掉默认唤醒词 `CONFIG_SR_WN_WN9_NIHAOXIAOZHI_TTS=n`。
- **AEC 在设备端**：`CONFIG_USE_AUDIO_PROCESSOR=y`（ `USE_DEVICE_AEC` 的 depends 前提）＋ `CONFIG_USE_DEVICE_AEC=y` ＋ `CONFIG_USE_SERVER_AEC=n`，
  配合 `AUDIO_INPUT_REFERENCE=true`（MIC3 作回放参考）；运行时双击 BOOT 可在 设备端/关 之间切换。
- **存储**：16MB Flash + 分区表 `partitions/v2/16m.csv`（含 8MB assets SPIFFS 区，烧 `generated_assets.bin`）。

## 与档案的已确认偏差说明

| 项 | 结论 |
| --- | --- |
| Flash 模式 DIO | **按档案 §1 显式指定**（`CONFIG_ESPTOOLPY_FLASHMODE_DIO=y` / `QIO=n`）。DIO 对硬件永远安全；若实测模组支持 QIO 想提速，把 `config.json` 里这两行改为 `CONFIG_ESPTOOLPY_FLASHMODE_DIO=n` + `CONFIG_ESPTOOLPY_FLASHMODE_QIO=y` 即可，其余不动。 |
| I2C 400kHz | **按设备侧实现，总线结构体无此字段**：IDF 6.1 的 `i2c_master_bus_config_t` **没有** `scl_speed_hz` 字段（写进去会编译报错 `has no member named 'scl_speed_hz'`），速率由各 device 指定——`main/boards/common/i2c_device.cc` 的编解码/PCA9557 为 400kHz、`InitializeTouch()` 的 FT5x06 为 400kHz，与档案 §3 要求一致。摄像头 SCCB 复用本总线（`sccb_i2c_port=1`）。 |
| GPIO48 用途选择 | 板载 WS2812 只有这一颗，`GetLed()`（状态灯）优先；YH 控灯让位为 NC。若要把 GPIO48 交给 YH，须同时改 `config.h` 的 `YH_WS2812_GPIO` 并删除板实现里的 `GetLed()` 覆写。 |
| **背光极性**（⚠ 2026-10-16 二次订正） | **回退为 `true`（低电平导通点亮）**。中途曾按 TFT 原理图改 `false`，实机仍黑屏且与"Q2 栅极经 R21(10k) **上拉** 3V3"矛盾（上拉 ⇒ P 沟道 ⇒ 拉低才导通）。两条独立证据支持 `true`：① 上游 pristine `config.h:39` 就是 `true`；② `camera板子信息.md:60` 明确"背光 GPIO42，PWM，低电平有效"。**本行以 `true` 为准**。若修好 CS 后实测"亮度调高反而变暗"，再改 `false`。 |
| **bit0 是 LCD_CS 不是复位**（⚠ 2026-10-16 二次订正，原理图最终确认） | 官方 wiki 与 V1.0.1 全板原理图**双确认**：**IO0 = LCD_CS，低电平选通**；原理图备注写明"LCD_CS：IO 扩展芯片输出，非 ESP32-S3 原生 GPIO"。故稳态必须是 **0（选中）**。代码现为 `SetOutputState(0,1) → 延时10ms → SetOutputState(0,0)` + 复位后等 120ms。⚠ **中途"bit0=低电平复位、稳态 1"的结论是错的**（按"LCD 能点亮"反推不可靠——被取消片选时背光照样亮），已回退。 |
| **本屏 FPC 无触摸线**（新增，原理图校准） | 该屏 FPC 引脚中**没有任何 SDA/SCL/INT 触摸信号** → 该屏**本身不带触摸**。预期日志：6 个候选地址（0x38/0x5D/0x14/0x15/0x55/0x5A）**全 NACK**，**属正常，不是故障**，功能不受影响（BOOT 键 + 语音可用）。若板上另有触摸排线/芯片，多型号自动识别会命中并按日志型号处理。 |
| 无 CS / 无 MISO（新增，原理图校准） | 原理图**无 CS 网络**（硬件接地、常选通）、**无 MISO**（单向写）。固件 `CS=NC` 正确；因无 MISO，读 ID / 读状态类操作不可用，**不要据此判"屏坏了"**。 |

## 不要动清单

- `config.json` 的 `manufacturer` / `type` / `target` / `builds[0].name`、**一个字符都不要改**：type 参与 OTA 与设备身份，改了等于换设备。
- `config.h` 的引脚宏**不要凭"能点亮"倒推着改**：现存值已按 V1.0.1 全板原理图校准。DVP 现占 **GPIO4/6/7/8/9/10/11/15/16/17/18/21**；**GPIO3、GPIO46 现已空出**（原理图分别标注为"用户按键"与未连接），音量键若要恢复只能接这两个脚，接别的会撞 DVP。
- 不要把 my-s3-tft 的移植件搬过来：双击表情彩蛋（本板双击按档案 §6 用于 AEC 开关）、圆屏皮肤、`HandleKeyEvent`、1s Tick、SSD1306 备用屏（320×240 横屏不适用，且 GPIO8/9 已被 DVP 占用）。
- 初始化顺序、PCA9557（PA 使能 bit1 / LCD 复位 bit0 / 摄像头电源 bit2）与 BoxAudioCodec 参数保持原样。

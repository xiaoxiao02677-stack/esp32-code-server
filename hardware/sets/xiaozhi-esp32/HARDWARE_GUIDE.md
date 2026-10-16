# ESP32 硬件开发指南

> 当前板型：**立创实战派 S3** `lckfb/szpi-esp32s3`（板型宏 `CONFIG_BOARD_TYPE_LICHUANG_DEV_S3`，产物 `lckfb-lichuang-dev`）
> 固件基线：xiaozhi-esp32 v2.5.1 / ESP-IDF v6.1 / ESP32-S3
> 硬件规格的唯一权威来源：`G:\demo\21_xiaozhi\hardware\small_screen_camera\camera板子信息.md`（见文末"相关文档"）
> 迁移与维护说明：`docs/lckfb-szpi-摄像头板适配说明.md`

本指南**只描述摄像头板**。旧的小屏圆屏板（`my-s3-tft`）文档内容已全部作废。

---

## 1. 硬件规格

| 组件 | 型号 / 规格 | 接口与连接 |
| --- | --- | --- |
| MCU | ESP32-S3（Xtensa LX7 双核） | Flash 16MB（DIO @80MHz）、PSRAM Octal @80MHz |
| LCD | ST7789V，320×240 横屏，16-bit RGB565 | SPI TFT，FPC 座 `AFC01-S14FCC-00`（FPC4，3V3 供电，16pin 座实际用 15 脚）；SPI3：MOSI=40 / SCLK=41 / DC=39 / **CS 硬件接地（原理图无 CS）**、**无 MISO** |
| 背光 | GPIO42，PWM | **高电平有效**（Q2 MOS 高导通点亮）→ `DISPLAY_BACKLIGHT_OUTPUT_INVERT=false`（旧"低电平有效"已被原理图推翻） |
| 触摸 | 多型号自动识别：0x38 FT5x06 / 0x5D·0x14 GT911 / 0x15 CST816S / 0x55 ST7123 / 0x5A CST9217 | 挂在音频 I2C 总线（port1，400kHz）；**本屏 FPC 无触摸线（无 SDA/SCL/INT），6 地址全 NACK 属预期** |
| DAC（扬声器） | ES8311，地址 0x18 | I2S：MCLK38 / WS13 / BCLK14 / DOUT45 |
| ADC（麦克风） | ES7210，地址 0x82（7-bit 0x41） | I2S：DIN12，复用同上 I2S 时序 |
| 功放 / 编解码控制 | PCA9557 IO 扩展器 @0x19 | bit0=LCD 复位、bit1=PA 使能、bit2=摄像头上电（**低有效**） |
| 摄像头 | 8-bit DVP，RGB565，QVGA(320×240) | XCLK=GPIO5 @20MHz，SCCB 复用 I2C port1，fb 在 PSRAM |
| 按键 | BOOT（GPIO0） | 单击 / 双击 / 长按三种语义，无音量键 |
| LED | 板载 WS2812（GPIO48） | 作为系统状态灯（`SingleLed(BUILTIN_LED_GPIO)` 覆写 `GetLed()`） |
| 采样率 | 输入 24kHz / 输出 24kHz | `AUDIO_INPUT_REFERENCE=true` + `CONFIG_USE_DEVICE_AEC=y`（设备端 AEC） |

音频 I2S 引脚：

| 信号 | GPIO | 信号 | GPIO |
| --- | --- | --- | --- |
| MCLK | 38 | WS/LRCK | 13 |
| BCLK | 14 | DOUT → ES8311 | 45 |
| DIN ← ES7210 | 12 | — | — |

### 1.1 显示与触摸参数

| 项目 | 值 |
| --- | --- |
| 分辨率 | 320×240 |
| 方向 | swap_xy=true、mirror_x=true、mirror_y=false |
| SPI 时钟 | 80MHz，mode 2 |
| 反色 | `invert_color(true)` |
| 复位 | 无独立 GPIO 复位脚；RESET(FPC6) 经 R76(10k) 上拉 3V3，由 PCA9557 bit0 驱动 —— **低电平复位，释放态 bit0=1**（原理图备注 RESET 未直连 ESP32） |
| 触摸映射 | swap_xy=1、mirror_x=1；x_max=240、y_max=320 |

#### 1.1.1 FPC 引脚映射（TFT 接口原理图，屏幕侧权威）

| FPC 脚号 | 信号 | 连接 / 说明 |
| --- | --- | --- |
| FPC4 | 座型号 `AFC01-S14FCC-00` | FPC 16pin 座，实际用到 15 脚，供电 3V3 |
| FPC5 | LEDA | 背光阳极，经 **R20(10Ω)** 限流，由 Q2 驱动 |
| FPC6 | RESET | 经 **R76(10k)** 上拉至 3V3；**低电平复位**；原理图未直连 ESP32 |
| FPC7 | LCD_DC | **GPIO39** |
| FPC8 | LCD_MOSI | **GPIO40** |
| FPC9 | LCD_SCK | **GPIO41** |
| FPC10 | 3V3 | 屏供电 |
| FPC11 | 3V3 | 屏供电（与 FPC10 并联） |
| FPC15 | GND | 地 |
| —（非 FPC） | LCD_BL | **GPIO42** → Q2 背光驱动级（PWM） |

其他确认事实：**无 CS**（硬件接地、常选通）、**无 MISO**（SPI 单向写，不能读 ID/状态）、**无触摸信号线**（该屏不带触摸）。

#### 1.1.2 背光电路（Q2，高电平点亮）

```
GPIO42 (PWM) --[R23 1k]--> Q2 (MOS 管) --[R20 10Ω]--> LEDA (FPC5) --> 背光 LED
                            栅极 [R21 10k] 上拉至 3V3
```

| 元件 | 值 | 作用 |
| --- | --- | --- |
| R23 | 1k | IO42 → Q2 栅/基极限流 |
| R21 | 10k | Q2 栅极上拉至 3V3（IO42 高阻时 Q2 默认导通 → 上电瞬间背光可能闪亮，属正常） |
| R20 | 10Ω | LEDA 回路限流 |
| Q2 | MOS 管 | 背光开关 / PWM 调光 |

| 结论 | 内容 |
| --- | --- |
| 极性 | **IO42 高电平 → Q2 导通 → 点亮背光（高电平有效）** |
| 固件 | `DISPLAY_BACKLIGHT_OUTPUT_INVERT = **false**`（PWM 不反相） |
| 回退 | 若"亮度条越高越暗"，改回 `true` |
| 旧说法 | "低电平有效 / 主动低"已被原理图推翻 |

#### 1.1.3 复位电路（R76 上拉，低电平复位）

```
3V3 --[R76 10k]--+--> RESET (FPC6)
                  |
          PCA9557 bit0（LCD 与触摸共享）
```

| 结论 | 内容 |
| --- | --- |
| 极性 | **低电平复位**（R76 上拉保证默认不复位） |
| 释放态 | **bit0 = 1（不复位）** |
| 固件 | `InitializeSt7789Display()` 发规范脉冲：**bit0=0 保持 20ms → bit0=1 保持 50ms**，末态保持 1 |
| 旧代码问题 | 原 `SetOutputState(0, 0)` 会把屏幕一直按住复位（低电平复位下 0 = 复位中） |
| 日志 | `PCA9557 bit0 (LCD/touch reset, active-low) held at 1 (1=no reset)` |
| 备注 | 原理图 RESET **未直连 ESP32**，实机需确认是否已额外接线；若未接，靠 R76 上拉也能自行释放 |

### 1.2 摄像头参数

| 项目 | 值 |
| --- | --- |
| 接口 / 格式 | 8-bit DVP，PIXFORMAT_RGB565，FRAMESIZE_QVGA |
| XCLK | GPIO5，20MHz |
| SCCB | SCL=GPIO2（`sccb_i2c_port=1`，与音频 I2C 共总线） |
| 帧缓冲 | `fb_count=1`，`fb_location=CAMERA_FB_IN_PSRAM` |
| 抓取模式 | `CAMERA_GRAB_WHEN_EMPTY` |
| JPEG 质量 | 12 |
| 上电 | PCA9557 bit2（低有效） |

---

## 2. 环境配置

### 2.1 ESP-IDF 工具链

| 项目 | 值 |
| --- | --- |
| IDF 路径 | `D:\INSTALL\esp\v6.1\esp-idf` |
| 工具根目录 | `D:\INSTALL\esp`（`IDF_TOOLS_PATH`） |
| Python 环境 | `D:\INSTALL\esp\tools\python\v6.1\venv` |
| 临时目录 | `D:\INSTALL\esp\tmp`（必须，避免 gcc 临时文件被杀软拦截） |

### 2.2 项目路径

| 项目 | 路径 |
| --- | --- |
| 源码 | `G:\demo\21_xiaozhi\hardware\small_screen_camera\xiaozhi-esp32` |
| 构建输出 | `...\xiaozhi-esp32\build` |
| 板目录 | `...\xiaozhi-esp32\main\boards\lckfb\szpi-esp32s3` |
| 分区表 | `...\xiaozhi-esp32\partitions\v2\16m.csv` |

---

## 3. 开发命令

> 编译 / 烧录均由**用户手动执行**，脚本不会自动触发。

### 3.1 编译

```batch
build_lckfb_s3.bat
```

### 3.2 烧录

```batch
yh_flash.bat COM3
```

不带参数时自动探测 CP210x / CH340 / USB-JTAG 串口：

```batch
yh_flash.bat
```

### 3.3 串口监视

```batch
monitor.bat COM3
```

```batch
monitor.bat
```

### 3.4 等价裸命令

编译：

```batch
set PYTHONPATH=
set MSYSTEM=
set IDF_TOOLS_PATH=D:\INSTALL\esp
set IDF_PATH=D:\INSTALL\esp\v6.1\esp-idf
set IDF_PYTHON_ENV_PATH=D:\INSTALL\esp\tools\python\v6.1\venv
set "TEMP=D:\INSTALL\esp\tmp"
set "TMP=D:\INSTALL\esp\tmp"
call D:\INSTALL\esp\v6.1\esp-idf\export.bat
cd /d G:\demo\21_xiaozhi\hardware\small_screen_camera\xiaozhi-esp32
python scripts\build.py lckfb/szpi-esp32s3
```

烧录（**全量，含 assets 分区**）：

```batch
cd /d G:\demo\21_xiaozhi\hardware\small_screen_camera\xiaozhi-esp32\build
python -m esptool --chip esp32s3 -p COM3 -b 460800 --before default-reset --after hard-reset ^
  write-flash --flash-mode dio --flash-size 16MB --flash-freq 80m ^
  0x0 merged-binary.bin ^
  0x800000 generated_assets.bin
```

分量烧录（需要单独更新某个分区时）：

```batch
python -m esptool --chip esp32s3 -p COM3 -b 460800 --before default-reset --after hard-reset ^
  write-flash --flash-mode dio --flash-size 16MB --flash-freq 80m ^
  0x0 bootloader\bootloader.bin ^
  0x8000 partition_table\partition-table.bin ^
  0x20000 xiaozhi.bin ^
  0x800000 generated_assets.bin
```

监视：

```batch
python -m serial.tools.miniterm COM3 115200
```

### 3.5 构建产物

| 文件 | 说明 |
| --- | --- |
| `build/merged-binary.bin` | 一体烧录包（bootloader+分区表+app），烧 `0x0` |
| `build/generated_assets.bin` | 字体 / 表情 / 音效资源包，烧 `0x800000` |
| `build/xiaozhi.bin` | 仅 app（OTA 用，不含 assets） |

---

## 4. 分区表（`partitions/v2/16m.csv`）

| 分区 | 类型 | 偏移 | 大小 | 说明 |
| --- | --- | --- | --- | --- |
| nvs | data/nvs | 0x9000 | 16KB | 配置存储 |
| otadata | data/ota | 0xD000 | 8KB | OTA 启动选择 |
| phy_init | data/phy | 0xF000 | 4KB | 射频校准 |
| ota_0 | app | 0x20000 | 0x3F0000（≈3.9MB） | 应用槽 A |
| ota_1 | app | — | 0x3F0000（≈3.9MB） | 应用槽 B |
| assets | data/spiffs | 0x800000 | 8MB | 字体/表情/音效资源包 |

---

## 5. GPIO 分配

| GPIO | 功能 | FPC 脚号 | 所属设备 |
| --- | --- | --- | --- |
| 0 | BOOT 按键 | — | 输入（内部上拉） |
| 1 | I2C SDA（port1，400kHz） | — | ES8311 / ES7210 / PCA9557 / 触摸 / 摄像头 SCCB |
| 2 | I2C SCL（port1，400kHz） | — | 同上 |
| 3 | VSYNC | — | 摄像头 DVP |
| 4 | D6 | — | 摄像头 DVP |
| 5 | XCLK（20MHz） | — | 摄像头 DVP |
| 6 | D5 | — | 摄像头 DVP |
| 7 | PCLK | — | 摄像头 DVP |
| 8 | D2 | — | 摄像头 DVP |
| 9 | D7 | — | 摄像头 DVP |
| 12 | I2S DIN | — | ES7210（麦克风输入） |
| 13 | I2S WS/LRCK | — | ES8311 + ES7210 |
| 14 | I2S BCLK | — | ES8311 + ES7210 |
| 15 | D4 | — | 摄像头 DVP |
| 16 | D0 | — | 摄像头 DVP |
| 17 | D3 | — | 摄像头 DVP |
| 18 | D1 | — | 摄像头 DVP |
| 38 | I2S MCLK | — | ES8311 + ES7210 |
| 39 | DC（LCD_DC） | **FPC7** | ST7789 |
| 40 | SPI MOSI（LCD_MOSI） | **FPC8** | ST7789（SPI3_HOST） |
| 41 | SPI SCLK（LCD_SCK） | **FPC9** | ST7789（SPI3_HOST） |
| 42 | 背光 PWM（LCD_BL） | 非 FPC（经 Q2） | LCD 背光，**高电平有效**（`DISPLAY_BACKLIGHT_OUTPUT_INVERT=false`） |
| 45 | I2S DOUT | — | ES8311（扬声器输出） |
| 46 | HREF | — | 摄像头 DVP |
| 48 | WS2812 数据 | — | 板载状态灯（系统状态指示） |

屏幕侧**非 GPIO** 的 FPC 信号（不占 MCU 引脚）：RESET=**FPC6**（经 R76 上拉，由 PCA9557 bit0 驱动，低电平复位）、LEDA=**FPC5**（经 R20 限流，由 Q2 驱动）、3V3=**FPC10/11**、GND=**FPC15**。

> **冲突提示**：GPIO3 / GPIO46 已被摄像头 VSYNC / HREF 占用，本板因此**没有音量键**（`VOLUME_UP/DOWN_BUTTON_GPIO = GPIO_NUM_NC`）。
> GPIO8 / GPIO9 被 DVP D2/D7 占用，旧圆屏板的 SSD1306 备用屏（SCL=9/SDA=8）**无法迁移**。
> 屏幕侧极性以 TFT 原理图为准：背光**高电平点亮**、复位**低电平复位**（旧"低电平有效/主动低"说法已作废）。

---

## 6. 按键与指示灯语义

| 操作 | 行为 |
| --- | --- |
| BOOT 单击 | 开始 / 打断对话；设备处于 `Starting` 状态时进入 Wi-Fi 配网模式 |
| BOOT 长按（配网防呆，1s） | 设备在 `Starting` 且**开机 30 秒内**才进入配网，超时忽略（防"按键即重配网"死循环） |
| BOOT 双击 | 切换设备端 AEC 开 / 关（`CONFIG_USE_DEVICE_AEC` 生效时，仅 Idle 态可切） |
| BOOT 长按 | PressToTalk 按住说话（需 MCP 工具 `PressToTalk` 已开启） |
| LED（GPIO48） | 系统状态灯：`SingleLed(BUILTIN_LED_GPIO)` 覆写 `GetLed()` |

MCP 工具：`self.system.reconfigure_wifi`（重新配网）、`PressToTalkMcpTool`（长按说话 / 单击唤醒模式切换）。

---

## 7. YH 协议

YH（屿禾）设备协议是独立的设备管理旁路通道，与小智主业务通道（WebSocket/MQTT）互不影响：

| 项目 | 值 |
| --- | --- |
| 服务端 | TCP `sandyun.top:12399`（22222 是服务器 SSH 端口，非 YH 协议端口） |
| 开关 | `CONFIG_YH_PROTOCOL_ENABLED=y` |
| 协议 | newline-delimited JSON（每行一条 JSON 消息） |
| 消息类型 | HELLO / ADVERTISEMENT / HEARTBEAT / COMMAND / ACK |
| 功能 | 设备状态同步、远程指令（如 SET_LED） |
| YH 专用 WS2812 | 设为 `GPIO_NUM_NC`（空操作），避免与状态灯抢占 GPIO48 / RMT 通道 |

---

## 8. 定制服务

| 项目 | 值 |
| --- | --- |
| OTA 地址 | `http://sandyun.top:8002/xiaozhi/ota/` |
| 自定义唤醒词 | "你好小禾" `ni hao xiao he`（Multinet7 量化，阈值 40） |
| 关闭的内置词 | 显式关闭 `CONFIG_SR_WN_WN9_NIHAOXIAOZHI_TTS` |
| Flash 模式 | DIO @80MHz（按板卡档案显式指定；实测支持 QIO 时可改回，见板 README） |
| PSRAM | Octal @80MHz |

---

## 9. 目录结构（当前工程）

```
xiaozhi-esp32/
├── main/
│   ├── main.cc                 # 主入口
│   ├── application.cc/h        # 应用逻辑
│   ├── CMakeLists.txt          # BOARD_TYPE -> BOARD_DIR 映射
│   ├── Kconfig.projbuild       # 板型 choice / YH / 唤醒词等配置
│   ├── led/                    # single_led / gpio_led / circular_strip
│   ├── display/                # lcd_display / emote_display ...
│   ├── audio/                  # codecs（box_audio_codec 等）
│   ├── boards/
│   │   ├── common/             # board.cc/h：GetLed() 默认为 NoLed
│   │   ├── my-s3-tft/          # 旧圆屏板（保留，不再构建）
│   │   └── lckfb/
│   │       ├── szpi-esp32c3/
│   │       └── szpi-esp32s3/   # ★ 当前板
│   │           ├── config.h              # 全部硬件引脚宏（唯一硬件事实来源）
│   │           ├── config.json           # 板身份 + sdkconfig 追加项
│   │           ├── lichuang_dev_board.cc # 板级实现，DECLARE_BOARD(LichuangDevBoard)
│   │           └── README.md             # 板级说明
│   └── yh/
│       ├── yh_protocol.cc/h    # YH 设备协议
│       └── yh_ws2812_led.cc/h  # YH 专用 WS2812（本板置 NC）
├── partitions/
│   └── v2/16m.csv              # 当前分区表
├── scripts/
│   ├── build.py                # 板型构建入口
│   └── ...                     # assets 生成、语言、音频调试等工具
├── docs/                       # 协议 / 审计 / 适配说明文档
├── build_lckfb_s3.bat          # 编译（摄像头板）
├── yh_flash.bat                # 烧录
├── monitor.bat                 # 串口监视
├── workflow.bat                # 组合工作流
└── sdkconfig                   # 由 build.py 按板型生成，勿手工长期维护
```

板级初始化顺序（`lichuang_dev_board.cc`）：

```
InitializeI2c → InitializeSpi → InitializeSt7789Display → InitializeTouch
  → InitializeButtons → InitializeCamera → InitializeTools
  → GetBacklight()->RestoreBrightness()
```

必须实现的接口：`GetAudioCodec()` / `GetDisplay()` / `GetBacklight()` / `GetCamera()`（本板另覆写 `GetLed()`）。

---

## 10. 调试技巧

### 查看编译日志

```batch
idf.py build -v
```

### 清理构建

```batch
idf.py fullclean
```

### 查看分区表

```batch
idf.py partition-table
```

### 擦除 Flash

```batch
idf.py -p COM3 erase-flash
```

### 只看板级 / YH 日志

串口监视后用关键字过滤：`LichuangDevBoard`、`camera`、`FT5x06`、`ES8311`、`ES7210`、`[YH]`。

---

## 11. 常见问题

### 1. 编译失败 - Permission denied

确保 TEMP / TMP 指向无空格路径：

```batch
set TEMP=D:\INSTALL\esp\tmp
set TMP=D:\INSTALL\esp\tmp
```

### 2. 首次构建报 `Cannot validate board selection: sdkconfig was not generated`

sdkconfig 尚未生成，属已知现象，**重跑一次 `build_lckfb_s3.bat` 即可**。

### 3. 烧录失败 - Connection refused / 连不上

- 检查 COM 端口是否正确；
- 确保 ESP32-S3 处于下载模式（按住 BOOT 再点 RESET）；
- 降低波特率重试：`-b 115200`。

### 4. 串口无输出

- 波特率 115200；
- 确认 COM 端口与数据线（部分线仅充电）；
- 确认没有其它串口工具占用端口。

### 5. 开机黑屏 / 白屏

- 背光 GPIO42 **高电平有效**（Q2 MOS 高导通点亮），确认 `DISPLAY_BACKLIGHT_OUTPUT_INVERT=false`；若"亮度越高越暗"则改回 `true`；
- LCD 复位经 RESET(FPC6) + PCA9557 bit0 控制，**低电平复位**，释放态应为 **bit0=1** → 看日志 `PCA9557 bit0 (LCD/touch reset, active-low) held at 1`；确认 I2C（GPIO1/2）通信正常；
- 查 SPI GPIO39/40/41 与 FPC7/8/9 焊接、3V3(FPC10/11) 与 GND(FPC15)；
- 确认烧录时 `--flash-mode dio` 与 16MB Flash 匹配。

### 6. 有画面但触摸不准 / 开机报触摸 NACK

- 触摸已改为**多型号自动识别**（0x38 / 0x5D·0x14 / 0x15 / 0x55 / 0x5A），谁 ACK 用谁；
- **本屏 FPC 无触摸线**：6 个地址全 NACK 属**预期，不是故障**，功能不受影响（BOOT 键 + 语音可用）；
- 若某地址 ACK：按日志识别出的型号核对方向参数 `swap_xy=1`、`mirror_x=1`，`x_max=240`、`y_max=320`。

### 7. 无声 / 录音无数据

- PA 使能走 PCA9557 bit1（`EnableOutput` 中置 1/0）；
- 确认 ES8311(0x18) / ES7210(0x82) 在 I2C 总线上可探测到；
- 24kHz 采样率两端需一致。

### 8. 摄像头初始化失败

- 确认 PCA9557 bit2 已拉低上电；
- 确认 XCLK(GPIO5) 20MHz 与 `sccb_i2c_port=1`；
- `fb_count=1` + PSRAM，确认 PSRAM 已启用且 `CONFIG_CAMERA_PSRAM_DMA=y`。

### 9. ⚠ assets 分区必须全量烧录，OTA 只刷 app

| 场景 | 是否刷 assets（0x800000） |
| --- | --- |
| 首次烧录 / 换板 / 换分区表 | **必须刷**，否则缺字体表情，界面乱码或崩溃 |
| 日常 OTA 升级 | **不刷**，OTA 只更新 app 分区 |
| `yh_flash.bat`（`@flash_args`） | 只覆盖 app 相关分区，**首次必须手工补刷 `generated_assets.bin`** |

```batch
python -m esptool --chip esp32s3 -p COM3 -b 460800 write-flash 0x800000 build\generated_assets.bin
```

### 10. 切回旧板

```batch
python scripts\build.py my-s3-tft
```

两块板目录互不影响，详见 `docs/lckfb-szpi-摄像头板适配说明.md` 的"回滚方法"。

---

## 12. 版本信息

- ESP-IDF: v6.1
- 框架: C++
- 目标芯片: ESP32-S3
- 构建系统: CMake + idf.py

---

## 13. 相关文档

| 文档 | 路径 |
| --- | --- |
| 板卡硬件档案（权威） | `G:\demo\21_xiaozhi\hardware\small_screen_camera\camera板子信息.md` |
| 摄像头板适配说明 | `docs/lckfb-szpi-摄像头板适配说明.md` |
| 实机首跑排障手册 | `docs/lckfb-实机首跑排障.md`（§2 屏幕原理图校准：FPC 映射、背光/复位极性、无 CS/无触摸线） |
| TFT 接口原理图（用户提供） | 屏幕侧最终权威：FPC `AFC01-S14FCC-00`、背光 Q2/R21/R23/R20、复位 R76 |
| YH 设备协议 | `docs/YH-Device-Protocol.md` |
| YH 通信架构审计 | `docs/Xiaozhi-YH-通信架构审计报告.md` |
| 自定义板开发 | `docs/custom-board_zh.md` |
| 分区表说明 | `partitions/v2/README.md` |

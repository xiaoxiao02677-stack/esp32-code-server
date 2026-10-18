# ⚠️ 先读这里：引脚**全部为推测值**，未经过实物核实

> ## 🚨 未经核实，请勿直接烧录到真机 🚨
>
> 本版型来自《第二代 大屏幕固件信息.md》的固件字符串推断，**没有原理图**。
> 该资料自己在「第 5 节 关键结论」里写明：
>
> > 主控、存储、无线和外设型号可信度较高；**精确 GPIO 引脚可信度较低**，
> > 因为固件无调试符号，**且多处引脚存在冲突**。
>
> 资料给出的引脚**互相打架，无法直接使用**，本版型已按规则重新分配了一批引脚
> （见下表的「原资料值 → 本版型采用值」列）。
> 因此 `set.json` 里 `pins_verified = false`。
>
> **烧录前必须至少完成下列一项核实**；核实通过后请把 `pins_verified` 改成 `true`。

## 如何核实（按推荐顺序）

1. **读完整 16MB flash 并解析 NVS / 分区表**
   `esptool.py -p COM10 -b 921600 read_flash 0x0 0x1000000 full_16mb.bin`
   资料里已有的 `full_fw.bin` 只是 64KB 片段，信息不足。
2. **解析 NVS 命名空间**：yuhe 固件会把 Wi-Fi、设备配置写进 NVS；
   但**注意 NVS 里通常不存 GPIO**，这一步主要用于还原板型名称与历史配置，
   便于反查到对应的公开板型。
3. **找原理图**：拿到板型号（资料里 MAC 为 `b8:1f:3f:c3:96:20`）后直接查同名开发板。
4. **万用表/示波器实测**：断电蜂鸣档逐点量 ILI9341 排针与 ESP32-S3 的连通性，
   这是最可靠的兜底办法。
5. **最小化验证固件**：先只点亮屏幕（不动 I2S），确认 SPI 组正确后再加音频。

---

## 1. 引脚冲突与我的处理（核心）

| 信号 | 原资料值 | 本版型采用值 | 改动类型 | 理由 |
|---|---|---|---|---|
| ES8311 I2S MCLK | GPIO2 | **GPIO2** | 沿用 | I2S 优先，资料值保留 |
| ES8311 I2S BCLK | GPIO46 | **GPIO46** | 沿用 | I2S 优先，资料值保留 |
| ES8311 I2S WS | GPIO45 | **GPIO45** | 沿用 | I2S 优先，资料值保留 |
| ES8311 I2S DIN | GPIO7 | **GPIO7** | 沿用 | I2S 优先，资料值保留 |
| ES8311 I2S DOUT | **（资料未给出）** | **GPIO10** | 🆕 我补 | 全双工必须有 DOUT；选不与 I2S/SPI/I2C/BOOT 冲突的空闲脚 |
| ES8311 I2C SDA | **（资料未给出）** | **GPIO8** | 🆕 我补 | 资料只给了触摸 I2C 候选 `SDA=1/8`，取 8（1 留给触摸候选） |
| ES8311 I2C SCL | **（资料未给出）** | **GPIO9** | 🆕 我补 | 资料候选 `SCL=2/9`；2 已被 I2S MCLK 占用，只能取 9 |
| LCD CS | GPIO5 | **GPIO5** | 沿用 | 与 I2S/I2C 均不冲突 |
| LCD DC | GPIO6 | **GPIO6** | 沿用 | DC/SCK 同脚冲突时保留 DC（ILI9341 必须靠 DC 区分命令/数据） |
| LCD RST | GPIO4 | **GPIO4** | 沿用 | 资料里 SD-CS 也是 4，但本版型**不实现 SD**，故不冲突 |
| LCD MOSI | GPIO7 | **GPIO11** | 🔧 我改 | **与 I2S-DIN 撞车**；I2S 优先，把 LCD MOSI 挪到空闲 GPIO11 |
| LCD SCK | GPIO6 | **GPIO12** | 🔧 我改 | **与 LCD-DC 撞车**（DC 与 SCK 不可能同脚）；DC 保留 6，SCK 挪到 GPIO12 |
| LCD MISO | GPIO1 | **NC（不接）** | 🔧 我改 | ILI9341 只读几乎不用；且 GPIO1 是触摸 I2C SDA 候选，直接不接更安全 |
| LCD BL（背光） | **（资料未给出）** | **GPIO14** | 🆕 我补 | 2.8" ILI9341 模块普遍有 BL 脚；取空闲非 strapping 的 GPIO14 |
| BOOT 键 | GPIO0 | **GPIO0** | 沿用 | ESP32-S3 BOOT 键通用惯例 |
| 板载 LED | **（资料未给出）** | **GPIO48** | 🆕 我补 | ESP32-S3 常见 WS2812 位置 |

**总共 8 个引脚是我自行补充或改动的**（🆕 新补 + 🔧 改动）：
I2S DOUT、I2C SDA、I2C SCL、LCD MOSI、LCD SCK、LCD MISO、LCD BL、板载 LED。

## 2. ESP32-S3 保留脚（已全部避开）

| 范围 | 原因 | 本版型是否占用 |
|---|---|---|
| GPIO26–32 | 内联 flash / PSRAM（Quad） | ❌ 未占用 |
| GPIO33–37 | Octal PSRAM（本板是 8MB Octal PSRAM） | ❌ 未占用 |
| GPIO19 / 20 | USB OTG（本板用 USB-Serial/JTAG 下载） | ❌ 未占用 |
| GPIO0 | 启动 strapping（BOOT 键） | ✅ 仅作按键，低电平触发 |
| GPIO3 / 45 / 46 | strapping 脚 | GPIO45/46 被 I2S 占用（资料指定，属可接受用法，且外部无强上拉即可正常启动） |

> ⚠️ 若实测发现板子偶尔进不了下载模式，首先怀疑 GPIO45/46 的外部上下拉。

## 3. 引脚总表（config.h 一览）

| 分类 | 宏 | 值 |
|---|---|---|
| 音频 I2S | `AUDIO_I2S_GPIO_MCLK` | GPIO2 |
| | `AUDIO_I2S_GPIO_BCLK` | GPIO46 |
| | `AUDIO_I2S_GPIO_WS` | GPIO45 |
| | `AUDIO_I2S_GPIO_DIN` | GPIO7 |
| | `AUDIO_I2S_GPIO_DOUT` | GPIO10 🆕 |
| 音频 I2C | `AUDIO_CODEC_I2C_SDA_PIN` | GPIO8 🆕 |
| | `AUDIO_CODEC_I2C_SCL_PIN` | GPIO9 🆕 |
| | `AUDIO_CODEC_PA_PIN` | NC（资料未提 PA 控制） |
| | `AUDIO_CODEC_ES8311_ADDR` | `ES8311_CODEC_DEFAULT_ADDR` |
| 屏幕 | `DISPLAY_CS_PIN` | GPIO5 |
| | `DISPLAY_DC_PIN` | GPIO6 |
| | `DISPLAY_RST_PIN` | GPIO4 |
| | `DISPLAY_MOSI_PIN` | GPIO11 🔧 |
| | `DISPLAY_SCK_PIN` | GPIO12 🔧 |
| | `DISPLAY_MISO_PIN` | NC 🔧 |
| | `DISPLAY_BACKLIGHT_PIN` | GPIO14 🆕 |
| | `LCD_SPI_HOST` | `SPI2_HOST` |
| | `DISPLAY_SPI_SCLK_HZ` | 20 MHz |
| 交互 | `BOOT_BUTTON_GPIO` | GPIO0 |
| | `BUILTIN_LED_GPIO` | GPIO48 🆕 |
| 面板 | 分辨率 | 320 × 240，16bpp，BGR，SWAP_XY=true，INVERT_COLOR=true |

采样率：输入 24000 Hz / 输出 24000 Hz（ES8311 常见配置）。

## 4. 外设状态

| 外设 | 状态 | 说明 |
|---|---|---|
| ILI9341 2.8" SPI 屏 | ✅ 已实现 | SCL/SDA 之外的 SPI 组为推测值 |
| ES8311 音频编解码 | ✅ 已实现 | I2S 四脚沿用资料值；I2C 控制脚为推测值 |
| BOOT 键（GPIO0） | ✅ 已实现 | 单击：启动中进配网 / 运行态切换对话；长按：进配网 |
| WS2812 状态灯 | ✅ 已实现 | 引脚推测 |
| **I2C 触摸屏** | ⛔ **刻意不实现** | 资料记录：`存在但初始化失败 touch ic error!`，芯片型号与 I2C 引脚都无法确定（候选 SDA=1/8、SCL=2/9）。留到拿到原理图后再加 |
| **SD 卡槽** | ⛔ **刻意不实现** | 资料记录存在（SD card Test OK），但给出的 SPI 脚（CS=4、MOSI=7、MISO=1、SCK=6）与 LCD/I2S 全部冲突，无法与屏幕共存于同一组引脚。留到拿到原理图后再加 |
| **设备侧 AEC** | ⛔ **刻意关闭** | `config.json` 里**没有** `CONFIG_USE_DEVICE_AEC=y`。原因：ES8311 codec 不提供回采参考通道（`main/audio/codecs/es8311_audio_codec.cc` 中 `input_reference_` 硬编码为 `false`），没有回采就无法做设备侧 AEC。**这是刻意选择，不是漏配，请不要补上。** 关闭 AEC 也不会导致「播报被自己打断」：Application 在 AEC 不生效时会自动回落到「播完再听」 |

## 5. 构建

```bash
# 交互式选择版型（会打印 pins_verified=false 的醒目警告）
python hardware/sets/build.py

# 只确认能被扫到
python hardware/sets/build.py --list
```

`build.py` 会自动完成：菜单选择 → 文件同步到 `<FW>/main/boards/yuhe/yh-big-ili9341/`
→ Kconfig / CMakeLists 注册 → 调用固件 `scripts/build.py`。

## 6. 参考模板

- **主模板**：`<FW>/main/boards/freenove-esp32s3-display-2.8-lcd/`
  同为 ESP32-S3 + ILI9341 2.8" 320x240 + ES8311，屏与 codec 的初始化流程直接照搬；
  字体 `font_noto_sans_basic_20_4` / `font_material_symbols_20_4` 也取自它。
- **BOOT 键交互习惯**：参考 `<FW>/main/boards/yuhe/1.54tft-wifi/yuhe-1.54tft-wifi.cc`。

模板中被**去掉**的部分：I2C 触摸驱动（本版型不实现触摸）、
`AdcBatteryMonitor` 电量检测（本版型无电池相关引脚信息）。

# bigscreen-s3 引脚分配表

> 依据《99 大屏幕固件信息.md》+ `freenove-esp32s3-display-2.8-lcd` 参考板交叉校准。
> 99 文档自述「精确 GPIO 引脚可信度较低」，以下消解了原文档的引脚冲突。

## 冲突消解说明

99 文档原文存在三处引脚冲突（一个 GPIO 无法同时做两件事）：

| 冲突 GPIO | 99 原文用法 A | 99 原文用法 B | 消解结果 |
|---|---|---|---|
| GPIO6 | LCD DC | LCD SCK / SD SCK | **保留 DC=6**；SCK 移到 GPIO12 |
| GPIO7 | I2S DIN（麦克风） | LCD MOSI / SD MOSI | **保留 I2S DIN=7**；LCD MOSI 移到 GPIO13 |
| GPIO1 | 触摸 SDA / SD MISO | LCD MISO | 触摸/SD 本阶段不启用，GPIO1 保留给 PA |

消解原则：**音频 I2S 引脚来自固件 I2S 外设探测（es8311 字符串旁），可信度最高，全部保留**；显示控制脚（CS/DC/RST）与音频无冲突，保留；显示 SPI 数据脚（SCK/MOSI）与音频冲突，重新分配到干净 GPIO 区（12/13）。

## 最终引脚分配（config.h）

### ES8311 音频（I2S + I2C）

| 功能 | GPIO | 来源 |
|---|---|---|
| I2S MCLK | 2 | 99 文档 |
| I2S BCLK (SCK) | 46 | 99 文档 |
| I2S WS (LRC) | 45 | 99 文档 |
| I2S DIN（麦克风） | 7 | 99 文档 |
| I2S DOUT（扬声器） | 8 | 推测（99 未给，DIN 相邻） |
| PA 使能 | 1 | 推测（99 未给） |
| I2C SDA（ES8311 控制） | 11 | 推测（99 未给） |
| I2C SCL（ES8311 控制） | 10 | 推测（99 未给） |

### ILI9341 显示（SPI，320x240 横屏）

| 功能 | GPIO | 来源 |
|---|---|---|
| CS 片选 | 5 | 99 文档 |
| DC 数据/命令 | 6 | 99 文档 |
| RST 复位 | 4 | 99 文档 |
| SCK 时钟 | 12 | **消解值**（原 SCK=6 与 DC 冲突） |
| MOSI 主出 | 13 | **消解值**（原 MOSI=7 与 I2S DIN 冲突） |
| MISO 主入 | 悬空 | 屏只写不读 |
| 背光 | 47 | 推测（99 未给） |
| SPI 时钟 | 40 MHz | ILI9341 安全值 |

### 其他

| 功能 | GPIO |
|---|---|
| BOOT 按键 | 0 |
| 板载 LED | 无（未探测到） |

### 本阶段不启用

- **I2C 触摸屏**：型号未定且 `touch ic error` 初始化失败——跳过（如后续确认型号为 FT6336/GT911 等，可参照 freenove 板的 TouchDriver 移植）
- **SD 卡**：与显示/音频引脚冲突，未分配

## 实测修改指引

烧录后若异常，改 `main/boards/bigscreen-s3/config.h` 对应宏即可（无需动 .cc）：

| 症状 | 优先检查 |
|---|---|
| 白屏/花屏 | `DISPLAY_SCK_PIN`(12) / `DISPLAY_MOSI_PIN`(13) 是否与实际接线一致；颜色反了改 `DISPLAY_INVERT_COLOR`；方向不对改 `DISPLAY_SWAP_XY` / `MIRROR_X/Y` |
| 完全黑屏 | `DISPLAY_BACKLIGHT_PIN`(47) 与 `DISPLAY_BACKLIGHT_OUTPUT_INVERT` |
| 无声 | `AUDIO_I2S_GPIO_DOUT`(8) / `AUDIO_CODEC_PA_PIN`(1)；ES8311 初始化失败查 I2C 脚 10/11 |
| 麦克风无输入 | `AUDIO_I2S_GPIO_DIN`(7) |
| 屏幕镜像/颠倒 | 调 `DISPLAY_MIRROR_X/Y` 与 `DISPLAY_SWAP_XY` 四个组合 |

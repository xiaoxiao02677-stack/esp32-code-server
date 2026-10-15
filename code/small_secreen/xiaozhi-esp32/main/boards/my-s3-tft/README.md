# my-s3-tft

自定义板卡：ESP32-S3-N16R8 + ST7789 240×240 SPI LCD（主屏）/ SSD1306 128×64 I2C OLED（备用屏）+ MAX98357A I2S 功放。

## 硬件

| 外设 | 引脚 |
|---|---|
| 主屏 ST7789 SCL / SDA / RST / DC / CS / BL | GPIO21 / 47 / 45 / 40 / 41 / 42 |
| 备用屏 SSD1306 SCL / SDA（VCC=3V3, GND） | GPIO9 / 8 |
| 功放 BCLK / LRC / DIN | GPIO15 / 16 / 7 |
| BOOT 按键 | GPIO0 |
| 麦克风 INMP441（已接线） | WS=GPIO4, SCK=GPIO5, DIN=GPIO6 |

- Flash 16MB（`partitions/v2/16m.csv`），PSRAM 8MB（八线，`sdkconfig.defaults.esp32s3` 默认已开）
- MAX98357A：VIN=3.3V 供电，GAIN 接 GND（3.3V 下实际增益 12dB，5V 时为 15dB），SD 接 3.3V 常使能（输出左声道）；固件默认音量 50%，音量偏小时可通过 MCP "设置音量" 调高
- 麦克风 INMP441 已按上表接线（VDD=3.3V, L/R=GND 左声道），I2S RX 正常收音，无需额外配置。

## 屏幕自动切换

开机时固件先在 SCL=9/SDA=8 上探测 I2C 地址 0x3C：

- **探测到** → 使用备用屏方案（SSD1306 128×64 I2C OLED，仅 VCC/GND 两根电源线）
- **探测不到** → 回退主屏方案（ST7789 240×240 SPI，完整 6 线接法 + 背光）

备用屏与主屏引脚互相独立，无需改代码或重烧固件即可换屏。注意：备用屏模式为单色基础 UI（状态/表情/对话），无圆屏皮肤的时间/电量/气泡与按键彩蛋。

## 构建

```sh
# 需要 ESP-IDF >= v6.0.1（推荐 v6.1），IDF 5.x 不支持
python scripts/build.py my-s3-tft --name my-s3-tft
```

## 说明

- 显示驱动复用 `SpiLcdDisplay`（ST7789，SPI3，40MHz，标准 240×240 无偏移，颜色反转开）。
- 若屏幕方向/颜色不对：调 `config.h` 中 `DISPLAY_MIRROR_X/Y`、`DISPLAY_SWAP_XY`、`DISPLAY_INVERT_COLOR`。
- 无 LED（默认 `NoLed`）、无电池。BOOT 键 = 对话/停止，开机时按下进入 WiFi 配网。

# bigscreen-s3 引脚分配表（v2，已修正）

> **板卡鉴定**：Freenove ESP32-S3 Display 2.8"（或同布线套板）。
> v1 依据《99 大屏幕固件信息.md》的字符串推断分配引脚，实测 ES8311 I2C 无 ACK 导致启动 abort。
> 修正依据：该板官方原理图（仓库 `main/boards/freenove-esp32s3-display-2.8-lcd/` 板级配置完全一致：
> ES8311 + ILI9341 2.8" + I2C 触摸 + SD + N16R8）。
> 99 文档的引脚实为 Freenove 引脚但**功能标签张冠李戴**（46=LCD DC、45=背光、4=MCLK、5=BCLK…）。

## 当前引脚（config.h）

### ES8311 音频（I2S + I2C）

| 功能 | GPIO | 来源 |
|---|---|---|
| I2S MCLK | 4 | Freenove 官方（99 文档误标为 LCD RST） |
| I2S BCLK | 5 | Freenove 官方（99 文档误标为 LCD CS） |
| I2S WS (LRC) | 7 | Freenove 官方（99 文档误标为 I2S DIN） |
| I2S DIN（麦克风） | 6 | Freenove 官方（99 文档误标为 SD SCK） |
| I2S DOUT（扬声器） | 8 | Freenove 官方（99 文档误标为触摸 SDA） |
| PA 使能（低有效） | 1 | Freenove 官方 |
| I2C SDA（ES8311 控制） | 16 | Freenove 官方（v1 猜 11 → I2C 无 ACK 崩溃） |
| I2C SCL（ES8311 控制） | 15 | Freenove 官方（v1 猜 10 → I2C 无 ACK 崩溃） |

### ILI9341 显示（SPI，320x240 横屏）

| 功能 | GPIO | 来源 |
|---|---|---|
| CS 片选 | 10 | Freenove 官方 |
| DC 数据/命令 | 46 | Freenove 官方（99 文档误标为 I2S BCLK） |
| RST 复位 | NC | Freenove 板无独立复位脚 |
| SCK 时钟 | 12 | Freenove 官方 |
| MOSI 主出 | 11 | Freenove 官方 |
| MISO | 13 | Freenove 官方 |
| 背光 | 45 | Freenove 官方（99 文档误标为 I2S WS） |

### SD 卡（SDMMC 4-bit，背面卡槽）

| 功能 | GPIO | 来源 |
|---|---|---|
| CLK | 38 | Freenove 官方例程 Sketch_06.1_SDMMC_Test（2.8" 分支） |
| CMD | 40 | 同上 |
| D0 | 39 | 同上 |
| D1 | 41 | 同上 |
| D2 | 48 | 同上 |
| D3 | 47 | 同上 |

> 用途：`/sdcard/bg.gif` 大体积动画背景（≤4MB，FAT32）。
> 与显示/音频/BOOT 引脚零冲突。无卡时固件自动回退 Flash 内置背景。

## 防崩溃机制

`bigscreen-s3.cc` 启动时先探测 ES8311（I2C 地址 0x30）：

- **探测成功** → 正常走 `Es8311AudioCodec`（硬件 codec，硬件音量）。
- **探测失败** → 打印 `[WARN] ES8311 not detected ...`，降级为
  `NoAudioCodecDuplex`（纯 I2S 数字音频），设备照常运行、可配网联网，
  不再像 v1 那样 `ESP_ERROR_CHECK` abort 重启循环。

## 验证记录

- 2026-10-10：v1 引脚（I2C=10/11）烧录后启动即崩（本文档开头的 backtrace）。
- 2026-10-10：v2 引脚（Freenove 官方）编译通过（BUILD OK），待烧录实测。

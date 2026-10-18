# 屿禾小方块 1.54 寸 TFT（Wi-Fi）— `yh-154tft-wifi`

## 1. 版型简介

- 主控：ESP32-S3（Wi-Fi 版，无 4G 模组）
- 显示：ST7789，240 × 240，SPI3_HOST，16bpp RGB，颜色反转开启
- 音频：**没有专用 codec 芯片**，用 `NoAudioCodecSimplex` 软件 I2S 直驱
  （输入 16 kHz / 输出 24 kHz）
- 电源：单节锂电池，GPIO9 充电检测 + ADC1_CH7 电池电压采样 + 芯片温度传感器
- 特有功能：芯片高温（≥ 75 °C）屏幕弹窗警告、RTC GPIO2 电源保持、省电定时休眠/关机
- 迁移自 `<FW>/main/boards/yuhe/1.54tft-wifi/`（上游原型为征辰 ZHENGCHEN 1.54 寸 TFT Wi-Fi 版）

| 项 | 值 |
| --- | --- |
| set id | `yh-154tft-wifi` |
| 同步目标 | `<FW>/main/boards/yuhe/yh-154tft-wifi/` |
| Kconfig 符号 | `BOARD_TYPE_YUHE_SET_154TFT_WIFI` |
| Kconfig 显示名 | `Yuhe 1.54inch TFT WiFi (sets)` |
| OTA 板名 | `yh-154tft-wifi` |
| 字体 | `font_noto_sans_basic_20_4` / `font_material_symbols_20_4` |

## 2. 文件清单

| 文件 | 说明 |
| --- | --- |
| `set.json` | 版型元数据（`hardware/sets/build.py` 读它出菜单），**不同步到固件** |
| `config.json` | 构建配置（固件 `scripts/build.py` 读） |
| `config.h` | 引脚与显示参数宏 |
| `yh_set_154tft_wifi.cc` | 板实现，类名 `YhSet154TftWifiBoard`，末尾 `DECLARE_BOARD` |
| `yh_set_lcd_display.h` | `YhSetLcdDisplay`，继承 `SpiLcdDisplay` + 高温弹窗 |
| `power_manager.h` | `PowerManager`：电池 ADC、充电检测、芯片温度 |
| `README.md` | 本文件，**不同步到固件** |

## 3. 引脚总表

### 3.1 显示（ST7789 / SPI3_HOST）

| 功能 | 宏名 | GPIO |
| --- | --- | --- |
| SDA（MOSI） | `DISPLAY_SDA` | 41 |
| SCL（SCLK） | `DISPLAY_SCL` | 42 |
| RES（复位） | `DISPLAY_RES` | 45 |
| DC（数据/命令） | `DISPLAY_DC` | 40 |
| CS（片选） | `DISPLAY_CS` | 21 |
| 背光 PWM | `DISPLAY_BACKLIGHT_PIN` | 20 |

MISO 未使用（`GPIO_NUM_NC`），DMA 通道自动分配。

### 3.2 音频（单工 I2S，`NoAudioCodecSimplex`）

| 功能 | 宏名 | GPIO |
| --- | --- | --- |
| 麦克风 WS | `AUDIO_I2S_MIC_GPIO_WS` | 4 |
| 麦克风 SCK | `AUDIO_I2S_MIC_GPIO_SCK` | 5 |
| 麦克风 DIN | `AUDIO_I2S_MIC_GPIO_DIN` | 6 |
| 扬声器 DOUT | `AUDIO_I2S_SPK_GPIO_DOUT` | 7 |
| 扬声器 BCLK | `AUDIO_I2S_SPK_GPIO_BCLK` | 15 |
| 扬声器 LRCK | `AUDIO_I2S_SPK_GPIO_LRCK` | 16 |

### 3.3 按键

| 功能 | 宏名 | GPIO |
| --- | --- | --- |
| BOOT | `BOOT_BUTTON_GPIO` | 0 |
| 音量 + | `VOLUME_UP_BUTTON_GPIO` | 10 |
| 音量 − | `VOLUME_DOWN_BUTTON_GPIO` | 39 |

### 3.4 电源与 RTC

| 功能 | 宏名 | GPIO |
| --- | --- | --- |
| 充电状态检测（输入，高 = 充电中） | `POWER_CHARGE_DETECT_GPIO` | 9 |
| 电池电压 ADC | ADC_UNIT_1 / ADC_CHANNEL_7（**硬编码**） | 8 |
| 电源保持（RTC 输出，上电拉高） | `POWER_HOLD_RTC_GPIO` | 2 |

### 3.5 GPIO 占用汇总

```
 0  BOOT 按键            15  SPK BCLK          40  显示 DC
 2  RTC 电源保持(输出高)  16  SPK LRCK          41  显示 SDA(MOSI)
 4  MIC WS               20  背光 PWM          42  显示 SCL(SCLK)
 5  MIC SCK              21  显示 CS           45  显示 RES
 6  MIC DIN              39  音量- 按键
 7  SPK DOUT             
 8  电池 ADC(ADC1_CH7)   
 9  充电检测(输入)        
10  音量+ 按键           
```

26–32 为 flash/PSRAM 专用，不可复用。

## 4. 显示参数

| 参数 | 值 |
| --- | --- |
| 分辨率 | 240 × 240 |
| 交换 XY / 镜像 X / 镜像 Y | false / false / false |
| 偏移 X / Y | 0 / 0 |
| 色彩 | 16 bpp，`LCD_RGB_ELEMENT_ORDER_RGB` |
| 颜色反转 | 启用 |
| SPI 模式 | 3 |
| SPI 时钟 | **80 MHz**（硬编码在 `.cc`，不在 `config.h`） |
| 传输队列深度 | 10 |
| 命令/参数位宽 | 8 / 8 |
| 背光反转 | false |

## 5. 按键行为

| 按键 | 操作 | 行为 |
| --- | --- | --- |
| BOOT | 单击 | 唤醒省电定时器；启动态则进入配网，否则切换对话状态 |
| BOOT | 长按 | 唤醒 + 强制进入配网模式（重置 Wi-Fi 配置） |
| 音量 + | 单击 | 音量 +10（上限 100），屏幕提示当前音量 |
| 音量 + | 长按 | 音量置 100，提示「最大音量」 |
| 音量 − | 单击 | 音量 −10（下限 0），屏幕提示当前音量 |
| 音量 − | 长按 | 音量置 0，提示「已静音」 |

每次操作都会先 `power_save_timer_->WakeUp()` 重置省电计时。

## 6. 电源与电量

### 6.1 电池电量映射

- ADC：`ADC_UNIT_1` / `ADC_CHANNEL_7`，衰减 12 dB，位宽 12 bit
- 采样：保留最近 **3** 次（`kBatteryAdcDataCount = 3`），每个原始值 **+80** 后取平均
- 低电量阈值：**20 %**

| ADC 均值 | 电量 |
| --- | --- |
| 2030 | 0 % |
| 2134 | 20 % |
| 2252 | 40 % |
| 2370 | 60 % |
| 2488 | 80 % |
| 2606 | 100 % |

低于 2030 记 0 %，高于 2606 记 100 %，中间线性插值。
上报系统时做了保底：`level = max(GetBatteryLevel(), 20)`，**显示最低 20 %**。

### 6.2 充电检测

- GPIO9 输入，高电平 = 充电中，无上下拉
- 电量 = 100 % 时 `IsCharging()` 强制返回 `false`
- 充电开始 → 关闭省电定时器；充电停止 → 重新启用

### 6.3 芯片温度与高温弹窗

- 使用 `temperature_sensor` 新驱动，量程 **10 – 80 °C**，每 **10 秒**读一次
- 温度变化 **≥ 3.5 °C** 才触发回调（滞回，防抖）
- 屏幕弹窗阈值 **75 °C**：红色圆角弹窗，宽 = 屏宽 × 0.9，底部居中，文案「警告：温度过高」
- 未调用 `SetupHighTempWarningPopup()` 时会打警告日志并跳过

### 6.4 省电策略

```cpp
power_save_timer_ = new PowerSaveTimer(-1, 60, 300);
```

| 参数 | 值 | 含义 |
| --- | --- | --- |
| cpu_max_freq | −1 | 不限制 CPU 频率 |
| seconds_to_sleep | 60 | 60 秒无操作进入休眠 |
| seconds_to_shutdown | 300 | 300 秒无操作关机 |

进入休眠：屏幕进 power-save 模式 + 背光降到 1；退出休眠则恢复。
**放电时启用，充电时禁用**。RTC GPIO2 初始化时设为输出并拉高以维持电源。

## 7. 构建方式

统一走版型适配中心，不要手动改固件的 `Kconfig.projbuild` / `CMakeLists.txt`：

```bash
# 列出所有可用版型
python hardware/sets/build.py --list

# 交互式选择版型 → 自动同步 + 注册 + 编译
python hardware/sets/build.py
```

`build.py` 会把本目录（除 `set.json`、`README.md`）下的
`*.cc / *.h / *.json` 同步到 `<FW>/main/boards/yuhe/yh-154tft-wifi/`，
再自动完成 Kconfig / CMakeLists 注册并调用固件 `scripts/build.py`。
产物在固件的 `build/` 下。

**不要**手动 `idf.py set-target`，`build.py` 内部以 `-DIDF_TARGET=esp32s3` + `reconfigure` 完成。

## 8. 已知注意点（迁移时务必读）

1. **SPI 时钟 80 MHz 偏激进**。ST7789 常规规格约 40 MHz。花屏/闪屏时改
   `yh_set_154tft_wifi.cc` 中 `io_config.pclk_hz = 80 * 1000 * 1000` → `40 * 1000 * 1000`。
   此值**硬编码**，不在 `config.h`。
2. **电池 ADC 通道硬编码在 `power_manager.h`**（`ADC_UNIT_1` / `ADC_CHANNEL_7`，
   ESP32-S3 上对应 GPIO8），`config.h` 里没有对应宏。如果实际硬件接的不是 GPIO8，
   必须改 `power_manager.h` 而不是 `config.h`。
3. **电量显示保底 20 %**，实际低于 20 % 也显示 20 %。
4. **温度传感器量程 10 – 80 °C**，弹窗阈值 75 °C，余量很小；超过 80 °C 读数不再可信。
5. **ADC 均值 +80 偏移**是这块板的经验校准值，换电池或分压电阻需重新标定映射表。
6. 该板**无专用编解码芯片**，用 `NoAudioCodecSimplex` 直驱 I2S，
   输入 16 kHz / 输出 24 kHz 是软件 I2S 的配置。
7. `PowerManager` 类是 header-only 且**未改名**（仍叫 `PowerManager`），
   与其它版型同名不冲突，因为不在同一编译单元；它是 `yh_set_154tft_wifi.cc` 私有包含。
8. 本版型未内置 8 MB flash 变体；若实物是 8 MB flash，需要另加 `config.8m.json`
   并同时改 `CONFIG_ESPTOOLPY_FLASHSIZE_*` 与分区表，只改分区表会烧录失败。

## 9. 产品链接（上游附带）

```
https://e.tb.cn/h.6Gl2LC7rsrswQZp?tk=qFuaV9hzh0k CZ356
```

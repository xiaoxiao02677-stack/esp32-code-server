# 第一代小方块（ESP32-S3-N16R8 / ST7789）

版型 ID：`yh-n16r8-st7789`
同步目标：`<FW>/main/boards/yuhe/yh-n16r8-st7789`

## 版型简介

- 主控：ESP32-S3-N16R8（Flash 16MB / PSRAM 8MB），ESP-IDF 6.x，目标 `esp32s3`
- 显示：ST7789 240×240 SPI 屏（5 线 + PWM 背光）
- 音频：**无 codec**，I2S 单工直驱
  - 输出：MAX98357A 功放（GAIN 接地 = 默认增益，SD 接 3.3V 常开）
  - 输入：INMP441 麦克风（L/R 接地 = 左声道）
- 网络：Wi-Fi（`WifiBoard`）
- 按键：仅 BOOT

## 引脚总表

来源：硬件资料《第一代 esp32.md》「GPIO 占用总表」。

| GPIO | 设备 | 用途 | config.h 宏 |
| :--: | --- | --- | --- |
| 21 | ST7789 | SCL（SPI 时钟） | `DISPLAY_SCL` |
| 47 | ST7789 | SDA（SPI MOSI） | `DISPLAY_SDA` |
| 45 | ST7789 | RST | `DISPLAY_RES` |
| 40 | ST7789 | DC | `DISPLAY_DC` |
| 41 | ST7789 | CS | `DISPLAY_CS` |
| 42 | ST7789 | BL（PWM 背光） | `DISPLAY_BACKLIGHT_PIN` |
| 15 | MAX98357A | BCLK | `AUDIO_I2S_SPK_GPIO_BCLK` |
| 16 | MAX98357A | LRC（WS） | `AUDIO_I2S_SPK_GPIO_LRCK` |
| 7 | MAX98357A | DIN | `AUDIO_I2S_SPK_GPIO_DOUT` |
| 5 | INMP441 | SCK | `AUDIO_I2S_MIC_GPIO_SCK` |
| 4 | INMP441 | WS | `AUDIO_I2S_MIC_GPIO_WS` |
| 6 | INMP441 | SD | `AUDIO_I2S_MIC_GPIO_DIN` |
| 0 | BOOT 键 | 单击对话 / 长按配网 | `BOOT_BUTTON_GPIO` |

未接线 / 未实现的外设：状态灯（无引脚资料）、音量键（无引脚资料）、电池 ADC 与充电检测（无引脚资料）、SSD1306 备用屏（有引脚但本版型不实现）。

采样率：输入 16000 Hz，输出 24000 Hz（与模板板一致）。

## 与模板板 `yuhe/1.54tft-wifi` 的差异对照

模板：`<FW>/main/boards/yuhe/1.54tft-wifi/`，硬件架构相同（ST7789 SPI + `NoAudioCodecSimplex` 单工 I2S）。

### 引脚差异（音频完全一致，只有 LCD 不同）

| 宏 | 模板板 `1.54tft-wifi` | 本板 `yh-n16r8-st7789` |
| --- | --- | --- |
| `DISPLAY_SDA`（MOSI） | 41 | **47** |
| `DISPLAY_SCL` | 42 | **21** |
| `DISPLAY_RES` | 45 | 45（相同） |
| `DISPLAY_DC` | 40 | 40（相同） |
| `DISPLAY_CS` | 21 | **41** |
| `DISPLAY_BACKLIGHT_PIN` | 20 | **42** |
| `AUDIO_I2S_*`（6 个） | 4/5/6/7/15/16 | 4/5/6/7/15/16（**完全相同**） |
| `BOOT_BUTTON_GPIO` | 0 | 0（相同） |

> 注意：CS 与 BL 相对模板是 41/42 互换，MOSI 41→47、SCL 42→21，改动时逐项对齐，不要按模板顺序顺延。

### 功能差异（相对模板删除的部分）

| 项 | 模板板 | 本板 | 原因 |
| --- | --- | --- | --- |
| `power_manager.h`（电池 ADC + 充电检测 + 芯片温度） | 有 | **无** | 资料未给电池/充电引脚，直接继承 `Board` 默认（`GetBatteryLevel()` / `GetTemperature()` 返回 false） |
| `yuhe_lcd_display.h`（高温弹窗） | 有 | **无** | 无温度传感器需求，改用标准 `SpiLcdDisplay` |
| `VOLUME_UP_BUTTON_GPIO` / `VOLUME_DOWN_BUTTON_GPIO` | 10 / 39 | **无** | 资料未给按键引脚，音量键未接 |
| `rtc_gpio_init(GPIO_NUM_2)` 电源保持 | 有 | **无** | 资料 GPIO 总表无 GPIO2，不擅自驱动未声明引脚 |
| `InitializeTools()` | 有（空函数） | **无** | 无工具初始化需求 |
| LED / `GetLed()` | 只有 `#include "led/single_led.h"`，未实例化，走基类 `NoLed` | **连 include 一起删掉，同样走基类 `NoLed`** | 资料未给 LED 引脚，不为硬件做决定；与模板保持「除屏幕引脚外零差异」 |

保留：SPI 总线初始化（SPI3_HOST）、ST7789 面板初始化（spi_mode 3 / 80MHz / RGB565 / 反色）、BOOT 单击与长按逻辑、`PowerSaveTimer`（-1 / 60s 息屏 / 300s）、`PwmBacklight` 背光、`SetPowerSaveLevel()` 覆盖。

> `main/CMakeLists.txt` 用 `file(GLOB boards/${BOARD_DIR}/*.cc *.c)` 只收当前选中板目录的源码（约 922 行），
> 因此上面这些删除只影响本版型，不会牵连 `1.54tft-wifi` 等其它版型。

## 构建方式

通过版型适配中心（推荐）：

```bash
python hardware/sets/build.py
# 菜单里选「第一代小方块（ESP32-S3-N16R8 / ST7789）」
```

`build.py` 会自动：同步本目录 `*.cc/*.h/*.json`（`set.json`、`README.md` 除外）到
`<FW>/main/boards/yuhe/yh-n16r8-st7789/`，注册 Kconfig / CMakeLists，然后调用固件 `scripts/build.py`。

等价的 menuconfig 选项：

```
Xiaozhi Assistant -> Board Type -> Yuhe N16R8 ST7789 (sets)
```

字体（抄自模板板 `CONFIG_BOARD_TYPE_YUHE_1_54TFT_WIFI`）：
`font_noto_sans_basic_20_4` / `font_material_symbols_20_4`，emoji 集合 `noto-color-emoji_64`。

编译产物板名：`yh-n16r8-st7789`。

## 已知缺口

1. **按键**：硬件资料未给任何按键 GPIO。BOOT 采用 ESP32-S3 标准 BOOT 引脚 GPIO0；**音量键未接**，因此没有音量加减与静音功能（需用 App 或语音调节）。若实物 BOOT 不在 GPIO0，改 `config.h` 的 `BOOT_BUTTON_GPIO` 即可。
2. **LED**：资料未给状态灯引脚，**未实现**，走基类 `Board::GetLed()` 返回的 `static NoLed`（`main/boards/common/board.cc:167`，安全空实现，UI 只少灯效不会崩）。GPIO48 虽是 ESP32-S3 开发板板载 WS2812 的常见位置，但「常见」不等于「这块板就是」，故不替硬件做决定。启用方法见下节。
3. **电池 / 充电检测**：资料未给 ADC 与充电检测引脚，`GetBatteryLevel()` 返回 false，UI 不显示电量。
4. **芯片温度**：无 `PowerManager`，`GetTemperature()` 返回 false，无高温弹窗。
5. **备用屏 SSD1306（I2C SCL=9 / SDA=8）**：资料标注为可选备用屏，**本版型未实现**。当前固定使用 ST7789 主屏，未做开机 I2C 0x3C 探测与自动切换。
6. **电源保持 GPIO**：模板用 `rtc_gpio` 拉高一个引脚做休眠保持，本板资料未声明该引脚，已移除；因此息屏后不做深度休眠掉电（仅息屏 + 背光降到 1）。

## 已移除 / 未接线外设：如何启用 LED

若实物板载 LED 且确认接在 **GPIO48**（ESP32-S3 开发板常见位置），在 `yh_set_n16r8_st7789.cc` 中加入

```cpp
#include "led/single_led.h"

// 类内 public 区，与 GetBacklight() 并列
virtual Led* GetLed() override {
    static SingleLed led(GPIO_NUM_48);
    return &led;
}
```

注意：`SingleLed` 使用 `led_strip`（RMT 后端）驱动，会在该脚持续输出 WS2812 时序波形，占用一路 RMT 通道；普通 LED 也能点亮但色彩不可控。若确认灯在别的脚，把 `GPIO_NUM_48` 换成实际引脚（或在 `config.h` 里定义 `BUILTIN_LED_GPIO` 再引用）。

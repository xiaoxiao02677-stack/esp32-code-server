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
| 0 | BOOT 键 | 短按对话 / 双击表情彩蛋 / 长按静音·配网 | `BOOT_BUTTON_GPIO` |

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

保留：SPI 总线初始化（SPI3_HOST）、ST7789 面板初始化（spi_mode 3 / 80MHz / RGB565 / 反色）、`PowerSaveTimer`（-1 / 60s 息屏 / 300s）、`PwmBacklight` 背光、`SetPowerSaveLevel()` 覆盖。
BOOT 键与显示皮肤已升级为圆屏版（见下节）。

## 圆屏皮肤（共享层 YhSkinDisplay）

> 2026-10-17 起皮肤**不再放在本目录**：已提升为四个 `yh-*` 版型共用的
> `main/display/yh_skin/`（`YhSkinDisplay` + `YhSkinProfile::Round240(false)`）。
> 视觉基准仍是 A 板 `my-s3-tft` 的 `round_screen_display.*`，布局逐项对齐。
> 本目录原来的 `round_screen_display.h/.cc` 与 `good_bg.c` 已归档到
> `.trash/2026-10-17-yh-skin/`，背景图合并为共享符号 `yh_skin_bg`（只存一份像素）。

| 位置 | 作用 |
| --- | --- |
| `main/display/yh_skin/yh_skin_display.cc` | 圆屏布局 / 协议钩子 / 按键反馈 / 1 秒节拍（四版型共用） |
| `main/display/yh_skin/yh_skin_boot.cc` | 开机首帧品牌画面（呼吸点 + 版本号） |
| `main/display/yh_skin/yh_skin_cards.cc` | 配网 / 激活码 / 升级 / 错误 四类卡片 |
| `main/display/yh_skin/yh_skin_assets.c` | 240×240 RGB565 背景图（`yh_skin_bg`，脚本生成） |
| 本目录 `yh_set_n16r8_st7789.cc` | 只负责硬件初始化 + `YhSkinProfile::Round240(false)` 传参 + 按键/节拍接线 |

规格与踩坑详见 [`../../UI_SKIN.md`](../../UI_SKIN.md)。

布局：顶部 y=10 时间、y=28 电量（无电池时隐藏）、中心 y=-15 表情、底部 y=-55 气泡（200×50 / 文字宽 180 / 圆角 16 / 粉边框）、y=-18 操作提示；背景为 `good.jpg` 全屏图 + 深紫渐变兜底。

BOOT 键三事件（与 A 板逐项对齐）：

- 短按：待机/说话 → `ToggleChatState()`，皮肤反馈「我在听...」+ laughing
- 双击：待机 → 表情彩蛋轮播（loving/embarrassed/cool/silly/surprised，10 秒后回 neutral）
- 长按 1s：`Starting` 且开机 30s 内 → 进配网；聆听/说话 → 取消/打断；待机 → 静音切换

1 秒节拍（`esp_timer` 周期 1s）：彩蛋超时恢复、23:30 睡觉提醒、07:00 早晨问好（仅待机 + 时间已同步）。

相对 A 板只改了 5 处缺陷修复 + 1 处无电池适配（Q6 裁定）：

| 编号 | 修复 |
| --- | --- |
| D1/D2 | 气泡文本按 **UTF-8 码点**截断到 72 码点（原按 96 字节硬切，会切半个汉字）；超长补 `…` |
| D3 | 电量文本去掉 `⚡` 前缀，改纯数字 `NN%`（中文字库无该字形，会显示豆腐块） |
| D4 | `ClearChatMessages()` 不再把 `chat_message_label_` 置空，改为隐藏占位（防 `SetTheme` 解引用崩溃） |
| D5 | 底部提示 y=-12 → **y=-18**，避开 240×240 圆边裁切 |
| G3 | 本板无电池检测，电量标签初始隐藏，`UpdateStatusBar` 在 `GetBatteryLevel()` 返回 false 时保持隐藏（不显示 `0%`） |


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

1. **按键**：硬件资料未给任何按键 GPIO。BOOT 采用 ESP32-S3 标准 BOOT 引脚 GPIO0；**音量键未接**，因此没有音量加减（待机长按 BOOT 可做 0/70 静音切换，或由 App/语音调节音量）。若实物 BOOT 不在 GPIO0，改 `config.h` 的 `BOOT_BUTTON_GPIO` 即可。
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

#ifndef _BOARD_CONFIG_H_
#define _BOARD_CONFIG_H_

#include <driver/gpio.h>

/*
 * 自定义板卡: ESP32-S3-N16R8 + ST7789 240x240 SPI LCD + MAX98357A I2S 功放
 *
 * 硬件连接:
 *   LCD(主屏):  SCL=21 SDA=47 RST=45 DC=40 CS=41 BL=42
 *   备用屏(I2C): SCL=9 SDA=8 VCC=3V3 GND=GND (SSD1306 0.96" 128x64, 地址0x3C)
 *   功放:  LRC=16 BCLK=15 DIN=7, VIN=3.3V (GAIN=GND -> 12dB@3.3V, SD=3.3V 使能)
 *
 * INMP441 麦克风 (I2S 输入): SCK=5 WS=4 SD=6, VDD=3.3V, L/R=GND(左声道).
 *
 * 与 99 固件信息.md 的引脚表一致; NoAudioCodecSimplex 会建立真实的 I2S RX
 * 通道(见 audio/codecs/no_audio_codec.cc), 因此只要硬件按上表接好,
 * 固件即可直接收音, 无需改代码.
 *
 * 屏幕兼容性: 开机先在 SCL=9/SDA=8 上探测 I2C 备用屏 (0x3C), 探测到则
 * 使用备用屏方案; 探测不到(原 SPI 屏接法)则走主屏方案. 两套引脚互相独立:
 *   - 主屏 ST7789: SPI CLK=21 MOSI=47(+RST/DC/CS/BL)
 *   - 备用 SSD1306: I2C SCL=9 SDA=8(仅 VCC/GND 供电)
 */

#define AUDIO_INPUT_SAMPLE_RATE  16000
#define AUDIO_OUTPUT_SAMPLE_RATE 24000

// 功放 GAIN 接 GND: 3.3V 供电下实际增益 12dB (5V 时为 15dB)。
// 增益与最大输出功率较低, 软件默认音量保守取 50 防破音, 可由 MCP 调高
// (系统默认 70, 走 MCP "设置音量" 或 menuconfig 可调)
#define AUDIO_I2S_METHOD_SIMPLEX

#ifdef AUDIO_I2S_METHOD_SIMPLEX

// 麦克风 INMP441 (I2S 输入, 已按 99 固件信息.md 接线)
#define AUDIO_I2S_MIC_GPIO_WS GPIO_NUM_4
#define AUDIO_I2S_MIC_GPIO_SCK GPIO_NUM_5
#define AUDIO_I2S_MIC_GPIO_DIN GPIO_NUM_6

// 喇叭 (MAX98357A)
#define AUDIO_I2S_SPK_GPIO_DOUT GPIO_NUM_7
#define AUDIO_I2S_SPK_GPIO_BCLK GPIO_NUM_15
#define AUDIO_I2S_SPK_GPIO_LRCK GPIO_NUM_16

#else

#define AUDIO_I2S_GPIO_WS GPIO_NUM_4
#define AUDIO_I2S_GPIO_BCLK GPIO_NUM_15
#define AUDIO_I2S_GPIO_DIN  GPIO_NUM_6
#define AUDIO_I2S_GPIO_DOUT GPIO_NUM_7

#endif

#define BOOT_BUTTON_GPIO        GPIO_NUM_0
#define BUILTIN_LED_GPIO        GPIO_NUM_NC

// YH Device Protocol: WS2812 RGB LED（DevKitC-1 板载；若你的板子未焊或接其他脚, 改这里）
#ifdef CONFIG_YH_PROTOCOL_ENABLED
#ifndef YH_WS2812_GPIO
#define YH_WS2812_GPIO          GPIO_NUM_48
#endif
#endif

// ST7789 240x240 SPI LCD (主屏)
#define DISPLAY_MOSI_PIN      GPIO_NUM_47
#define DISPLAY_CLK_PIN       GPIO_NUM_21
#define DISPLAY_DC_PIN        GPIO_NUM_40
#define DISPLAY_RST_PIN       GPIO_NUM_45
#define DISPLAY_CS_PIN        GPIO_NUM_41
#define DISPLAY_BACKLIGHT_PIN GPIO_NUM_42

// 备用屏: SSD1306 128x64 I2C OLED (独立引脚, 与主屏互不影响)
// 开机先探测 0x3C, 探测到即用备用屏, 否则回退主屏 ST7789
//
// 控制器选择: 0.96" OLED 多为 SSD1306(默认); 1.3" OLED 及部分 0.96" 为
// SH1106 —— 若备用屏花屏/竖向错位, 取消下行注释切换为 SH1106 驱动
#define DISPLAY_FB_SSD1306_USE_SH1106
#define DISPLAY_FB_SSD1306_MIRROR_X true   // OLED 模块默认接线需双向镜像(参照仓库其他 OLED 板)
#define DISPLAY_FB_SSD1306_MIRROR_Y true
#define DISPLAY_FALLBACK_SSD1306
#define DISPLAY_FB_SSD1306_SCL_PIN GPIO_NUM_9
#define DISPLAY_FB_SSD1306_SDA_PIN GPIO_NUM_8
#define DISPLAY_FB_SSD1306_ADDR    0x3C
#define DISPLAY_FB_SSD1306_WIDTH   128
#define DISPLAY_FB_SSD1306_HEIGHT  64

#define DISPLAY_WIDTH   240
#define DISPLAY_HEIGHT  240
#define DISPLAY_MIRROR_X false
#define DISPLAY_MIRROR_Y false
#define DISPLAY_SWAP_XY false
#define DISPLAY_INVERT_COLOR    true
#define DISPLAY_RGB_ORDER  LCD_RGB_ELEMENT_ORDER_RGB
#define DISPLAY_OFFSET_X  0
#define DISPLAY_OFFSET_Y  0
#define DISPLAY_BACKLIGHT_OUTPUT_INVERT false
#define DISPLAY_SPI_MODE 0

#endif // _BOARD_CONFIG_H_

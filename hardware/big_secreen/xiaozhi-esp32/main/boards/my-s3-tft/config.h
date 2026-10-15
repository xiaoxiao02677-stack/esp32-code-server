#ifndef _BOARD_CONFIG_H_
#define _BOARD_CONFIG_H_

#include <driver/gpio.h>

/*
 * 自定义板卡: ESP32-S3-N16R8 + ST7789 240x240 SPI LCD + MAX98357A I2S 功放
 *
 * 硬件连接:
 *   LCD:  SCL=21 SDA=47 RST=45 DC=40 CS=41 BL=42
 *   功放:  LRC=16 BCLK=15 DIN=7, VIN=3.3V (GAIN=GND -> 12dB@3.3V, SD=3.3V 使能)
 *
 * INMP441 麦克风 (I2S 输入): SCK=5 WS=4 SD=6, VDD=3.3V, L/R=GND(左声道).
 *
 * 与 99 固件信息.md 的引脚表一致; NoAudioCodecSimplex 会建立真实的 I2S RX
 * 通道(见 audio/codecs/no_audio_codec.cc), 因此只要硬件按上表接好,
 * 固件即可直接收音, 无需改代码.
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

// ST7789 240x240 SPI LCD
#define DISPLAY_MOSI_PIN      GPIO_NUM_47
#define DISPLAY_CLK_PIN       GPIO_NUM_21
#define DISPLAY_DC_PIN        GPIO_NUM_40
#define DISPLAY_RST_PIN       GPIO_NUM_45
#define DISPLAY_CS_PIN        GPIO_NUM_41
#define DISPLAY_BACKLIGHT_PIN GPIO_NUM_42

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

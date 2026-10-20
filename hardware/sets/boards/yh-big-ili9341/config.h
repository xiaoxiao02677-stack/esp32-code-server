#ifndef _BOARD_CONFIG_H_
#define _BOARD_CONFIG_H_

/* ============================================================================
 * yh-big-ili9341：Freenove ESP32-S3 Display 2.8"（或同布线套板）
 *
 * 引脚权威来源：hardware/big_secreen/yuhe-esp32/main/boards/bigscreen-s3/
 * （原厂固件，实机验证可正常出声音/画面/配网）。该板即 Freenove
 * ESP32-S3 Display 2.8"，引脚按 Freenove 官方原理图修正，不再使用
 * 《第二代 大屏幕固件信息.md》的字符串推断值——那份文档把 Freenove
 * 引脚的功能标签张冠李戴了（46 是 LCD DC、45 是背光、4 是 MCLK…）。
 * ========================================================================== */

#include <driver/gpio.h>

/* ---------------------------------------------------------------------------
 * 音频采样率
 * ------------------------------------------------------------------------- */
#define AUDIO_INPUT_SAMPLE_RATE  24000
#define AUDIO_OUTPUT_SAMPLE_RATE 24000

/* ---------------------------------------------------------------------------
 * ES8311 音频：I2S 部分（Freenove 官方布线）
 * ------------------------------------------------------------------------- */
#define AUDIO_I2S_GPIO_MCLK  GPIO_NUM_4
#define AUDIO_I2S_GPIO_BCLK  GPIO_NUM_5
#define AUDIO_I2S_GPIO_WS    GPIO_NUM_7
#define AUDIO_I2S_GPIO_DOUT  GPIO_NUM_8
#define AUDIO_I2S_GPIO_DIN   GPIO_NUM_6

/* ---------------------------------------------------------------------------
 * ES8311 音频：I2C 控制部分（Freenove 官方布线）
 * ------------------------------------------------------------------------- */
#define AUDIO_CODEC_I2C_NUM       I2C_NUM_0
#define AUDIO_CODEC_I2C_SCL_PIN   GPIO_NUM_15
#define AUDIO_CODEC_I2C_SDA_PIN   GPIO_NUM_16
#define AUDIO_CODEC_ES8311_ADDR   ES8311_CODEC_DEFAULT_ADDR

/* 功放使能（Freenove 官方布线，低电平使能）*/
#define AUDIO_CODEC_PA_PIN        GPIO_NUM_1
#define AUDIO_CODEC_PA_INVERTED   true

/* ---------------------------------------------------------------------------
 * 按键与指示灯
 * ------------------------------------------------------------------------- */
#define BOOT_BUTTON_GPIO    GPIO_NUM_0
#define BUILTIN_LED_GPIO    GPIO_NUM_48  // Freenove 板载 LED（与 SD D2 共用，仅指示用）

/* ---------------------------------------------------------------------------
 * ILI9341 2.8 寸 SPI 屏（Freenove 官方布线）
 * ------------------------------------------------------------------------- */
#define DISPLAY_BACKLIGHT_PIN GPIO_NUM_45
#define DISPLAY_BACKLIGHT_OUTPUT_INVERT false

#define DISPLAY_RST_PIN       GPIO_NUM_NC   // Freenove 板 LCD 无独立复位脚
#define DISPLAY_CS_PIN        GPIO_NUM_10
#define DISPLAY_DC_PIN        GPIO_NUM_46
#define DISPLAY_SCK_PIN       GPIO_NUM_12
#define DISPLAY_MOSI_PIN      GPIO_NUM_11
#define DISPLAY_MISO_PIN      GPIO_NUM_13
#define DISPLAY_SPI_SCLK_HZ   (20 * 1000 * 1000)
#define DISPLAY_SPI_MODE      0

#define LCD_SPI_HOST          SPI3_HOST

/* 面板参数：ILI9341 2.8 寸典型 320x240 */
#define LCD_TYPE_ILI9341_SERIAL
#define DISPLAY_WIDTH         320
#define DISPLAY_HEIGHT        240
#define DISPLAY_MIRROR_X      false
#define DISPLAY_MIRROR_Y      false
#define DISPLAY_SWAP_XY       true
#define DISPLAY_INVERT_COLOR  true
#define DISPLAY_RGB_ORDER     LCD_RGB_ELEMENT_ORDER_BGR
#define DISPLAY_OFFSET_X      0
#define DISPLAY_OFFSET_Y      0

#endif  // _BOARD_CONFIG_H_

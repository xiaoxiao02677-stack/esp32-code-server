#ifndef _BOARD_CONFIG_H_
#define _BOARD_CONFIG_H_

#include <driver/gpio.h>

// ============================================================
// bigscreen-s3：ESP32-S3 + ES8311 + ILI9341 2.8" SPI 屏
// 依据《99 大屏幕固件信息.md》适配。
//
// ⚠️ 引脚消解策略（99 文档引脚自相冲突，无法直接使用）：
//   - 音频 I2S 四脚（46/45/7/2）来自固件 I2S 外设探测，可信度高 → 原样采用
//   - 显示控制脚 CS=5 / DC=6 / RST=4 与音频无冲突 → 原样采用
//   - 显示数据脚（99 原文 MOSI=7 与音频 DIN 冲突、SCK=6 与 DC 冲突）
//     → 重新分配到干净区：SCK=12 / MOSI=13
//   - 详见 PINOUT.md（含全部引脚表与实测修改指引）
// 若烧录后音频/显示不工作，优先核对本文件宏与 PINOUT.md。
// ============================================================

#define AUDIO_INPUT_SAMPLE_RATE  24000
#define AUDIO_OUTPUT_SAMPLE_RATE 24000

// ---------- 音频 I2S（ES8311，99 文档探测值）----------
#define AUDIO_I2S_GPIO_MCLK      GPIO_NUM_2   // MCLK（99: GPIO2）
#define AUDIO_I2S_GPIO_BCLK      GPIO_NUM_46  // SCK（99: GPIO46）
#define AUDIO_I2S_GPIO_DIN       GPIO_NUM_7   // DIN 麦克风（99: GPIO7）
#define AUDIO_I2S_GPIO_WS        GPIO_NUM_45  // LRC（99: GPIO45）
#define AUDIO_I2S_GPIO_DOUT      GPIO_NUM_8   // DOUT 扬声器（99 未给出，取 DIN 相邻脚）
#define AUDIO_CODEC_PA_PIN       GPIO_NUM_1   // PA 使能（99 未给出，取常用脚）

// ---------- 音频 I2C（ES8311 控制通道，99 未给出）----------
#define AUDIO_CODEC_I2C_NUM      I2C_NUM_0
#define AUDIO_CODEC_I2C_SCL_PIN  GPIO_NUM_10
#define AUDIO_CODEC_I2C_SDA_PIN  GPIO_NUM_11
#define AUDIO_CODEC_ES8311_ADDR  ES8311_CODEC_DEFAULT_ADDR

// ---------- BOOT 按键 ----------
#define BOOT_BUTTON_GPIO GPIO_NUM_0

// ---------- 显示（ILI9341 2.8" 320x240 横屏）----------
#define DISPLAY_BACKLIGHT_PIN GPIO_NUM_47  // 背光（99 未给出，取常用脚）
#define DISPLAY_BACKLIGHT_OUTPUT_INVERT false

#define DISPLAY_RST_PIN       GPIO_NUM_4   // 复位（99: RST=GPIO4）
#define DISPLAY_CS_PIN        GPIO_NUM_5   // 片选（99: CS=GPIO5）
#define DISPLAY_DC_PIN        GPIO_NUM_6   // 数据/命令（99: DC=GPIO6）
#define DISPLAY_SCK_PIN       GPIO_NUM_12  // SPI 时钟（消解值；99 原文 SCK=6 与 DC 冲突）
#define DISPLAY_MOSI_PIN      GPIO_NUM_13  // SPI 主出（消解值；99 原文 MOSI=7 与音频 DIN 冲突）
#define DISPLAY_MISO_PIN      GPIO_NUM_NC  // 2.8 寸屏只写不读，悬空
#define DISPLAY_SPI_SCLK_HZ   (40 * 1000 * 1000)

#define LCD_SPI_HOST          SPI3_HOST

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
#define DISPLAY_SPI_MODE      0

#endif  // _BOARD_CONFIG_H_

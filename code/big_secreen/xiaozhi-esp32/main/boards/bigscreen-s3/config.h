#ifndef _BOARD_CONFIG_H_
#define _BOARD_CONFIG_H_

#include <driver/gpio.h>

// ============================================================
// bigscreen-s3：ESP32-S3 + ES8311 + ILI9341 2.8" SPI 屏
// 板卡鉴定：Freenove ESP32-S3 Display 2.8"（或同布线套板）。
// 引脚已按该板官方原理图（仓库 freenove-esp32s3-display-2.8-lcd 板）修正，
// 不再使用《99 大屏幕固件信息.md》的字符串推断值——那份文档把 Freenove
// 引脚的功能标签张冠李戴了（46 是 LCD DC、45 是背光、4 是 MCLK、5 是 BCLK…）。
// 若音频/显示仍有异常，对照 main/boards/freenove-esp32s3-display-2.8-lcd/config.h。
// ============================================================

#define AUDIO_INPUT_SAMPLE_RATE  24000
#define AUDIO_OUTPUT_SAMPLE_RATE 24000

// ---------- 音频 I2S（Freenove 官方布线）----------
#define AUDIO_I2S_GPIO_MCLK      GPIO_NUM_4
#define AUDIO_I2S_GPIO_BCLK      GPIO_NUM_5
#define AUDIO_I2S_GPIO_WS        GPIO_NUM_7
#define AUDIO_I2S_GPIO_DOUT      GPIO_NUM_8
#define AUDIO_I2S_GPIO_DIN       GPIO_NUM_6

// ---------- 音频 I2C（ES8311 控制通道，Freenove 官方布线）----------
#define AUDIO_CODEC_I2C_NUM      I2C_NUM_0
#define AUDIO_CODEC_I2C_SCL_PIN  GPIO_NUM_15
#define AUDIO_CODEC_I2C_SDA_PIN  GPIO_NUM_16
#define AUDIO_CODEC_ES8311_ADDR  ES8311_CODEC_DEFAULT_ADDR

// ---------- 功放使能（Freenove 官方布线，低电平使能）----------
#define AUDIO_CODEC_PA_PIN       GPIO_NUM_1

// ---------- BOOT 按键 ----------
#define BOOT_BUTTON_GPIO GPIO_NUM_0

// ---------- SD 卡（SDMMC 4-bit，Freenove 官方布线，背面卡槽）----------
// 引脚来自 Freenove 官方例程 Sketch_06.1_SDMMC_Test（FNK0104A/B 2.8" 分支，
// 官方注释 "Please do not modify it"）。与 LCD（10/11/12/13/46/45）、
// 音频（1/4/5/6/7/8/15/16）、BOOT（0）零冲突。
// 用途：/sdcard/bg.gif 大体积动画背景（SD 缺失时回退 Flash 内置版）。
#define SD_CARD_MOUNT_POINT "/sdcard"
#define SD_MMC_GPIO_CLK GPIO_NUM_38
#define SD_MMC_GPIO_CMD GPIO_NUM_40
#define SD_MMC_GPIO_D0  GPIO_NUM_39
#define SD_MMC_GPIO_D1  GPIO_NUM_41
#define SD_MMC_GPIO_D2  GPIO_NUM_48
#define SD_MMC_GPIO_D3  GPIO_NUM_47

// ---------- 显示（ILI9341 2.8" 320x240 横屏，Freenove 官方布线）----------
#define DISPLAY_BACKLIGHT_PIN GPIO_NUM_45
#define DISPLAY_BACKLIGHT_OUTPUT_INVERT false

#define DISPLAY_RST_PIN       GPIO_NUM_NC   // Freenove 板 LCD 无独立复位脚（与触摸共享复位/上电默认复位）
#define DISPLAY_CS_PIN        GPIO_NUM_10
#define DISPLAY_DC_PIN        GPIO_NUM_46
#define DISPLAY_SCK_PIN       GPIO_NUM_12
#define DISPLAY_MOSI_PIN      GPIO_NUM_11
#define DISPLAY_MISO_PIN      GPIO_NUM_13
#define DISPLAY_SPI_SCLK_HZ   (20 * 1000 * 1000)
#define DISPLAY_SPI_MODE      0

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

#endif  // _BOARD_CONFIG_H_

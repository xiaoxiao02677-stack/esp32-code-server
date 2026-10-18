
#ifndef _BOARD_CONFIG_H_
#define _BOARD_CONFIG_H_

#include <driver/gpio.h>

/* 音频：单工 I2S 直驱（NoAudioCodecSimplex），无专用 codec 芯片 */
#define AUDIO_INPUT_SAMPLE_RATE  16000
#define AUDIO_OUTPUT_SAMPLE_RATE 24000
#define AUDIO_I2S_MIC_GPIO_WS   GPIO_NUM_4
#define AUDIO_I2S_MIC_GPIO_SCK  GPIO_NUM_5
#define AUDIO_I2S_MIC_GPIO_DIN  GPIO_NUM_6
#define AUDIO_I2S_SPK_GPIO_DOUT GPIO_NUM_7
#define AUDIO_I2S_SPK_GPIO_BCLK GPIO_NUM_15
#define AUDIO_I2S_SPK_GPIO_LRCK GPIO_NUM_16

/* 按键 */
#define BOOT_BUTTON_GPIO        GPIO_NUM_0
#define VOLUME_UP_BUTTON_GPIO   GPIO_NUM_10
#define VOLUME_DOWN_BUTTON_GPIO GPIO_NUM_39

/* 显示：ST7789 240x240，SPI3_HOST */
#define DISPLAY_SDA GPIO_NUM_41
#define DISPLAY_SCL GPIO_NUM_42
#define DISPLAY_RES GPIO_NUM_45
#define DISPLAY_DC GPIO_NUM_40
#define DISPLAY_CS GPIO_NUM_21

#define DISPLAY_WIDTH   240
#define DISPLAY_HEIGHT  240
#define DISPLAY_SWAP_XY  false
#define DISPLAY_MIRROR_X false
#define DISPLAY_MIRROR_Y false
#define BACKLIGHT_INVERT false
#define DISPLAY_OFFSET_X  0
#define DISPLAY_OFFSET_Y  0

#define DISPLAY_BACKLIGHT_PIN GPIO_NUM_20
#define DISPLAY_BACKLIGHT_OUTPUT_INVERT false

/* 电源与 RTC
 * 注意：以下两个引脚在原实现里是硬编码在 .cc / power_manager.h 中，
 * 没有在 config.h 里定义宏。这里补充宏仅为文档对照，修改时务必同步：
 *   - GPIO_NUM_9：充电状态检测（PowerManager 构造参数，见 yh_set_154tft_wifi.cc）
 *   - GPIO_NUM_2：RTC 电源保持（InitializePowerSaveTimer，见 yh_set_154tft_wifi.cc）
 *   - ADC_UNIT_1 / ADC_CHANNEL_7（= GPIO8）：电池电压采样，硬编码在 power_manager.h
 */
#define POWER_CHARGE_DETECT_GPIO GPIO_NUM_9
#define POWER_HOLD_RTC_GPIO      GPIO_NUM_2

#endif // _BOARD_CONFIG_H_

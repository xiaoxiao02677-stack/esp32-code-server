#ifndef _BOARD_CONFIG_H_
#define _BOARD_CONFIG_H_

/* ============================================================================
 *
 *   !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
 *   !!                        【 引 脚 未 核 实 】                        !!
 *   !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
 *
 *   本文件的 GPIO 分配**大部分是推测值**，未经实物/原理图核实。
 *
 *   来源资料《第二代 大屏幕固件信息.md》自己明确写了：
 *     "精确 GPIO 引脚可信度较低，因为固件无调试符号，且多处引脚存在冲突"
 *
 *   资料原文给出的引脚组（互相冲突，无法直接使用）：
 *     ES8311 I2S : BCLK=46, WS=45, DIN=7, MCLK=2
 *     ILI9341 SPI: CS=5, DC=6, RST=4, MOSI=7, SCK=6, MISO=1
 *     触摸 I2C   : SDA=1/8, SCL=2/9（需确认）
 *     SD 卡 SPI  : CS=4, MOSI=7, MISO=1, SCK=6
 *
 *   已知硬冲突：
 *     1) GPIO7 同时是 I2S-DIN 与 LCD-MOSI
 *     2) GPIO6 同时是 LCD-DC  与 LCD-SCK（DC 与 SCK 绝不可能同脚）
 *     3) GPIO1 同时是 LCD-MISO 与 触摸 I2C SDA（候选）
 *     4) GPIO4 同时是 LCD-RST  与 SD-CS（本版型不实现 SD，故不冲突）
 *
 *   处理策略（详见 README.md 的引脚对照表）：
 *     - I2S 音频引脚优先，完全沿用资料值（MCLK/BCLK/WS/DIN）
 *     - LCD 保留资料中不冲突的 CS/DC/RST，把冲突的 MOSI、SCK 挪到空闲 GPIO
 *     - 所有自行补充/修改的引脚在本文件内以 "【推测】" 标记
 *
 *   >>> 烧录前必须对照原理图逐条核实；核实后请把 set.json 的 pins_verified 改为 true <<<
 *
 * ========================================================================== */

#include <driver/gpio.h>

/* ---------------------------------------------------------------------------
 * 音频采样率
 * ------------------------------------------------------------------------- */
#define AUDIO_INPUT_SAMPLE_RATE  24000
#define AUDIO_OUTPUT_SAMPLE_RATE 24000

/* ---------------------------------------------------------------------------
 * ES8311 音频：I2S 部分
 * 这四个引脚完全沿用资料值（I2S 优先策略），是本文件可信度最高的一组。
 * ------------------------------------------------------------------------- */
#define AUDIO_I2S_GPIO_MCLK  GPIO_NUM_2   // MCLK  （资料值，保留）
#define AUDIO_I2S_GPIO_BCLK  GPIO_NUM_46  // BCLK  （资料值，保留）
#define AUDIO_I2S_GPIO_WS    GPIO_NUM_45  // WS/LRCK（资料值，保留）
#define AUDIO_I2S_GPIO_DIN   GPIO_NUM_7   // DIN（麦克风 -> ESP32）（资料值，保留）
#define AUDIO_I2S_GPIO_DOUT  GPIO_NUM_10  // DOUT（ESP32 -> 扬声器）【推测】资料未给出，选空闲 GPIO10

/* ---------------------------------------------------------------------------
 * ES8311 音频：I2C 控制部分
 * 资料没有给 ES8311 的 I2C 引脚，只给了触摸 I2C 的候选集（SDA=1/8，SCL=2/9）。
 * 由于 GPIO2 已被 MCLK 占用、GPIO1 是触摸 I2C SDA 的候选，
 * 这里从候选集中取 SDA=8 / SCL=9（候选集内自洽的一对）。
 * ------------------------------------------------------------------------- */
#define AUDIO_CODEC_I2C_NUM       I2C_NUM_0
#define AUDIO_CODEC_I2C_SDA_PIN   GPIO_NUM_8   // 【推测】取自资料触摸 I2C 候选集 {1,8} 中的 8
#define AUDIO_CODEC_I2C_SCL_PIN   GPIO_NUM_9   // 【推测】取自资料触摸 I2C 候选集 {2,9} 中的 9（2 已被 MCLK 占用）
#define AUDIO_CODEC_ES8311_ADDR   ES8311_CODEC_DEFAULT_ADDR

/* 功放使能：资料未提及 PA 控制脚，故不使能（NC） */
#define AUDIO_CODEC_PA_PIN        GPIO_NUM_NC

/* ---------------------------------------------------------------------------
 * 按键与指示灯
 * ------------------------------------------------------------------------- */
#define BOOT_BUTTON_GPIO    GPIO_NUM_0   // BOOT 键，ESP32-S3 通用惯例
#define BUILTIN_LED_GPIO    GPIO_NUM_48  // 【推测】资料未给出；ESP32-S3 常见 WS2812 在 GPIO48

/* ---------------------------------------------------------------------------
 * ILI9341 2.8 寸 SPI 屏
 *
 *  信号   资料值   采用值   说明
 *  CS     5        5       资料值，与其它外设不冲突，保留
 *  DC     6        6       资料值，保留（DC/SCK 同名冲突时优先保 DC）
 *  RST    4        4       资料值，保留（SD 的 CS 也是 4，但本版型不实现 SD）
 *  MOSI   7        11      【推测】7 已被 I2S-DIN 占用，改到空闲的 GPIO11
 *  SCK    6        12      【推测】6 已被 LCD-DC 占用，改到空闲的 GPIO12
 *  MISO   1        NC      【推测】ILI9341 无需读回；且 1 与触摸 I2C SDA 候选冲突，直接不接
 *  BL     -        14      【推测】资料未给出背光引脚
 * ------------------------------------------------------------------------- */
#define DISPLAY_CS_PIN        GPIO_NUM_5
#define DISPLAY_DC_PIN        GPIO_NUM_6
#define DISPLAY_RST_PIN       GPIO_NUM_4
#define DISPLAY_MOSI_PIN      GPIO_NUM_11  // 【推测】原资料 GPIO7
#define DISPLAY_SCK_PIN       GPIO_NUM_12  // 【推测】原资料 GPIO6
#define DISPLAY_MISO_PIN      GPIO_NUM_NC  // 【推测】原资料 GPIO1，改为不接

#define DISPLAY_BACKLIGHT_PIN GPIO_NUM_14  // 【推测】资料未给出
#define DISPLAY_BACKLIGHT_OUTPUT_INVERT false

#define LCD_SPI_HOST          SPI2_HOST
#define DISPLAY_SPI_SCLK_HZ   (20 * 1000 * 1000)
#define DISPLAY_SPI_MODE      0

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

/* ---------------------------------------------------------------------------
 * 刻意不实现的外设（资料提到但信息不足 / 已知异常）
 *   - 触摸屏：资料记录存在但初始化失败（"touch ic error!"），
 *             芯片型号与 I2C 引脚均无法确定 -> 不实现
 *   - SD 卡：资料只给了 SPI 引脚且与 LCD/I2S 冲突 -> 不实现
 * 若后续拿到原理图，可在此补充 TOUCH_I2C_* / SD_* 宏。
 * ------------------------------------------------------------------------- */

#endif  // _BOARD_CONFIG_H_

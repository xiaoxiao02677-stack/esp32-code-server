/* ============================================================
 * display.c — SPI + ST7789 (240x240) + LVGL port
 * ESP-IDF v6.1
 * ============================================================ */
#include <string.h>
#include "esp_err.h"
#include "esp_idf_version.h"
#include "esp_log.h"
#include "esp_heap_caps.h"
#include "driver/spi_master.h"
#include "driver/gpio.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "esp_lcd_panel_io.h"
#include "esp_lcd_panel_ops.h"

#if __has_include("esp_lcd_panel_st7789.h")
#include "esp_lcd_panel_st7789.h"
#else
#error "本 IDF 未内置 esp_lcd_panel_st7789。请在 main/idf_component.yml 加依赖：" \
       "espressif/esp_lcd_st7789"
#endif

#include "esp_lvgl_port.h"
#include "app_config.h"
#include "emopet_ui.h"

static const char *TAG = "display";

static esp_lcd_panel_handle_t s_panel = NULL;
static esp_lcd_panel_io_handle_t s_io = NULL;

/* v6.1 起 esp_lcd 用 FourCC 色格式取代 bits_per_pixel */
#if ESP_IDF_VERSION >= ESP_IDF_VERSION_VAL(6, 1, 0)
#define PET_USE_FOURCC_COLOR 1
#else
#define PET_USE_FOURCC_COLOR 0
#endif

/* ── 背光（BLK）。开机动画靠它避免上电花屏 ────────── */
void display_backlight(bool on)
{
    gpio_set_level(CONFIG_LCD_PIN_BLK, on ? 1 : 0);
}

/* 把整屏刷成暖黑 #1A1412（RGB565），上电第一件事 */
void display_clear_dark(void)
{
    const uint16_t dark = 0x18E3;  /* #1A1412 -> RGB565 */
    size_t px = (size_t)SCR_W * SCR_H;
    uint16_t *buf = heap_caps_malloc(px * sizeof(uint16_t), MALLOC_CAP_8BIT);
    if (!buf) { ESP_LOGW(TAG, "清屏缓冲分配失败，跳过"); return; }
    for (size_t i = 0; i < px; i++) buf[i] = dark;
    esp_lcd_panel_draw_bitmap(s_panel, 0, 0, SCR_W, SCR_H, buf);
    heap_caps_free(buf);
}

lv_display_t *display_init(void)
{
    /* ── 1. 背光 GPIO，先拉低 ─────────────────────── */
    gpio_config_t blk = {
        .pin_bit_mask = (1ULL << CONFIG_LCD_PIN_BLK),
        .mode = GPIO_MODE_OUTPUT,
        .pull_up_en = GPIO_PULLUP_DISABLE,
        .pull_down_en = GPIO_PULLDOWN_DISABLE,
        .intr_type = GPIO_INTR_DISABLE,
    };
    ESP_ERROR_CHECK(gpio_config(&blk));
    display_backlight(false);

    /* ── 2. SPI 总线 ─────────────────────────────── */
    spi_bus_config_t bus_cfg = {
        .sclk_io_num = CONFIG_LCD_PIN_SCLK,
        .mosi_io_num = CONFIG_LCD_PIN_MOSI,
        .miso_io_num = -1,
        .quadwp_io_num = -1,
        .quadhd_io_num = -1,
        .data4_io_num = -1,
        .data5_io_num = -1,
        .data6_io_num = -1,
        .data7_io_num = -1,
        .max_transfer_sz = SCR_W * SCR_H * sizeof(uint16_t) + 8,
    };
    ESP_ERROR_CHECK(spi_bus_initialize(CONFIG_LCD_SPI_HOST, &bus_cfg, SPI_DMA_CH_AUTO));

    esp_lcd_panel_io_spi_config_t io_cfg = {
        .cs_gpio_num = CONFIG_LCD_PIN_CS,
        .dc_gpio_num = CONFIG_LCD_PIN_DC,
        .spi_mode = 0,
        .pclk_hz = CONFIG_LCD_SPI_FREQ_MHZ * 1000 * 1000,
        .trans_queue_depth = 10,
        .lcd_cmd_bits = 8,
        .lcd_param_bits = 8,
    };
    ESP_ERROR_CHECK(esp_lcd_new_panel_io_spi((esp_lcd_spi_bus_handle_t)CONFIG_LCD_SPI_HOST,
                                             &io_cfg, &s_io));

    /* ── 3. ST7789 面板 ────────────────────────────
     * 注意：v6.1 用 .color_format（FourCC）替代 .bits_per_pixel。
     * 若你的 IDF 头文件字段名不同，以 esp_lcd_panel_dev.h 为准。 */
    esp_lcd_panel_dev_config_t panel_cfg = {
        .reset_gpio_num = CONFIG_LCD_PIN_RST,
        .rgb_endian = LCD_RGB_ENDIAN_RGB,
#if PET_USE_FOURCC_COLOR
        .color_format = LCD_COLOR_FORMAT_RGB565,
#else
        .bits_per_pixel = 16,
#endif
    };
    ESP_ERROR_CHECK(esp_lcd_new_panel_st7789(s_io, &panel_cfg, &s_panel));

    ESP_ERROR_CHECK(esp_lcd_panel_reset(s_panel));
    ESP_ERROR_CHECK(esp_lcd_panel_init(s_panel));
    ESP_ERROR_CHECK(esp_lcd_panel_disp_on_off(s_panel, true));

    /* 240x240 模块常有行列偏移，按需配置 */
    if (CONFIG_LCD_GAP_X || CONFIG_LCD_GAP_Y) {
        ESP_ERROR_CHECK(esp_lcd_panel_set_gap(s_panel, CONFIG_LCD_GAP_X, CONFIG_LCD_GAP_Y));
    }
    if (CONFIG_LCD_MIRROR_X || CONFIG_LCD_MIRROR_Y) {
        ESP_ERROR_CHECK(esp_lcd_panel_mirror(s_panel, CONFIG_LCD_MIRROR_X, CONFIG_LCD_MIRROR_Y));
    }

    /* ── 4. 上电花屏对策：先刷暖黑，再开背光 ──────── */
    display_clear_dark();
    vTaskDelay(pdMS_TO_TICKS(120));
    display_backlight(true);

    /* ── 5. LVGL port ──────────────────────────────
     * 显式指定 task_affinity=0：LVGL 固定在 core0，把 core1 留给音频。
     * 不要用 ESP_LVGL_PORT_INIT_CONFIG()，它默认 affinity=-1（可迁移）。 */
    const lvgl_port_cfg_t lvgl_cfg = {
        .task_priority = 4,
        .task_stack = 6144,
        .task_affinity = 0,
        .task_max_sleep_ms = 500,
        .timer_period_ms = 5,
    };
    ESP_ERROR_CHECK(lvgl_port_init(&lvgl_cfg));

    const lvgl_port_display_cfg_t disp_cfg = {
        .io_handle = s_io,
        .panel_handle = s_panel,
        .buffer_size = SCR_W * SCR_H,
        .double_buffer = true,
        .hres = SCR_W,
        .vres = SCR_H,
        .monochrome = false,
        .color_format = LV_COLOR_FORMAT_RGB565,
        .rotation = {
            .swap_xy = false,
            .mirror_x = false,
            .mirror_y = false,
        },
        .flags = {
            .buff_dma = true,
            .swap_bytes = false,
        },
    };
    lv_display_t *disp = lvgl_port_add_disp(&disp_cfg);
    if (!disp) { ESP_LOGE(TAG, "lvgl_port_add_disp 失败"); return NULL; }

    /* 旋转必须在 lvgl_port_add_disp 之后设置，否则会被内部重置 */
    if (CONFIG_LCD_MIRROR_X || CONFIG_LCD_MIRROR_Y) {
        ESP_ERROR_CHECK(esp_lcd_panel_mirror(s_panel, CONFIG_LCD_MIRROR_X, CONFIG_LCD_MIRROR_Y));
    }

    ESP_LOGI(TAG, "display ready: %dx%d @ %dMHz SPI", SCR_W, SCR_H, CONFIG_LCD_SPI_FREQ_MHZ);
    return disp;
}

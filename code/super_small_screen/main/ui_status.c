/*
 * ui_status.c - OLED status screens for super_small_screen (ESP32-S3).
 *
 * Panel geometry: 72x40 px, 5 pages (y is a page number in draw_string).
 * Font: 5x7 with 6 px advance -> 12 chars max per centered line.
 */
#include "ui_status.h"
#include "ssd1306.h"
#include "font.h"
#include <string.h>

#define UI_WIDTH   OLED_WIDTH    /* 72 */
#define UI_PAGES   OLED_PAGE_COUNT /* 5 */
#define UI_CHAR_W  6             /* 5 px glyph + 1 px spacing */
#define UI_MAX_LEN 12            /* 12 chars * 6 = 72 px */

static void ui_commit(void)
{
    ssd1306_refresh();
}

static void ui_draw_centered_page(const char *str, uint8_t page)
{
    if (!str || !*str) {
        return;
    }
    size_t len = strlen(str);
    if (len > UI_MAX_LEN) {
        len = UI_MAX_LEN;
    }
    uint8_t x = (uint8_t)((UI_WIDTH - (int)len * UI_CHAR_W + 1) / 2);
    ssd1306_draw_string(x, page, str);
}

/* --- scaled / pixel helpers (only used for the big "CCC" eye) --- */

/* Draw a 5x7 glyph scaled by an integer factor, top-left at pixel (x, y). */
static void ui_draw_glyph_scaled(char c, uint8_t x, uint8_t y, uint8_t scale)
{
    if (c < 32 || c > 126) {
        c = '?';
    }
    const uint8_t *glyph = font5x7[c - 32];
    for (uint8_t col = 0; col < 5; col++) {
        uint8_t bits = glyph[col];
        for (uint8_t row = 0; row < 7; row++) {
            if (bits & (1u << (6 - row))) {
                for (uint8_t sy = 0; sy < scale; sy++) {
                    uint8_t py = y + row * scale + sy;
                    for (uint8_t sx = 0; sx < scale; sx++) {
                        ssd1306_draw_pixel(x + col * scale + sx, py, 1);
                    }
                }
            }
        }
    }
}

/* Width in pixels of a string drawn at the given scale. */
static uint16_t ui_text_width(const char *str, uint8_t scale)
{
    return (uint16_t)(strlen(str) * (5u * scale + scale)); /* advance 6*scale */
}

/* Draw a string scaled by an integer factor, centered on pixel rows
 * [y_top, y_top + 7*scale). */
static void ui_draw_centered_scaled(const char *str, uint8_t y_top, uint8_t scale)
{
    uint16_t w = ui_text_width(str, scale);
    if (w > UI_WIDTH) {
        return;
    }
    uint8_t x0 = (uint8_t)((UI_WIDTH - w) / 2);
    uint8_t x = x0;
    while (*str) {
        ui_draw_glyph_scaled(*str++, x, y_top, scale);
        x = (uint8_t)(x + 6u * scale);
    }
}

/* --- public screens --- */

void ui_show_wifi_config(const char *ssid, const char *url)
{
    char line[17]; /* 12 chars + "..." + NUL */

    ssd1306_clear();
    ui_draw_centered_page("WiFi CFG", 1);

    if (ssid && *ssid) {
        size_t len = strlen(ssid);
        if (len > UI_MAX_LEN) {
            memcpy(line, ssid, UI_MAX_LEN);
            memcpy(line + UI_MAX_LEN, "...", 4);
        } else {
            memcpy(line, ssid, len + 1);
        }
        ui_draw_centered_page(line, 3);
    }

    /* 配网页地址（去掉 "http://" 前缀，OLED 只显示主机部分） */
    if (url && *url) {
        const char *p = strstr(url, "://");
        p = p ? p + 3 : url;
        size_t len = strlen(p);
        if (len > UI_MAX_LEN) {
            memcpy(line, p, UI_MAX_LEN);
            memcpy(line + UI_MAX_LEN, "...", 4);
        } else {
            memcpy(line, p, len + 1);
        }
        ui_draw_centered_page(line, 4);
    }

    ui_commit();
}

void ui_show_connecting(void)
{
    ssd1306_clear();
    ui_draw_centered_page("Connecting", 2);
    ui_commit();
}

void ui_show_ccc(void)
{
    /* Big "CCC": three 3x scaled C's span the panel (21 px tall), with a
     * small "CONNECTED" caption on the last page. */
    ssd1306_clear();
    ui_draw_centered_scaled("CCC", 2, 3);
    ui_draw_centered_page("CONNECTED", 4);
    ui_commit();
}

void ui_show_hello_world(void)
{
    /* Same layout as the original boot screen. */
    ssd1306_clear();
    ssd1306_draw_string(6, 1, "Hello");
    ssd1306_draw_string(0, 3, "World!");
    ui_commit();
}

void ui_show_sync(void)
{
    ssd1306_clear();
    ui_draw_centered_page("SYNC...", 2);
    ui_commit();
}

void ui_show_reboot(void)
{
    ssd1306_clear();
    ui_draw_centered_page("Reboot...", 2);
    ui_commit();
}

void ui_show_text(const char *line1, const char *line2)
{
    ssd1306_clear();
    ui_draw_centered_page(line1, 1);
    ui_draw_centered_page(line2, 3);
    ui_commit();
}

#include "ssd1306.h"
#include "i2cdev.h"
#include "font.h"
#include "esp_log.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include <string.h>

static const char *TAG = "ssd1306";

/* 72x40 panel = 5 pages of 72 bytes */
static uint8_t fb[OLED_PAGE_COUNT][OLED_WIDTH];

static esp_err_t cmd(uint8_t opcode)
{
    uint8_t buf[2] = { 0x00, opcode };
    return i2cdev_write(OLED_I2C_ADDR, buf, sizeof(buf));
}

esp_err_t ssd1306_init(void)
{
    /* Wait for the panel to power up after reset */
    vTaskDelay(pdMS_TO_TICKS(50));

    esp_err_t err;
    /* Display off while configuring */
    if ((err = cmd(0xAE)) != ESP_OK) return err;
    /* 0.42" module: column offset 28 inside the 128-column controller RAM */
    if ((err = cmd(0xD3)) == ESP_OK)      if ((err = cmd(0x00)) != ESP_OK) return err;
    /* Horizontal addressing mode for linear framebuffer writes */
    if ((err = cmd(0x20)) == ESP_OK)      if ((err = cmd(0x00)) != ESP_OK) return err;
    /* Start line = 0 */
    if ((err = cmd(0x40)) != ESP_OK) return err;
    /* Segment remap: column 127 mapped to segment 0 (left-orientation) */
    if ((err = cmd(0xA1)) != ESP_OK) return err;
    /* COM scan direction: remapped */
    if ((err = cmd(0xC8)) != ESP_OK) return err;
    /* Multiplex ratio: 40 COM lines */
    if ((err = cmd(0xA8)) == ESP_OK)      if ((err = cmd(0x27)) != ESP_OK) return err;  /* 0x27 = 39 => 40 MUX */
    /* Clock divide 0xF0/0x80 ~ 100 fps; default is fine */
    if ((err = cmd(0xD5)) == ESP_OK)      if ((err = cmd(0x80)) != ESP_OK) return err;
    /* Precharge: phase1 1, phase2 0xF */
    if ((err = cmd(0xD9)) == ESP_OK)      if ((err = cmd(0x21)) != ESP_OK) return err;
    /* COM pins hardware configuration: alternative, no remap */
    if ((err = cmd(0xDA)) == ESP_OK)      if ((err = cmd(0x12)) != ESP_OK) return err;
    /* Contrast */
    if ((err = cmd(0x81)) == ESP_OK)      if ((err = cmd(0xCF)) != ESP_OK) return err;
    /* Charge pump: enable (required for OLED VCC generation) */
    if ((err = cmd(0x8D)) == ESP_OK)      if ((err = cmd(0x14)) != ESP_OK) return err;
    /* Display RAM contents (not all-on) */
    if ((err = cmd(0xA4)) != ESP_OK) return err;
    /* Normal (non-inverted) display */
    if ((err = cmd(0xA6)) != ESP_OK) return err;

    /* Clear GDDRAM: 5 pages x 72 columns starting at (28,0) in horizontal mode */
    ssd1306_clear();
    if ((err = ssd1306_refresh()) != ESP_OK) return err;

    /* Display on */
    if ((err = cmd(0xAF)) != ESP_OK) return err;
    ESP_LOGI(TAG, "SSD1306 72x40 initialized");
    return ESP_OK;
}

void ssd1306_clear(void)
{
    memset(fb, 0, sizeof(fb));
}

void ssd1306_draw_string(uint8_t x, uint8_t page, const char *str)
{
    if (page >= OLED_PAGE_COUNT) {
        return;
    }
    while (*str && x + 5 < OLED_WIDTH) {
        char c = *str++;
        if (c < 32 || c > 126) {
            c = '?';
        }
        const uint8_t *glyph = font5x7[c - 32];
        for (uint8_t col = 0; col < 5; col++) {
            if (x + col < OLED_WIDTH) {
                fb[page][x + col] = glyph[col];
            }
        }
        x += 6;
    }
}

void ssd1306_draw_pixel(uint8_t x, uint8_t y, uint8_t on)
{
    if (x >= OLED_WIDTH || y >= OLED_HEIGHT) {
        return;
    }
    if (on) {
        fb[y / 8][x] |= (uint8_t)(1u << (y % 8));
    } else {
        fb[y / 8][x] &= (uint8_t)~(1u << (y % 8));
    }
}

esp_err_t ssd1306_refresh(void)
{
    /* Set column window to the visible 72 columns (28..99) */
    esp_err_t err;
    if ((err = cmd(0x21)) != ESP_OK) return err;
    if ((err = cmd(28)) != ESP_OK) return err;
    if ((err = cmd(28 + OLED_WIDTH - 1)) != ESP_OK) return err;
    /* Set page window 0..4 */
    if ((err = cmd(0x22)) != ESP_OK) return err;
    if ((err = cmd(0x00)) != ESP_OK) return err;
    if ((err = cmd(OLED_PAGE_COUNT - 1)) != ESP_OK) return err;

    /* Single continuous data write of all 5 pages (horizontal mode auto-advances) */
    uint8_t pkt[1 + OLED_PAGE_COUNT * OLED_WIDTH];
    pkt[0] = 0x40;
    memcpy(&pkt[1], fb, sizeof(fb));
    return i2cdev_write(OLED_I2C_ADDR, pkt, sizeof(pkt));
}

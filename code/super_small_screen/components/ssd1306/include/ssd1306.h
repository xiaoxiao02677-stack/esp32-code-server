/*
 * SSD1306 0.42" OLED (72x40) minimal driver for ESP32-S3
 * I2C address 0x3C, charge pump on, custom 72x40 panel geometry
 */
#ifndef SSD1306_H
#define SSD1306_H

#include <stdint.h>
#include "esp_err.h"

#define OLED_WIDTH   72
#define OLED_HEIGHT  40
#define OLED_I2C_ADDR 0x3C
#define OLED_PAGE_COUNT (OLED_HEIGHT / 8)

/* Call once after i2cdev_init(). Returns ESP_OK on success. */
esp_err_t ssd1306_init(void);

/* Clear the local framebuffer (does NOT push to display). */
void ssd1306_clear(void);

/* Draw an ASCII string with the built-in 5x7 font, scale 1.
 * x in pixels [0..71], y in pages [0..4] (one page = 8 pixel rows). */
void ssd1306_draw_string(uint8_t x, uint8_t page, const char *str);

/* Push the framebuffer to the display over I2C. */
esp_err_t ssd1306_refresh(void);

#endif /* SSD1306_H */

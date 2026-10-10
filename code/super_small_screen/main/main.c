#include "ssd1306.h"
#include "i2cdev.h"
#include "esp_log.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

static const char *TAG = "main";

/* Common SDA/SCL pairs found on ESP32-S3 boards with an onboard 0.42" OLED.
 * The winning pair is remembered across the scan. */
static const int pin_pairs[][2] = {
    /* {SDA, SCL} */
    {40, 41},   /* original guess */
    {41, 42},
    {8, 9},
    {9, 8},
    {47, 48},   /* some cube/round boards */
    {48, 47},
    {39, 42},
    {42, 39},
    {41, 40},
    {5, 6},
    {6, 5},
    {17, 18},
    {18, 17},
    {15, 16},
    {16, 15},
    {11, 12},
    {12, 11},
    {10, 11},
    {1, 2},
    {2, 1},
    {35, 36},
    {36, 35},
    {37, 38},
    {38, 37},
    {21, 22},
    {22, 21},
    {19, 20},
    {20, 19},
    {3, 4},
    {4, 3},
    {13, 14},
    {14, 13},
};
#define PIN_PAIR_COUNT (sizeof(pin_pairs) / sizeof(pin_pairs[0]))

static int detect_oled_pins(void)
{
    for (size_t i = 0; i < PIN_PAIR_COUNT; i++) {
        int sda = pin_pairs[i][0];
        int scl = pin_pairs[i][1];
        vTaskDelay(pdMS_TO_TICKS(5));
        esp_err_t err = i2cdev_probe(sda, scl, OLED_I2C_ADDR);
        if (err == ESP_OK) {
            ESP_LOGI(TAG, "OLED found at 0x%02X on SDA=%d SCL=%d",
                     OLED_I2C_ADDR, sda, scl);
            return (sda << 8) | scl;
        }
        ESP_LOGI(TAG, "probe SDA=%2d SCL=%2d ... %s",
                 sda, scl, esp_err_to_name(err));
    }
    return -1;
}

void app_main(void)
{
    ESP_LOGI(TAG, "boot: ESP32-S3 + 0.42in SSD1306 hello world");

    int found = detect_oled_pins();
    if (found < 0) {
        ESP_LOGE(TAG, "no OLED on any known pin pair - check wiring/pullups");
        return;
    }

    int sda = (found >> 8) & 0xFF;
    int scl = found & 0xFF;

    esp_err_t err = i2cdev_init_with(sda, scl);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "I2C init failed: %s", esp_err_to_name(err));
        return;
    }

    err = ssd1306_init();
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "OLED init failed: %s", esp_err_to_name(err));
        return;
    }

    ssd1306_clear();
    ssd1306_draw_string(6, 1, "Hello");
    ssd1306_draw_string(0, 3, "World!");
    err = ssd1306_refresh();
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "OLED refresh failed: %s", esp_err_to_name(err));
        return;
    }
    ESP_LOGI(TAG, "hello world rendered on SDA=%d SCL=%d", sda, scl);
}

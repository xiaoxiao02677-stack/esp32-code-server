#include "ssd1306.h"
#include "i2cdev.h"
#include "esp_log.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

static const char *TAG = "main";

void app_main(void)
{
    ESP_LOGI(TAG, "boot: ESP32-S3 + 0.42in SSD1306 hello world");

    esp_err_t err = i2cdev_init();
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
    }
    ESP_LOGI(TAG, "hello world rendered");
}

/*
 * main.c - 直接连接 Sandyun WiFi，测试 WebSocket 链路
 * 硬编码凭证，跳过 AP 配网，用于验证射频和服务器连通性
 */
#include <string.h>

#include "esp_log.h"
#include "esp_err.h"
#include "nvs_flash.h"

#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "freertos/event_groups.h"

#include "ssd1306.h"
#include "i2cdev.h"
#include "ui_status.h"
#include "wifi_manager.h"
#include "server_link.h"

static const char *TAG = "main";

/* Common SDA/SCL pairs */
static const int pin_pairs[][2] = {
    {40, 41}, {41, 42}, {8, 9}, {9, 8},
    {47, 48}, {48, 47}, {39, 42}, {42, 39},
    {41, 40}, {5, 6}, {6, 5}, {17, 18},
    {18, 17}, {15, 16}, {16, 15}, {11, 12},
    {12, 11}, {10, 11}, {1, 2}, {2, 1},
    {35, 36}, {36, 35}, {37, 38}, {38, 37},
    {21, 22}, {22, 21}, {19, 20}, {20, 19},
    {3, 4}, {4, 3}, {13, 14}, {14, 13},
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

#define APP_BIT_WIFI_CONNECTED  BIT0
#define APP_BIT_CFG_RECEIVED    BIT1

static EventGroupHandle_t s_app_events;

static void on_config_received(device_config_t *cfg)
{
    ESP_LOGI(TAG, "config received: session_id=%s", cfg->session_id);
    xEventGroupSetBits(s_app_events, APP_BIT_CFG_RECEIVED);
}

/* Hard-coded WiFi credentials for Sandyun AP */
#define WIFI_SSID     "Sandyun"
#define WIFI_PASSWORD "87316918"

void app_main(void)
{
    ESP_LOGI(TAG, "boot: connect to %s, test WebSocket link", WIFI_SSID);

    /* 1. NVS */
    esp_err_t err = nvs_flash_init();
    if (err == ESP_ERR_NVS_NO_FREE_PAGES || err == ESP_ERR_NVS_NEW_VERSION_FOUND) {
        ESP_ERROR_CHECK(nvs_flash_erase());
        err = nvs_flash_init();
    }
    ESP_ERROR_CHECK(err);

    /* 2. OLED */
    int found = detect_oled_pins();
    if (found < 0) {
        ESP_LOGE(TAG, "no OLED - check wiring");
        return;
    }
    int sda = (found >> 8) & 0xFF;
    int scl = found & 0xFF;
    ESP_ERROR_CHECK(i2cdev_init_with(sda, scl));
    ESP_ERROR_CHECK(ssd1306_init());
    ESP_LOGI(TAG, "OLED ready on SDA=%d SCL=%d", sda, scl);

    s_app_events = xEventGroupCreate();
    ESP_ERROR_CHECK(s_app_events ? ESP_OK : ESP_ERR_NO_MEM);

    /* 3. Save WiFi creds to NVS and connect */
    nvs_handle_t nvs;
    nvs_open("wifi", NVS_READWRITE, &nvs);
    nvs_set_str(nvs, "ssid", WIFI_SSID);
    nvs_set_str(nvs, "password", WIFI_PASSWORD);
    nvs_commit(nvs);
    nvs_close(nvs);
    ESP_LOGI(TAG, "WiFi creds saved: %s", WIFI_SSID);

    ui_show_connecting();
    ESP_LOGI(TAG, "Connecting to '%s'...", WIFI_SSID);
    if (wifi_connect_sta() != ESP_OK) {
        ESP_LOGE(TAG, "WiFi connect FAILED");
        ui_show_hello_world();
        for (;;) vTaskDelay(pdMS_TO_TICKS(1000));
    }
    ESP_LOGI(TAG, "WiFi connected: ssid=%s ip=%s",
             wifi_manager_get_sta_ssid(), wifi_manager_get_ip());

    /* 4. Server link */
    ui_show_sync();
    server_link_set_on_config(on_config_received);
    int rc = server_link_start();
    ESP_LOGI(TAG, "server_link_start() = %d", rc);

    EventBits_t bits = xEventGroupWaitBits(s_app_events, APP_BIT_CFG_RECEIVED,
                                           pdTRUE, pdFALSE,
                                           pdMS_TO_TICKS(30000));
    if (bits & APP_BIT_CFG_RECEIVED ||
        server_link_get_state() == SERVER_LINK_STATE_CONFIG_RECEIVED) {
        ui_show_ccc();
        ESP_LOGI(TAG, "CCC displayed - WebSocket link OK");
    } else {
        ESP_LOGE(TAG, "server config not received (state=%d)", server_link_get_state());
        ui_show_hello_world();
    }

    /* Keep alive */
    for (;;) vTaskDelay(pdMS_TO_TICKS(1000));
}

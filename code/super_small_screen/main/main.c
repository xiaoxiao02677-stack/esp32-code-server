/*
 * main.c - 开机即配网模式（小圆屏同款：热点 + 浏览器网页配网）
 *
 * 上电后立刻启动热点 "XZS3-XXXX"（开放网络，网关 192.168.4.1）：
 *   1. 手机连热点，自动弹出配网页（DNS 劫持/captive portal）
 *   2. 网页选 WiFi 输密码提交 -> 设备验证连接成功 -> 凭据存 NVS
 *   3. 网页跳转成功页 -> 自动请求 /exit -> 配网模式退出
 *   4. 设备自动用保存的 WiFi 连接 STA（CONFIG_MODE_EXIT -> start_station）
 *   5. STA 连上（CONNECTED）-> 启动 server_link（WebSocket 到服务器）
 *
 * 配网组件源码在 components/wifi_connect/（78/esp-wifi-connect v3.3.1 本地副本），
 * C 桥接层 main/wifi_bridge.{h,cc}。屏幕状态机：
 *   配网中  "WiFi CFG" + 热点名 + 192.168.4.1
 *   连WiFi  Connecting
 *   连服务器 SYNC...
 *   配置完成 CCC（大眼）
 */
#include <string.h>

#include "esp_log.h"
#include "esp_err.h"

#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

#include "ssd1306.h"
#include "i2cdev.h"
#include "ui_status.h"
#include "wifi_bridge.h"
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

/* WiFi 事件 -> UI + server_link 联动（在 WiFi 事件任务上下文，勿阻塞） */
static void on_wifi_event(wifi_bridge_event_t ev, const char *data)
{
    switch (ev) {
    case WIFI_BRIDGE_EVENT_CONFIG_MODE_ENTER:
        ESP_LOGI(TAG, "config AP up: ssid=%s url=%s",
                 wifi_bridge_get_ap_ssid(), wifi_bridge_get_ap_url());
        break;
    case WIFI_BRIDGE_EVENT_CONFIG_MODE_EXIT:
        ESP_LOGI(TAG, "config mode exit, connecting to saved WiFi...");
        ui_show_connecting();
        wifi_bridge_start_station();
        break;
    case WIFI_BRIDGE_EVENT_CONNECTED:
        ESP_LOGI(TAG, "WiFi connected: ssid=%s ip=%s",
                 data, wifi_bridge_get_ip());
        ui_show_sync();
        {
            int st = server_link_get_state();
            if (st == SERVER_LINK_STATE_IDLE || st == SERVER_LINK_STATE_FAILED) {
                int rc = server_link_start();
                ESP_LOGI(TAG, "server_link_start() = %d", rc);
            }
        }
        break;
    case WIFI_BRIDGE_EVENT_DISCONNECTED:
        ESP_LOGW(TAG, "WiFi disconnected (reason=%s)", data);
        break;
    }
}

void app_main(void)
{
    ESP_LOGI(TAG, "boot: provisioning mode (hotspot + web portal)");

    /* 1. OLED（I2C 引脚自动探测） */
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

    /* 2. WiFi 配网组件（内部完成 NVS/netif/事件循环/wifi 驱动初始化） */
    if (wifi_bridge_init("XZS3", "zh-CN") != ESP_OK) {
        ESP_LOGE(TAG, "wifi_bridge_init failed");
        ui_show_text("AP ERR", "RST");
        for (;;) vTaskDelay(pdMS_TO_TICKS(1000));
    }
    wifi_bridge_set_event_callback(on_wifi_event);

    /* 3. 开机直接启动配网热点（不连 WiFi，用户要求） */
    wifi_bridge_start_config_ap();
    wifi_bridge_set_tx_power_dbm(8); /* 发射功率上限 8dBm（档位值 34，非 ×4） */

    const char *ssid = wifi_bridge_get_ap_ssid();
    const char *url = wifi_bridge_get_ap_url();
    ui_show_wifi_config(ssid, url);
    ESP_LOGI(TAG, "config AP \"%s\" up, portal %s", ssid, url);
    ESP_LOGI(TAG, "connect phone to AP -> portal -> submit WiFi -> STA -> server");

    /* 4. 主循环：轮询 server_link 状态，配置同步完成即亮 CCC */
    int last_state = -1;
    for (;;) {
        int st = server_link_get_state();
        if (st != last_state) {
            ESP_LOGI(TAG, "server_link state=%d", st);
            last_state = st;
            if (st == SERVER_LINK_STATE_CONFIG_RECEIVED) {
                ui_show_ccc();
                ESP_LOGI(TAG, "CCC displayed - WebSocket link OK");
            } else if (st == SERVER_LINK_STATE_FAILED) {
                /* 服务器不可达：保持现状，WiFi 重连后 CONNECTED 会再次 start */
                ui_show_text("NO SRV", "RETRY...");
            }
        }
        vTaskDelay(pdMS_TO_TICKS(500));
    }
}
/*
 * wifi_bridge.cc - C 桥接层实现（封装 78/esp-wifi-connect 的 C++ WifiManager）。
 * 注意：WifiManager 的 GetSsid/GetIpAddress/GetApSsid/GetApWebUrl 返回
 * std::string 临时对象，c_str() 指针不能直接回传，必须拷贝到静态缓冲。
 */
#include "wifi_bridge.h"

#include <cstdio>
#include <string>

#include "esp_log.h"
#include "esp_mac.h"
#include "esp_wifi.h"
#include "nvs.h"

#include "wifi_manager.h"

static const char *TAG = "wifi_bridge";

static wifi_bridge_event_cb_t s_cb = NULL;
static char s_ap_ssid[24];
static char s_ap_url[24];
static char s_ip[16];

static void forward_event(WifiEvent ev, const std::string &data)
{
    if (!s_cb) {
        return;
    }
    wifi_bridge_event_t c_ev;
    switch (ev) {
    case WifiEvent::Connected:
        c_ev = WIFI_BRIDGE_EVENT_CONNECTED;
        break;
    case WifiEvent::Disconnected:
        c_ev = WIFI_BRIDGE_EVENT_DISCONNECTED;
        break;
    case WifiEvent::ConfigModeEnter:
        c_ev = WIFI_BRIDGE_EVENT_CONFIG_MODE_ENTER;
        break;
    case WifiEvent::ConfigModeExit:
        c_ev = WIFI_BRIDGE_EVENT_CONFIG_MODE_EXIT;
        break;
    default:
        /* Scanning / Connecting 不转发 */
        return;
    }
    s_cb(c_ev, data.c_str());
}

extern "C" {

esp_err_t wifi_bridge_init(const char *ssid_prefix, const char *language)
{
    WifiManagerConfig config;
    config.ssid_prefix = ssid_prefix ? ssid_prefix : "XZS3";
    config.language = language ? language : "zh-CN";
    config.show_ota_config = false;
    config.show_sleep_config = false;

    /* DHCP 主机名用 ASCII 前缀（非 ASCII 不被路由器接受） */
    uint8_t mac[6];
    if (esp_read_mac(mac, ESP_MAC_WIFI_STA) == ESP_OK) {
        char hostname[24];
        snprintf(hostname, sizeof(hostname), "xzs3-%02X%02X", mac[4], mac[5]);
        config.station_hostname = hostname;
    }

    return WifiManager::GetInstance().Initialize(config) ? ESP_OK : ESP_FAIL;
}

void wifi_bridge_set_event_callback(wifi_bridge_event_cb_t cb)
{
    s_cb = cb;
    WifiManager::GetInstance().SetEventCallback(forward_event);
}

void wifi_bridge_start_config_ap(void)
{
    WifiManager::GetInstance().StartConfigAp();
}

void wifi_bridge_start_station(void)
{
    WifiManager::GetInstance().StartStation();
}

const char *wifi_bridge_get_ap_ssid(void)
{
    std::string ssid = WifiManager::GetInstance().GetApSsid();
    snprintf(s_ap_ssid, sizeof(s_ap_ssid), "%s", ssid.c_str());
    return s_ap_ssid;
}

const char *wifi_bridge_get_ap_url(void)
{
    std::string url = WifiManager::GetInstance().GetApWebUrl();
    snprintf(s_ap_url, sizeof(s_ap_url), "%s", url.c_str());
    return s_ap_url;
}

esp_err_t wifi_bridge_set_tx_power_dbm(int8_t dbm)
{
    /* 官方档位表（esp_wifi.h attention 3/5）：set 值 → 实际 dBm。
     * set 值不是 dBm×4 连续可调（如 34→8、66→16 按表取整），
     * 10dBm 这类无档值会自动吸附到最近档并打 WARN。 */
    static const struct { int8_t set; int8_t dbm; } levels[] = {
        {8, 2},  {20, 5},  {28, 7},  {34, 8},  {44, 11}, {52, 13},
        {56, 14}, {60, 15}, {66, 16}, {72, 18}, {80, 20},
    };
    const int count = (int)(sizeof(levels) / sizeof(levels[0]));

    int best = -1;
    for (int i = 0; i < count; i++) {
        if (levels[i].dbm == dbm) {
            best = i;
            break;
        }
    }
    if (best < 0) {
        int best_diff = 99;
        for (int i = 0; i < count; i++) {
            int diff = levels[i].dbm - dbm;
            if (diff < 0) {
                diff = -diff;
            }
            if (diff < best_diff) {
                best_diff = diff;
                best = i;
            }
        }
        ESP_LOGW(TAG, "tx power %d dBm has no exact level, snapped to %d dBm",
                 dbm, levels[best].dbm);
    }

    const int8_t q = levels[best].set; /* 0.25dBm 单位的档位值 */

    int8_t before = 0;
    esp_wifi_get_max_tx_power(&before);
    esp_err_t err = esp_wifi_set_max_tx_power(q);
    int8_t after = 0;
    esp_wifi_get_max_tx_power(&after);
    ESP_LOGI(TAG, "tx power %d(%.1fdBm) -> set %d(%ddBm), get %d(%.1fdBm) [%s]",
             before, before / 4.0f, q, levels[best].dbm,
             after, after / 4.0f, esp_err_to_name(err));

    /* 与配网组件共用 NVS namespace "wifi"：让组件每次启动 AP 时
     * 也应用该值（组件 StartAccessPoint 读 NVS max_tx_power）。 */
    nvs_handle_t nvs;
    if (nvs_open("wifi", NVS_READWRITE, &nvs) == ESP_OK) {
        nvs_set_i8(nvs, "max_tx_power", q);
        nvs_commit(nvs);
        nvs_close(nvs);
    }
    return err;
}

bool wifi_bridge_is_config_mode(void)
{
    return WifiManager::GetInstance().IsConfigMode();
}

bool wifi_bridge_is_connected(void)
{
    return WifiManager::GetInstance().IsConnected();
}

const char *wifi_bridge_get_ip(void)
{
    std::string ip = WifiManager::GetInstance().GetIpAddress();
    snprintf(s_ip, sizeof(s_ip), "%s", ip.c_str());
    return s_ip;
}

} /* extern "C" */

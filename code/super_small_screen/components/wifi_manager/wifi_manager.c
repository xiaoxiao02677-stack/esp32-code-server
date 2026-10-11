/*
 * wifi_manager.c - minimal WiFi provisioning + STA manager
 *
 * STA mode:  credentials in NVS namespace "wifi" (keys ssid/password),
 *            15s connect timeout, auto-reconnect on drop
 * Provision: SoftAP "XZS3-XXXX" (open) + UDP JSON config server on 5555,
 *            {"ssid":"...","password":"..."} -> NVS -> reboot -> STA
 *
 * Deliberately does NOT use HTTP WebServer/DNS/SmartConfig: saves ~200KB+
 * of flash so the app fits the factory partition on a 4MB chip.
 */

#include <stdio.h>
#include <string.h>

#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "freertos/event_groups.h"

#include "esp_err.h"
#include "esp_log.h"
#include "esp_system.h"
#include "esp_mac.h"
#include "esp_netif.h"
#include "esp_event.h"
#include "esp_wifi.h"
#include "esp_netif_ip_addr.h"

#include "nvs.h"
#include "nvs_flash.h"

#include "lwip/sockets.h"

#include "wifi_manager.h"

static const char *TAG = "wifi_mgr";

#define NVS_NAMESPACE      "wifi"
#define NVS_KEY_SSID       "ssid"
#define NVS_KEY_PASSWORD   "password"

#define AP_SSID_PREFIX     "XZS3-"
#define AP_UDP_PORT        5555
#define AP_CFG_BUF_LEN     160

#define STA_CONNECT_TIMEOUT_MS  15000
#define STA_MAX_RETRY           4     /* logged retries before quiet reconnects */

#define WIFI_CONNECTED_BIT  BIT0
#define WIFI_FAIL_BIT       BIT1

static esp_netif_t *s_sta_netif = NULL;
static esp_netif_t *s_ap_netif = NULL;
static EventGroupHandle_t s_event_group = NULL;
static TaskHandle_t s_ap_task = NULL;

static esp_event_handler_instance_t s_wifi_ev = NULL;
static esp_event_handler_instance_t s_ip_ev = NULL;

static char s_ap_ssid[WIFI_MGR_AP_SSID_LEN];
static char s_sta_ssid[WIFI_MGR_SSID_LEN];
static char s_sta_password[WIFI_MGR_PASS_LEN];
static char s_sta_ip[16];

static bool s_sta_active = false;    /* STA session owns the radio */
static bool s_provisioning = false; /* AP + UDP config server up */
static bool s_stack_inited = false; /* netif/event loop/wifi driver up */

static int s_retry_count = 0;

static bool s_token_set = false;
static char s_token[32];

static const char s_reply_ok[]       = "{\"success\":true,\"msg\":\"saved, rebooting\"}";
static const char s_reply_bad[]      = "{\"success\":false,\"msg\":\"bad json\"}";
static const char s_reply_denied[]   = "{\"success\":false,\"msg\":\"bad token\"}";
static const char s_reply_save_err[] = "{\"success\":false,\"msg\":\"nvs save failed\"}";

/* ---------------- state ---------------- */

wifi_state_t wifi_manager_get_state(void)
{
    if (!s_event_group) {
        return WIFI_STATE_IDLE;
    }
    if (xEventGroupGetBits(s_event_group) & WIFI_CONNECTED_BIT) {
        return WIFI_STATE_CONNECTED;
    }
    if (s_provisioning) {
        return WIFI_STATE_SMARTCONFIG_MODE;
    }
    if (s_sta_active) {
        return WIFI_STATE_CONNECTING;
    }
    return WIFI_STATE_IDLE;
}

const char *wifi_manager_get_ap_ssid(void)
{
    return s_ap_ssid;
}

const char *wifi_manager_get_sta_ssid(void)
{
    return s_sta_ssid;
}

const char *wifi_manager_get_ip(void)
{
    return s_sta_ip;
}

void wifi_manager_set_token(const char *token)
{
    if (token && token[0]) {
        strncpy(s_token, token, sizeof(s_token) - 1);
        s_token[sizeof(s_token) - 1] = '\0';
        s_token_set = true;
    } else {
        s_token_set = false;
    }
}

/* ---------------- NVS ---------------- */

static esp_err_t nvs_init_once(void)
{
    static bool s_nvs_ready = false;
    if (s_nvs_ready) {
        return ESP_OK;
    }
    esp_err_t err = nvs_flash_init();
    if (err == ESP_ERR_NVS_NO_FREE_PAGES ||
        err == ESP_ERR_NVS_NEW_VERSION_FOUND) {
        ESP_ERROR_CHECK(nvs_flash_erase());
        err = nvs_flash_init();
    }
    if (err == ESP_OK) {
        s_nvs_ready = true;
    }
    return err;
}

static esp_err_t nvs_load_creds(char *ssid, size_t ssid_len,
                                char *password, size_t pass_len)
{
    ssid[0] = '\0';
    password[0] = '\0';

    nvs_handle_t handle;
    esp_err_t err = nvs_open(NVS_NAMESPACE, NVS_READONLY, &handle);
    if (err != ESP_OK) {
        return err;
    }

    size_t len = ssid_len;
    err = nvs_get_str(handle, NVS_KEY_SSID, ssid, &len);
    if (err != ESP_OK) {
        nvs_close(handle);
        return err;
    }

    len = pass_len;
    nvs_get_str(handle, NVS_KEY_PASSWORD, password, &len);
    /* missing password is legal -> stays "" (open network) */
    nvs_close(handle);
    return ESP_OK;
}

static esp_err_t nvs_save_creds(const char *ssid, const char *password)
{
    nvs_handle_t handle;
    esp_err_t err = nvs_open(NVS_NAMESPACE, NVS_READWRITE, &handle);
    if (err != ESP_OK) {
        return err;
    }
    err = nvs_set_str(handle, NVS_KEY_SSID, ssid);
    if (err == ESP_OK) {
        err = nvs_set_str(handle, NVS_KEY_PASSWORD, password);
    }
    if (err == ESP_OK) {
        err = nvs_commit(handle);
    }
    nvs_close(handle);
    return err;
}

bool wifi_manager_has_credentials(void)
{
    if (nvs_init_once() != ESP_OK) {
        return false;
    }
    char probe[WIFI_MGR_SSID_LEN];
    char probe_pass[WIFI_MGR_PASS_LEN];
    return (nvs_load_creds(probe, sizeof(probe),
                           probe_pass, sizeof(probe_pass)) == ESP_OK &&
            probe[0] != '\0');
}

/* ---------------- events ---------------- */

static void event_handler(void *arg, esp_event_base_t event_base,
                          int32_t event_id, void *event_data)
{
    (void)arg;
    if (event_base == WIFI_EVENT) {
        switch (event_id) {
        case WIFI_EVENT_STA_START:
            /* wifi started with STA config already set -> kick connect */
            if (s_sta_active && esp_wifi_connect() != ESP_OK) {
                xEventGroupSetBits(s_event_group, WIFI_FAIL_BIT);
            }
            break;
        case WIFI_EVENT_STA_DISCONNECTED: {
            wifi_event_sta_disconnected_t *ev = event_data;
            xEventGroupClearBits(s_event_group, WIFI_CONNECTED_BIT);
            s_sta_ip[0] = '\0';
            if (!s_sta_active) {
                /* session already given up (timeout/stop) */
                xEventGroupSetBits(s_event_group, WIFI_FAIL_BIT);
                break;
            }
            s_retry_count++;
            if (s_retry_count <= STA_MAX_RETRY) {
                ESP_LOGW(TAG, "connect failed (reason=%d), retry %d",
                         ev->reason, s_retry_count);
            } else if (s_retry_count % 20 == 0) {
                ESP_LOGW(TAG, "still reconnecting (reason=%d, try %d)",
                         ev->reason, s_retry_count);
            }
            /* keep retrying; the blocking 15s window gives up on its own */
            esp_wifi_connect();
            break;
        }
        case WIFI_EVENT_AP_STACONNECTED: {
            wifi_event_ap_staconnected_t *ev = event_data;
            ESP_LOGI(TAG, "config client " MACSTR " joined",
                     MAC2STR(ev->mac));
            break;
        }
        default:
            break;
        }
    } else if (event_base == IP_EVENT && event_id == IP_EVENT_STA_GOT_IP) {
        ip_event_got_ip_t *ev = event_data;
        snprintf(s_sta_ip, sizeof(s_sta_ip), IPSTR, IP2STR(&ev->ip_info.ip));
        s_retry_count = 0;
        ESP_LOGI(TAG, "got ip %s", s_sta_ip);
        xEventGroupSetBits(s_event_group, WIFI_CONNECTED_BIT);
    }
}

/* ---------------- STA ---------------- */

static void wifi_stack_init(void)
{
    if (s_stack_inited) {
        return;
    }
    ESP_ERROR_CHECK(esp_netif_init());
    ESP_ERROR_CHECK(esp_event_loop_create_default());

    wifi_init_config_t cfg = WIFI_INIT_CONFIG_DEFAULT();
    ESP_ERROR_CHECK(esp_wifi_init(&cfg));

    ESP_ERROR_CHECK(esp_event_handler_instance_register(
        WIFI_EVENT, ESP_EVENT_ANY_ID, &event_handler, NULL, &s_wifi_ev));
    ESP_ERROR_CHECK(esp_event_handler_instance_register(
        IP_EVENT, IP_EVENT_STA_GOT_IP, &event_handler, NULL, &s_ip_ev));

    s_stack_inited = true;
}

/* Blocking STA connect using stored credentials.
 * Idempotent: safe for the 30s background retry loop. */
esp_err_t wifi_connect_sta(void)
{
    esp_err_t err = nvs_init_once();
    if (err != ESP_OK) {
        return err;
    }
    if (!s_event_group) {
        s_event_group = xEventGroupCreate();
    }

    if (wifi_manager_get_state() == WIFI_STATE_CONNECTED) {
        return ESP_OK;    /* already up - nothing to do */
    }

    /* (Re)load creds - they may have changed in NVS */
    if (nvs_load_creds(s_sta_ssid, sizeof(s_sta_ssid),
                       s_sta_password, sizeof(s_sta_password)) != ESP_OK ||
        s_sta_ssid[0] == '\0') {
        ESP_LOGW(TAG, "no stored credentials");
        return ESP_ERR_NOT_FOUND;
    }

    wifi_stack_init();
    if (!s_sta_netif) {
        s_sta_netif = esp_netif_create_default_wifi_sta();
    }

    /* fresh attempt: stop any previous session (idempotent retry) */
    s_sta_active = false;
    esp_wifi_stop();
    ESP_ERROR_CHECK(esp_wifi_set_mode(WIFI_MODE_STA));

    wifi_config_t cfg = { 0 };
    strlcpy((char *)cfg.sta.ssid, s_sta_ssid, sizeof(cfg.sta.ssid));
    strlcpy((char *)cfg.sta.password, s_sta_password, sizeof(cfg.sta.password));
    cfg.sta.scan_method = WIFI_ALL_CHANNEL_SCAN;
    cfg.sta.failure_retry_cnt = 2;
    ESP_ERROR_CHECK(esp_wifi_set_config(WIFI_IF_STA, &cfg));

    s_sta_active = true;
    s_retry_count = 0;
    xEventGroupClearBits(s_event_group, WIFI_CONNECTED_BIT | WIFI_FAIL_BIT);

    /* esp_wifi_start fires WIFI_EVENT_STA_START -> handler calls connect */
    ESP_ERROR_CHECK(esp_wifi_start());

    ESP_LOGI(TAG, "connecting to \"%s\" (timeout %d ms)",
             s_sta_ssid, STA_CONNECT_TIMEOUT_MS);
    EventBits_t bits = xEventGroupWaitBits(s_event_group,
                                           WIFI_CONNECTED_BIT | WIFI_FAIL_BIT,
                                           pdTRUE, pdFALSE,
                                           pdMS_TO_TICKS(STA_CONNECT_TIMEOUT_MS));
    if (bits & WIFI_CONNECTED_BIT) {
        return ESP_OK;    /* s_sta_active stays true for auto-reconnect */
    }

    /* timeout or give-up: cancel the in-flight attempt */
    s_sta_active = false;
    esp_wifi_disconnect();
    esp_wifi_stop();
    return ESP_ERR_TIMEOUT;
}

/* ---------------- provisioning (SoftAP + UDP) ---------------- */

/* Minimal JSON string-field extractor - avoids a cJSON dependency
 * (IDF v6.1 no longer ships the standalone json component).
 * Handles standard \\ and \" escapes; plain-ASCII credentials expected. */
static bool json_get_str(const char *json, const char *key,
                         char *out, size_t out_len)
{
    char pattern[24];
    int n = snprintf(pattern, sizeof(pattern), "\"%s\"", key);
    if (n <= 0 || (size_t)n >= sizeof(pattern)) {
        return false;
    }
    const char *k = strstr(json, pattern);
    if (!k) {
        return false;
    }
    const char *v = strchr(k + n, ':');
    if (!v) {
        return false;
    }
    v++;
    while (*v == ' ' || *v == '\t') {
        v++;
    }
    if (*v != '"') {
        return false;
    }
    v++;

    size_t i = 0;
    while (*v && *v != '"' && i + 1 < out_len) {
        if (*v == '\\' && (v[1] == '"' || v[1] == '\\')) {
            v++;    /* keep next char literally */
        }
        out[i++] = *v++;
    }
    if (*v != '"') {
        return false;    /* unterminated value */
    }
    out[i] = '\0';
    return true;
}

static bool token_ok(const char *buf)
{
    if (!s_token_set) {
        return true;
    }
    char got[32];
    if (!json_get_str(buf, "token", got, sizeof(got))) {
        return false;
    }
    return strcmp(got, s_token) == 0;
}

static void ap_udp_server(void *arg)
{
    (void)arg;
    char buf[AP_CFG_BUF_LEN];
    char ssid[WIFI_MGR_SSID_LEN];
    char password[WIFI_MGR_PASS_LEN];

    int sock = socket(AF_INET, SOCK_DGRAM, IPPROTO_IP);
    if (sock < 0) {
        ESP_LOGE(TAG, "socket create failed");
        vTaskDelete(NULL);
        return;
    }

    struct sockaddr_in addr;
    memset(&addr, 0, sizeof(addr));
    addr.sin_family = AF_INET;
    addr.sin_port = htons(AP_UDP_PORT);
    addr.sin_addr.s_addr = htonl(INADDR_ANY);
    if (bind(sock, (struct sockaddr *)&addr, sizeof(addr)) < 0) {
        ESP_LOGE(TAG, "bind :%d failed", AP_UDP_PORT);
        close(sock);
        vTaskDelete(NULL);
        return;
    }
    ESP_LOGI(TAG, "udp config server on port %d", AP_UDP_PORT);

    for (;;) {
        struct sockaddr_in peer;
        socklen_t peer_len = sizeof(peer);
        int len = recvfrom(sock, buf, sizeof(buf) - 1, 0,
                           (struct sockaddr *)&peer, &peer_len);
        if (len <= 0) {
            continue;
        }
        buf[len] = '\0';
        ESP_LOGI(TAG, "cfg packet: %s", buf);

        if (!token_ok(buf)) {
            sendto(sock, s_reply_denied, sizeof(s_reply_denied) - 1, 0,
                   (struct sockaddr *)&peer, peer_len);
            continue;
        }
        if (!json_get_str(buf, "ssid", ssid, sizeof(ssid)) ||
            !json_get_str(buf, "password", password, sizeof(password)) ||
            ssid[0] == '\0' || strlen(ssid) > 32 ||
            strlen(password) > 63) {
            ESP_LOGW(TAG, "invalid cfg json");
            sendto(sock, s_reply_bad, sizeof(s_reply_bad) - 1, 0,
                   (struct sockaddr *)&peer, peer_len);
            continue;
        }
        if (nvs_save_creds(ssid, password) != ESP_OK) {
            ESP_LOGE(TAG, "nvs save failed");
            sendto(sock, s_reply_save_err, sizeof(s_reply_save_err) - 1, 0,
                   (struct sockaddr *)&peer, peer_len);
            continue;
        }

        ESP_LOGI(TAG, "credentials for \"%s\" saved, rebooting", ssid);
        sendto(sock, s_reply_ok, sizeof(s_reply_ok) - 1, 0,
               (struct sockaddr *)&peer, peer_len);
        vTaskDelay(pdMS_TO_TICKS(300));    /* let the reply leave the air */
        esp_restart();
    }
}

/* ---------------- lifecycle ---------------- */

esp_err_t wifi_manager_start(void)
{
    esp_err_t err = nvs_init_once();
    if (err != ESP_OK) {
        return err;
    }
    if (!s_event_group) {
        s_event_group = xEventGroupCreate();
    }

    /* AP SSID from softAP MAC: "XZS3-" + last 4 hex digits */
    uint8_t mac[6];
    ESP_ERROR_CHECK(esp_read_mac(mac, ESP_MAC_WIFI_SOFTAP));
    snprintf(s_ap_ssid, sizeof(s_ap_ssid), "%s%02X%02X",
             AP_SSID_PREFIX, mac[4], mac[5]);

    wifi_stack_init();
    if (!s_ap_netif) {
        s_ap_netif = esp_netif_create_default_wifi_ap();
    }

    esp_wifi_stop();
    s_provisioning = true;

    wifi_config_t cfg = { 0 };
    strlcpy((char *)cfg.ap.ssid, s_ap_ssid, sizeof(cfg.ap.ssid));
    cfg.ap.ssid_len = strlen(s_ap_ssid);
    cfg.ap.channel = 6;       /* 信道 6 比 1 更可靠（中国法规允许 1-11） */
    cfg.ap.max_connection = 4;
    cfg.ap.authmode = WIFI_AUTH_OPEN;
    cfg.ap.ssid_hidden = 0;   /* 确保 SSID 广播开启 */

    ESP_ERROR_CHECK(esp_wifi_set_mode(WIFI_MODE_AP));
    ESP_ERROR_CHECK(esp_wifi_set_protocol(WIFI_IF_AP,
                     WIFI_PROTOCOL_11B | WIFI_PROTOCOL_11G | WIFI_PROTOCOL_11N));
    ESP_ERROR_CHECK(esp_wifi_set_channel(cfg.ap.channel, WIFI_SECOND_CHAN_NONE));
    ESP_ERROR_CHECK(esp_wifi_set_config(WIFI_IF_AP, &cfg));
    ESP_ERROR_CHECK(esp_wifi_start());

    ESP_LOGI(TAG, "provisioning AP \"%s\" (open), udp cfg on :%d, "
             "gw 192.168.4.1", s_ap_ssid, AP_UDP_PORT);

    if (!s_ap_task) {
        xTaskCreate(ap_udp_server, "wifi_cfg", 4096, NULL, 5, &s_ap_task);
    }
    return ESP_OK;
}

void wifi_manager_stop(void)
{
    if (s_ap_task) {
        vTaskDelete(s_ap_task);
        s_ap_task = NULL;
    }
    s_sta_active = false;
    s_provisioning = false;

    if (s_stack_inited) {
        esp_wifi_stop();
        if (s_wifi_ev) {
            esp_event_handler_instance_unregister(
                WIFI_EVENT, ESP_EVENT_ANY_ID, s_wifi_ev);
            s_wifi_ev = NULL;
        }
        if (s_ip_ev) {
            esp_event_handler_instance_unregister(
                IP_EVENT, IP_EVENT_STA_GOT_IP, s_ip_ev);
            s_ip_ev = NULL;
        }
        esp_wifi_deinit();
        s_stack_inited = false;
    }

    if (s_ap_netif) {
        esp_netif_destroy_default_wifi(s_ap_netif);
        s_ap_netif = NULL;
    }
    if (s_sta_netif) {
        esp_netif_destroy_default_wifi(s_sta_netif);
        s_sta_netif = NULL;
    }
    if (s_event_group) {
        vEventGroupDelete(s_event_group);
        s_event_group = NULL;
    }
    ESP_LOGI(TAG, "stopped");
}

void wifi_manager_forget(void)
{
    nvs_handle_t handle;
    if (nvs_open(NVS_NAMESPACE, NVS_READWRITE, &handle) == ESP_OK) {
        nvs_erase_all(handle);
        nvs_commit(handle);
        nvs_close(handle);
    }
    ESP_LOGW(TAG, "credentials erased, rebooting into provisioning");
    vTaskDelay(pdMS_TO_TICKS(100));
    esp_restart();
}

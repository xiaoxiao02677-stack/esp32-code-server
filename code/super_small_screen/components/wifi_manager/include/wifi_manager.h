#pragma once

/*
 * wifi_manager - minimal WiFi provisioning + STA manager for super_small_screen
 * (ESP32-S3, 0.42" SSD1306 72x40, 4MB flash, size-optimized build)
 *
 * NVS layout (namespace "wifi"):
 *   "ssid"     string  station SSID
 *   "password" string  station password
 *
 * Typical main flow:
 *   if (!wifi_manager_has_credentials()) {       // cheap NVS probe
 *       wifi_manager_start();                    // AP "XZS3-XXXX" + UDP :5555
 *       ... poll get_state()==SMARTCONFIG_MODE, show AP SSID ...
 *       // module reboots itself once creds are saved via UDP
 *   } else {
 *       wifi_connect_sta();                      // blocking, 15s timeout
 *       // fail -> call again later (idempotent)
 *   }
 *
 * Provisioning protocol (UDP 5555, phone on the AP, 192.168.4.1):
 *   send: {"ssid":"mywifi","password":"secret"[,"token":"xxxx"]}
 *   recv: {"success":true,"msg":"saved, rebooting"}   then chip reboots
 *   err : {"success":false,"msg":"bad json|bad token|nvs save failed"}
 *   (token only checked if wifi_manager_set_token() was called)
 *
 * No HTTP WebServer / DNS / SmartConfig - keeps the app small.
 */

#include <stdbool.h>
#include <stddef.h>
#include "esp_err.h"

#ifdef __cplusplus
extern "C" {
#endif

typedef enum {
    WIFI_STATE_IDLE = 0,         /* not started */
    WIFI_STATE_CONNECTING,       /* STA connecting (incl. auto-reconnect) */
    WIFI_STATE_CONNECTED,        /* STA connected + got IP */
    WIFI_STATE_SMARTCONFIG_MODE, /* provisioning: SoftAP + UDP 5555 up */
} wifi_state_t;

#define WIFI_MGR_AP_SSID_LEN 16
#define WIFI_MGR_SSID_LEN    33
#define WIFI_MGR_PASS_LEN    65

/* Quick NVS probe: true if a station SSID is stored.
 * Initializes NVS if needed; never touches the WiFi driver. */
bool wifi_manager_has_credentials(void);

/* Start provisioning: SoftAP "XZS3-XXXX" (XXXX = last 4 hex of AP MAC,
 * open network) + UDP config server on port 5555.
 * Blocks until AP+UDP are up, then returns (server runs in its own task).
 * After credentials are saved the module reboots itself. */
esp_err_t wifi_manager_start(void);

/* Blocking STA connect using stored credentials (15s timeout).
 * Idempotent: safe to call again after failure (30s retry loop).
 * On success the event handler auto-reconnects on drops. */
esp_err_t wifi_connect_sta(void);

/* Tear everything down (rarely needed; module normally reboots instead). */
void wifi_manager_stop(void);

/* Current state. Safe from any task. */
wifi_state_t wifi_manager_get_state(void);

/* Provisioning AP SSID ("XZS3-XXXX"). Valid after wifi_manager_start(). */
const char *wifi_manager_get_ap_ssid(void);

/* Stored/connected station SSID ("" if none). */
const char *wifi_manager_get_sta_ssid(void);

/* Station IP string ("192.168.x.x"), "" if not connected. */
const char *wifi_manager_get_ip(void);

/* Optional shared secret: when set (non-NULL), UDP requests must carry a
 * matching "token" field. Call BEFORE wifi_manager_start(). Max 31 bytes. */
void wifi_manager_set_token(const char *token);

/* Erase credentials and reboot into provisioning mode. */
void wifi_manager_forget(void);

#ifdef __cplusplus
}
#endif

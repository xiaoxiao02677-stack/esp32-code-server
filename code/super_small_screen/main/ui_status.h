/*
 * ui_status.h - OLED status screens (72x40, 5x7 font) for super_small_screen.
 *
 * All screens clear the local framebuffer, draw and push one refresh over
 * I2C. Pure ASCII only (font has 32..126).
 */
#ifndef UI_STATUS_H
#define UI_STATUS_H

#ifdef __cplusplus
extern "C" {
#endif

/* No stored WiFi credentials -> AP mode provisioning.
 * Line 1: "WiFi CFG", line 2: SSID (truncated to 12 chars + "..." if long). */
void ui_show_wifi_config(const char *ssid);

/* Connecting to WiFi / server with stored credentials. */
void ui_show_connecting(void);

/* Big-eye "CCC" splash: one huge 3x scale eye per page, server connected. */
void ui_show_ccc(void);

/* Default idle screen (connection/server failed) - same layout as boot. */
void ui_show_hello_world(void);

/* OTA / device config sync in progress. */
void ui_show_sync(void);

/* Rebooting after provisioning saved new credentials. */
void ui_show_reboot(void);

/* Generic two-line screen, both lines centered (max ~12 chars per line,
 * NULL line keeps the page blank). */
void ui_show_text(const char *line1, const char *line2);

#ifdef __cplusplus
}
#endif

#endif /* UI_STATUS_H */

/*
 * wifi_bridge.h - C 桥接层：把小圆屏的 C++ WifiManager（78/esp-wifi-connect）
 * 配网组件封装成 C API，供 main.c 调用。
 *
 * 配网模式（热点 + 网页）：
 *   wifi_bridge_start_config_ap() -> 热点 "XZS3-XXXX"（开放，192.168.4.1）
 *   手机连热点自动弹配网页 -> 提交 WiFi -> 验证连接成功 -> 存 NVS -> 网页 /exit
 *   -> CONFIG_MODE_EXIT 事件 -> main 调 wifi_bridge_start_station() 连保存的 WiFi
 *   -> CONNECTED 事件
 */
#ifndef WIFI_BRIDGE_H
#define WIFI_BRIDGE_H

#include <stdbool.h>

#include "esp_err.h"

#ifdef __cplusplus
extern "C" {
#endif

/* 转发自 WifiManager 的事件（Scanning/Connecting 不转发） */
typedef enum {
    WIFI_BRIDGE_EVENT_CONFIG_MODE_ENTER = 0, /* 配网热点已启动 */
    WIFI_BRIDGE_EVENT_CONFIG_MODE_EXIT,      /* 配网模式退出（网页/exit 或超时） */
    WIFI_BRIDGE_EVENT_CONNECTED,             /* STA 连上 WiFi（data=ssid） */
    WIFI_BRIDGE_EVENT_DISCONNECTED,          /* STA 断开（data=reason） */
} wifi_bridge_event_t;

typedef void (*wifi_bridge_event_cb_t)(wifi_bridge_event_t ev, const char *data);

/* 初始化 WifiManager（NVS/netif/事件循环/wifi 驱动，幂等）。
 * ssid_prefix 为热点名前缀（建议 ASCII，OLED 只能显示 ASCII）；
 * language 为配网页语言（"zh-CN" 等）。返回 ESP_OK/ESP_FAIL。 */
esp_err_t wifi_bridge_init(const char *ssid_prefix, const char *language);

/* 注册事件回调（内部转发到 WifiManager）。回调在 WiFi 事件任务上下文，
 * 不要做阻塞操作；data 指针仅回调内有效。 */
void wifi_bridge_set_event_callback(wifi_bridge_event_cb_t cb);

/* 启动配网热点（非阻塞；自动停掉 STA） */
void wifi_bridge_start_config_ap(void);

/* 用已保存的 SSID 列表连接 STA（非阻塞；自动停掉热点） */
void wifi_bridge_start_station(void);

/* 配网热点 SSID（如 "XZS3-1234"），非配网模式返回 ""。线程安全。 */
const char *wifi_bridge_get_ap_ssid(void);

/* 配网页 URL（"http://192.168.4.1"），非配网模式返回 ""。线程安全。 */
const char *wifi_bridge_get_ap_url(void);

/* 设置 WiFi 发射功率上限（单位 dBm，可选档位 2/5/7/8/11/13/14/15/16/18/20，
 * 无精确档的值自动吸附到最近档并打 WARN）。
 * 按 esp_wifi.h 官方档位表换算 set 值（如 8dBm→34，非简单 ×4），
 * 并把 NVS "max_tx_power" 一并写入，防止配网页高级设置里的旧值
 * 在下次启动时回读覆盖。需在 WiFi 启动后调用（如 StartConfigAp 之后）。 */
esp_err_t wifi_bridge_set_tx_power_dbm(int8_t dbm);

/* 是否处于配网模式 */
bool wifi_bridge_is_config_mode(void);

/* STA 是否已连接（有 IP） */
bool wifi_bridge_is_connected(void);

/* STA 的 IP 字符串，未连接返回 ""。线程安全。 */
const char *wifi_bridge_get_ip(void);

#ifdef __cplusplus
}
#endif

#endif /* WIFI_BRIDGE_H */

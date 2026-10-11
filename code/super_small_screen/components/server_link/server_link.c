/*
 * server_link.c - 精简 WebSocket 客户端 + 服务器配置同步
 *
 * 参考 xiaozhi-esp32 的 websocket_protocol.cc hello 流程：
 *   连接 → 发 hello（audio_params 占位）→ 收服务器 hello（握手完成）
 *   → 收 device_config（配置同步完成，回调上层）
 *
 * 精简原则：无 opus/音频编解码；2KB 接收缓冲；静态缓冲；
 * 连接失败自动重试（SERVER_LINK_MAX_RETRIES 次，间隔 5s）后报 FAILED。
 */
#include "server_link.h"

#include <stddef.h>
#include <string.h>

#include "freertos/FreeRTOS.h"
#include "freertos/event_groups.h"
#include "freertos/semphr.h"
#include "freertos/task.h"

#include "esp_event.h"
#include "esp_log.h"
#include "esp_websocket_client.h"
#include "cJSON.h"
#include "nvs.h"
#include "nvs_flash.h"

static const char *TAG = "server_link";

/* 内部事件位 */
#define EV_CONNECT (1UL << 0) /* WS 连接建立 */
#define EV_FAIL (1UL << 1)    /* 断线/错误 */
#define EV_HELLO (1UL << 2)   /* 收到服务器 hello */
#define EV_STOP (1UL << 3)    /* 请求停止 */
#define EV_DONE (1UL << 4)    /* 任务已退出 */
#define EV_ALL (EV_CONNECT | EV_FAIL | EV_HELLO | EV_STOP | EV_DONE)

/* 连接失败自动重试 3 次（首次失败后再试 3 次，共最多 4 次尝试） */
#define SERVER_LINK_MAX_RETRIES 3
#define SERVER_LINK_RETRY_INTERVAL_MS 5000
#define SERVER_LINK_CONNECT_TIMEOUT_MS 15000
#define SERVER_LINK_HELLO_TIMEOUT_MS 10000
#define SERVER_LINK_SEND_TIMEOUT_MS 5000

/* 客户端 hello 报文（audio_params 为占位：本板无音频硬件，
 * 上线后接入编解码器时按实际能力修改） */
static const char SERVER_LINK_HELLO_JSON[] =
    "{\"type\":\"hello\",\"version\":1,\"transport\":\"websocket\","
    "\"audio_params\":{\"format\":\"opus\",\"sample_rate\":16000,"
    "\"channels\":1,\"frame_duration\":60}}";

static char s_url[128];
static volatile int s_state = SERVER_LINK_STATE_IDLE;
static volatile bool s_stopping;
static bool s_cfg_valid; /* 是否已收到过 device_config */
static EventGroupHandle_t s_events;
static SemaphoreHandle_t s_cfg_mutex;
static TaskHandle_t s_task;
static esp_websocket_client_handle_t s_client; /* 仅 server_link 任务持有/销毁 */
static device_config_t s_cfg;
static device_config_t s_cb_cfg; /* 回调快照（ws 任务内串行使用） */
static server_link_on_config_cb_t s_on_config;
static server_link_on_audio_cb_t s_on_audio;
static char s_rx_buf[SERVER_LINK_RX_BUF_SIZE + 1];
static int s_rx_len;

static void set_state(int state) {
    if (state != s_state) {
        ESP_LOGI(TAG, "state: %d -> %d", s_state, state);
        s_state = state;
    }
}

static void copy_str(char *dst, size_t dst_size, const char *src) {
    if (src == NULL) {
        dst[0] = '\0';
        return;
    }
    strlcpy(dst, src, dst_size);
}

/* 整数 + 范围校验（拒绝小数/越界，参考 board.cc 的 volume/brightness 校验） */
static bool get_int_in_range(const cJSON *obj, const char *key, int lo, int hi, int *out) {
    const cJSON *item = cJSON_GetObjectItem(obj, key);
    if (!cJSON_IsNumber(item)) {
        return false;
    }
    double value = item->valuedouble;
    if (value != (double)(long long)value || value < (double)lo || value > (double)hi) {
        ESP_LOGW(TAG, "ignore out-of-range %s: %.1f", key, value);
        return false;
    }
    *out = (int)value;
    return true;
}

static void cfg_defaults(device_config_t *cfg) {
    memset(cfg, 0, sizeof(*cfg));
    cfg->volume = -1;
    cfg->brightness = -1;
    /* 预留字段默认 -1（上线后实现，当前不消费） */
    cfg->speaker_volume = -1;
    cfg->mic_gain = -1;
}

/* —— 消息处理（均在 ws 客户端任务上下文调用）—— */

static void handle_server_hello(const cJSON *root) {
    const cJSON *session_id = cJSON_GetObjectItem(root, "session_id");
    if (xSemaphoreTake(s_cfg_mutex, pdMS_TO_TICKS(100)) == pdTRUE) {
        if (cJSON_IsString(session_id)) {
            copy_str(s_cfg.session_id, sizeof(s_cfg.session_id), session_id->valuestring);
        } else {
            ESP_LOGW(TAG, "server hello has no session_id");
        }
        s_cb_cfg = s_cfg;
        xSemaphoreGive(s_cfg_mutex);

        set_state(SERVER_LINK_STATE_CONNECTED);
        xEventGroupSetBits(s_events, EV_HELLO);
        /* 先释放锁再回调，允许回调内调用 server_link_get_config() */
        if (s_on_config != NULL) {
            s_on_config(&s_cb_cfg);
        }
    } else {
        ESP_LOGE(TAG, "cfg mutex timeout on server hello");
    }
}

static void handle_device_config(const cJSON *root) {
    const cJSON *payload = cJSON_GetObjectItem(root, "payload");
    if (!cJSON_IsObject(payload)) {
        ESP_LOGW(TAG, "invalid device_config: missing payload object");
        return;
    }

    if (xSemaphoreTake(s_cfg_mutex, pdMS_TO_TICKS(100)) != pdTRUE) {
        ESP_LOGE(TAG, "cfg mutex timeout on device_config");
        return;
    }

    /* —— 当前消费字段 —— */
    get_int_in_range(payload, "volume", 0, 100, &s_cfg.volume);
    get_int_in_range(payload, "brightness", 0, 100, &s_cfg.brightness);

    /* wake_word：字符串或字符串数组（取首个非空词），缺省不动 */
    const cJSON *wake_word = cJSON_GetObjectItem(payload, "wake_word");
    if (cJSON_IsString(wake_word)) {
        copy_str(s_cfg.wake_word, sizeof(s_cfg.wake_word), wake_word->valuestring);
    } else if (cJSON_IsArray(wake_word)) {
        const cJSON *item = NULL;
        cJSON_ArrayForEach(item, wake_word) {
            if (cJSON_IsString(item) && item->valuestring[0] != '\0') {
                copy_str(s_cfg.wake_word, sizeof(s_cfg.wake_word), item->valuestring);
                break;
            }
        }
    }

    /* —— 预留字段（上线后实现，当前仅解析存储、上层不消费）——
     * 格式假设：嵌套 {"speaker":{"volume","type"},"microphone":{"gain","type"}}，
     * 兼容平铺 {"speaker_volume","speaker_type","mic_gain","mic_type"} */
    const cJSON *speaker = cJSON_GetObjectItem(payload, "speaker");
    if (cJSON_IsObject(speaker)) {
        get_int_in_range(speaker, "volume", 0, 100, &s_cfg.speaker_volume);
        const cJSON *type = cJSON_GetObjectItem(speaker, "type");
        if (cJSON_IsString(type)) {
            copy_str(s_cfg.speaker_type, sizeof(s_cfg.speaker_type), type->valuestring);
        }
    } else {
        get_int_in_range(payload, "speaker_volume", 0, 100, &s_cfg.speaker_volume);
        const cJSON *type = cJSON_GetObjectItem(payload, "speaker_type");
        if (cJSON_IsString(type)) {
            copy_str(s_cfg.speaker_type, sizeof(s_cfg.speaker_type), type->valuestring);
        }
    }
    const cJSON *microphone = cJSON_GetObjectItem(payload, "microphone");
    if (cJSON_IsObject(microphone)) {
        get_int_in_range(microphone, "gain", 0, 100, &s_cfg.mic_gain);
        const cJSON *type = cJSON_GetObjectItem(microphone, "type");
        if (cJSON_IsString(type)) {
            copy_str(s_cfg.mic_type, sizeof(s_cfg.mic_type), type->valuestring);
        }
    } else {
        get_int_in_range(payload, "mic_gain", 0, 100, &s_cfg.mic_gain);
        const cJSON *type = cJSON_GetObjectItem(payload, "mic_type");
        if (cJSON_IsString(type)) {
            copy_str(s_cfg.mic_type, sizeof(s_cfg.mic_type), type->valuestring);
        }
    }

    s_cb_cfg = s_cfg;
    xSemaphoreGive(s_cfg_mutex);

    s_cfg_valid = true;
    set_state(SERVER_LINK_STATE_CONFIG_RECEIVED);
    ESP_LOGI(TAG, "device_config synced: vol=%d bri=%d wake=%s session=%s",
             s_cb_cfg.volume, s_cb_cfg.brightness, s_cb_cfg.wake_word, s_cb_cfg.session_id);
    if (s_on_config != NULL) {
        s_on_config(&s_cb_cfg);
    }
}

static void process_text_message(const char *data, int len) {
    cJSON *root = cJSON_ParseWithLength(data, (size_t)len);
    if (root == NULL) {
        ESP_LOGE(TAG, "JSON parse failed (%d bytes)", len);
        return;
    }
    const cJSON *type = cJSON_GetObjectItem(root, "type");
    if (cJSON_IsString(type)) {
        if (strcmp(type->valuestring, "hello") == 0) {
            handle_server_hello(root);
        } else if (strcmp(type->valuestring, "device_config") == 0) {
            handle_device_config(root);
        } else {
            ESP_LOGD(TAG, "ignore message type: %s", type->valuestring);
        }
    } else {
        ESP_LOGW(TAG, "message without type field");
    }
    cJSON_Delete(root);
}

static void handle_ws_data(esp_websocket_event_data_t *event) {
    /* 二进制帧：音频预留（上线后实现——由上层喂给编解码器/扬声器） */
    if (event->op_code == 0x02) {
        if (s_on_audio != NULL) {
            s_on_audio((const uint8_t *)event->data_ptr, (size_t)event->data_len);
        }
        return;
    }
    /* 仅处理文本帧（0x01）及其分片（0x00），控制帧由客户端内部处理 */
    if (event->op_code != 0x01 && event->op_code != 0x00) {
        return;
    }
    if (event->payload_offset == 0) {
        s_rx_len = 0;
    }
    if (s_rx_len + event->data_len > (int)sizeof(s_rx_buf) - 1) {
        ESP_LOGW(TAG, "drop overlong message (%d+%d bytes)", s_rx_len, event->data_len);
        s_rx_len = 0;
        return;
    }
    memcpy(&s_rx_buf[s_rx_len], event->data_ptr, (size_t)event->data_len);
    s_rx_len += event->data_len;
    if (s_rx_len < event->payload_len) {
        return; /* 等待后续分片 */
    }
    s_rx_buf[s_rx_len] = '\0';
    int len = s_rx_len;
    s_rx_len = 0;
    process_text_message(s_rx_buf, len);
}

static void ws_event_handler(void *handler_arg, esp_event_base_t base, int32_t event_id, void *event_data) {
    (void)handler_arg;
    (void)base;
    esp_websocket_event_data_t *event = (esp_websocket_event_data_t *)event_data;
    switch (event_id) {
        case WEBSOCKET_EVENT_CONNECTED:
            xEventGroupSetBits(s_events, EV_CONNECT);
            break;
        case WEBSOCKET_EVENT_DISCONNECTED:
        case WEBSOCKET_EVENT_ERROR:
            if (s_state == SERVER_LINK_STATE_CONNECTED || s_state == SERVER_LINK_STATE_CONFIG_RECEIVED) {
                set_state(SERVER_LINK_STATE_CONNECTING); /* 掉线后走重连周期 */
            }
            xEventGroupSetBits(s_events, EV_FAIL);
            break;
        case WEBSOCKET_EVENT_DATA:
            handle_ws_data(event);
            break;
        default:
            break;
    }
}

static void destroy_client(void) {
    if (s_client != NULL) {
        esp_websocket_client_stop(s_client);
        esp_websocket_client_destroy(s_client);
        s_client = NULL;
    }
    s_rx_len = 0;
}

/* 单次连接尝试：连接 → 发 hello → 等服务器 hello。
 * 返回 0 成功；-1 失败（可重试）；-2 收到停止请求。 */
static int connect_once(void) {
    esp_websocket_client_config_t ws_cfg = {
        .uri = s_url,
        .buffer_size = SERVER_LINK_RX_BUF_SIZE,
        .disable_auto_reconnect = true, /* 重试由本模块计数控制 */
        .network_timeout_ms = 10000,
    };
    s_client = esp_websocket_client_init(&ws_cfg);
    if (s_client == NULL) {
        ESP_LOGE(TAG, "websocket client init failed");
        return -1;
    }
    esp_websocket_register_events(s_client, WEBSOCKET_EVENT_ANY, ws_event_handler, NULL);
    if (esp_websocket_client_start(s_client) != ESP_OK) {
        ESP_LOGE(TAG, "websocket client start failed");
        destroy_client();
        return -1;
    }

    EventBits_t bits = xEventGroupWaitBits(s_events, EV_CONNECT | EV_FAIL | EV_STOP,
                                           pdFALSE, pdFALSE,
                                           pdMS_TO_TICKS(SERVER_LINK_CONNECT_TIMEOUT_MS));
    if (bits & EV_STOP) {
        return -2;
    }
    if (!(bits & EV_CONNECT)) {
        ESP_LOGW(TAG, "connect timeout/fail: %s", s_url);
        destroy_client();
        return -1;
    }

    /* 先清握手相关事件位再发 hello：避免"服务器 hello 已到但被清除"的竞态 */
    xEventGroupClearBits(s_events, EV_HELLO | EV_FAIL);
    int sent = esp_websocket_client_send_text(s_client, SERVER_LINK_HELLO_JSON,
                                              sizeof(SERVER_LINK_HELLO_JSON) - 1,
                                              pdMS_TO_TICKS(SERVER_LINK_SEND_TIMEOUT_MS));
    if (sent < 0) {
        ESP_LOGE(TAG, "send hello failed");
        destroy_client();
        return -1;
    }

    bits = xEventGroupWaitBits(s_events, EV_HELLO | EV_FAIL | EV_STOP,
                               pdFALSE, pdFALSE,
                               pdMS_TO_TICKS(SERVER_LINK_HELLO_TIMEOUT_MS));
    if (bits & EV_STOP) {
        return -2;
    }
    if (bits & EV_HELLO) {
        return 0; /* 握手成功（状态已置 CONNECTED） */
    }
    ESP_LOGW(TAG, "server hello timeout");
    destroy_client();
    return -1;
}

static void server_link_task(void *arg) {
    (void)arg;
    int retries = 0;
    while (!s_stopping) {
        xEventGroupClearBits(s_events, EV_CONNECT | EV_FAIL | EV_HELLO);
        int rc = connect_once();
        if (rc == -2) {
            break;
        }
        if (rc != 0) {
            if (retries >= SERVER_LINK_MAX_RETRIES) {
                ESP_LOGE(TAG, "connect failed after %d retries, giving up", retries);
                set_state(SERVER_LINK_STATE_FAILED);
                break;
            }
            retries++;
            ESP_LOGW(TAG, "retry %d/%d in %d ms", retries, SERVER_LINK_MAX_RETRIES,
                     SERVER_LINK_RETRY_INTERVAL_MS);
            EventBits_t bits = xEventGroupWaitBits(s_events, EV_STOP, pdFALSE, pdFALSE,
                                                   pdMS_TO_TICKS(SERVER_LINK_RETRY_INTERVAL_MS));
            if (bits & EV_STOP) {
                break;
            }
            continue;
        }
        /* 握手成功：重置重试计数，等待断线或停止 */
        retries = 0;
        EventBits_t bits = xEventGroupWaitBits(s_events, EV_FAIL | EV_STOP,
                                               pdFALSE, pdFALSE, portMAX_DELAY);
        if (bits & EV_STOP) {
            break;
        }
        ESP_LOGW(TAG, "connection lost, reconnecting");
        set_state(SERVER_LINK_STATE_CONNECTING);
        destroy_client();
    }
    destroy_client();
    s_task = NULL;
    xEventGroupSetBits(s_events, EV_DONE);
    vTaskDelete(NULL);
}

/* —— 公开 API —— */

int server_link_start(void) {
    if (s_task != NULL) {
        return -1; /* 已在运行 */
    }
    if (s_events == NULL) {
        s_events = xEventGroupCreate();
        if (s_events == NULL) {
            return -2;
        }
    }
    if (s_cfg_mutex == NULL) {
        s_cfg_mutex = xSemaphoreCreateMutex();
        if (s_cfg_mutex == NULL) {
            return -2;
        }
    }

    /* URL 优先级：NVS("server","url") > SERVER_WS_URL 宏 */
    strlcpy(s_url, SERVER_WS_URL, sizeof(s_url));
    esp_err_t err = nvs_flash_init();
    if (err != ESP_OK && err != ESP_ERR_INVALID_STATE) {
        ESP_LOGW(TAG, "nvs_flash_init: %s (use default url)", esp_err_to_name(err));
    } else {
        nvs_handle_t handle;
        if (nvs_open("server", NVS_READONLY, &handle) == ESP_OK) {
            size_t len = sizeof(s_url);
            if (nvs_get_str(handle, "url", s_url, &len) == ESP_OK) {
                ESP_LOGI(TAG, "WS url from NVS: %s", s_url);
            }
            nvs_close(handle);
        }
    }

    /* esp_websocket_client 依赖默认事件循环；wifi 模块已创建则忽略 */
    err = esp_event_loop_create_default();
    if (err != ESP_OK && err != ESP_ERR_INVALID_STATE) {
        ESP_LOGW(TAG, "event loop: %s", esp_err_to_name(err));
    }

    /* 复位配置（回调注册关系保留） */
    if (xSemaphoreTake(s_cfg_mutex, portMAX_DELAY) == pdTRUE) {
        cfg_defaults(&s_cfg);
        xSemaphoreGive(s_cfg_mutex);
    }
    s_cfg_valid = false;
    s_rx_len = 0;
    s_stopping = false;
    xEventGroupClearBits(s_events, EV_ALL);
    set_state(SERVER_LINK_STATE_CONNECTING);

    if (xTaskCreate(server_link_task, "server_link", 4096, NULL, 5, (TaskHandle_t *)&s_task) != pdPASS) {
        s_task = NULL;
        set_state(SERVER_LINK_STATE_IDLE);
        return -2;
    }
    return 0;
}

void server_link_stop(void) {
    if (s_task == NULL) {
        if (s_state == SERVER_LINK_STATE_FAILED) {
            set_state(SERVER_LINK_STATE_IDLE);
        }
        return;
    }
    s_stopping = true;
    xEventGroupSetBits(s_events, EV_STOP);
    xEventGroupWaitBits(s_events, EV_DONE, pdFALSE, pdFALSE, pdMS_TO_TICKS(3000));
    xEventGroupClearBits(s_events, EV_ALL);
    s_stopping = false;
    set_state(SERVER_LINK_STATE_IDLE);
}

int server_link_get_state(void) {
    return s_state;
}

int server_link_get_config(device_config_t *out_cfg) {
    if (out_cfg == NULL || !s_cfg_valid) {
        return -1;
    }
    if (xSemaphoreTake(s_cfg_mutex, pdMS_TO_TICKS(100)) != pdTRUE) {
        return -1;
    }
    *out_cfg = s_cfg;
    xSemaphoreGive(s_cfg_mutex);
    return 0;
}

void server_link_set_on_config(server_link_on_config_cb_t cb) {
    s_on_config = cb;
}

/* —— 音频接口预留（上线后实现，当前空实现）—— */

int server_link_send_audio(const uint8_t *data, size_t len) {
    /* 上线后实现：接入音频编解码器后，把麦克风采集的 opus 帧
     * （16kHz/单声道/60ms）经 esp_websocket_client_send_bin() 二进制发送。
     * 本板当前无音频硬件，直接拒绝。 */
    (void)data;
    (void)len;
    return -1;
}

void server_link_set_on_audio(server_link_on_audio_cb_t cb) {
    /* 上线后实现：注册后服务器下发的二进制音频帧将透传给该回调，
     * 由上层解码后送扬声器播放。当前仅保存注册。 */
    s_on_audio = cb;
}

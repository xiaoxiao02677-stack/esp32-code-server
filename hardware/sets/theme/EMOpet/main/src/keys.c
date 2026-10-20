/* ============================================================
 * keys.c — 三键（BOOT / VOL+ / VOL-）状态机
 * 5ms 扫描 + 软件消抖，识别 单击 / 双击 / 长按 / 双键同按
 * 不依赖任何外部 button 组件，跨 IDF 版本最稳
 * ============================================================ */
#include <string.h>
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "esp_err.h"
#include "driver/gpio.h"
#include "esp_timer.h"
#include "esp_log.h"
#include "app_config.h"
#include "emopet_ui.h"

static const char *TAG = "keys";

#define SCAN_MS           5
#define DEBOUNCE_CNT      3        /* 15ms 消抖 */
#define TAP_MAX_MS        250      /* 短按时长上限 */
#define LONG_MS           2000     /* BOOT 长按 */
#define VOL_LONG_MS       1000     /* VOL 长按 */
#define DBL_GAP_MS        300      /* 双击间隔 */
#define BOTH_HOLD_MS      500      /* 双键同按 */

typedef struct {
    int      gpio;
    bool     raw;
    bool     stable;
    uint8_t  cnt;
    int64_t  down_ms;
    bool     is_down;
    bool     long_fired;
    int64_t  last_tap_ms;
    bool     pending_tap;
} key_t;

static key_t s_boot, s_vup, s_vdn;
static key_cb_t s_cb = NULL;
static bool s_enabled = true;

static int64_t now_ms(void) { return (int64_t)(esp_timer_get_time() / 1000); }

static bool read_level(int gpio)
{
    int l = gpio_get_level(gpio);
#if CONFIG_KEY_ACTIVE_LOW
    return l == 0;
#else
    return l != 0;
#endif
}

static void key_init_one(key_t *k, int gpio)
{
    memset(k, 0, sizeof(*k));
    k->gpio = gpio;
}

static void emit(key_event_t e)
{
    if (s_cb && s_enabled) s_cb(e);
}

/* 返回本次扫描产生的事件（若有） */
static void key_scan(key_t *k, key_event_t tap_evt, key_event_t long_evt, int long_ms)
{
    bool raw = read_level(k->gpio);
    if (raw != k->raw) { k->raw = raw; k->cnt = 0; }
    else if (k->cnt < DEBOUNCE_CNT) k->cnt++;

    if (k->cnt < DEBOUNCE_CNT) return;
    bool st = k->raw;

    if (st && !k->is_down) {                     /* 按下 */
        k->is_down = true;
        k->down_ms = now_ms();
        k->long_fired = false;
        return;
    }
    if (st && k->is_down) {                      /* 持续按住 */
        if (!k->long_fired && (now_ms() - k->down_ms) >= long_ms) {
            k->long_fired = true;
            emit(long_evt);
        }
        return;
    }
    if (!st && k->is_down) {                     /* 释放 */
        int64_t dur = now_ms() - k->down_ms;
        k->is_down = false;
        if (k->long_fired) { k->pending_tap = false; return; }
        if (dur > TAP_MAX_MS) return;            /* 中等时长：不响应 */

        /* 双击判定 */
        if (tap_evt == KEY_EVT_BOOT_SINGLE && k->pending_tap &&
            (now_ms() - k->last_tap_ms) <= DBL_GAP_MS) {
            k->pending_tap = false;
            emit(KEY_EVT_BOOT_DOUBLE);
            return;
        }
        k->last_tap_ms = now_ms();
        if (tap_evt == KEY_EVT_BOOT_SINGLE) { k->pending_tap = true; return; }
        emit(tap_evt);
    }

    /* 待定单击超时 → 补发单击 */
    if (k->pending_tap && (now_ms() - k->last_tap_ms) > DBL_GAP_MS) {
        k->pending_tap = false;
        emit(tap_evt);
    }
}

static void keys_task(void *arg)
{
    (void)arg;
    static int64_t both_ms = -1;
    while (1) {
        key_scan(&s_boot, KEY_EVT_BOOT_SINGLE,   KEY_EVT_BOOT_LONG,   LONG_MS);
        key_scan(&s_vup,  KEY_EVT_VOLUP_SINGLE,  KEY_EVT_VOLUP_LONG,  VOL_LONG_MS);
        key_scan(&s_vdn,  KEY_EVT_VOLDN_SINGLE,  KEY_EVT_VOLDN_LONG,  VOL_LONG_MS);

        /* VOL+ 与 VOL- 同按 */
        bool both = s_vup.is_down && s_vdn.is_down;
        if (both) {
            if (both_ms < 0) both_ms = now_ms();
            else if (now_ms() - both_ms >= BOTH_HOLD_MS) {
                emit(KEY_EVT_BOTH_VOL);
                s_vup.long_fired = s_vdn.long_fired = true;  /* 抑制后续单击 */
                both_ms = -1;
            }
        } else {
            both_ms = -1;
        }

        vTaskDelay(pdMS_TO_TICKS(SCAN_MS));
    }
}

void keys_init(key_cb_t cb)
{
    s_cb = cb;

    gpio_config_t io = {
        .mode = GPIO_MODE_INPUT,
        .pull_up_en = GPIO_PULLUP_ENABLE,
        .pull_down_en = GPIO_PULLDOWN_DISABLE,
        .intr_type = GPIO_INTR_DISABLE,
        .pin_bit_mask = (1ULL << CONFIG_KEY_BOOT_GPIO) |
                        (1ULL << CONFIG_KEY_VOLUP_GPIO) |
                        (1ULL << CONFIG_KEY_VOLDN_GPIO),
    };
    ESP_ERROR_CHECK(gpio_config(&io));

    key_init_one(&s_boot, CONFIG_KEY_BOOT_GPIO);
    key_init_one(&s_vup,  CONFIG_KEY_VOLUP_GPIO);
    key_init_one(&s_vdn,  CONFIG_KEY_VOLDN_GPIO);

    xTaskCreatePinnedToCore(keys_task, "keys", 3072, NULL, 5, NULL, 1);
    ESP_LOGI(TAG, "keys ready: BOOT=%d VOL+=%d VOL-=%d",
             CONFIG_KEY_BOOT_GPIO, CONFIG_KEY_VOLUP_GPIO, CONFIG_KEY_VOLDN_GPIO);
}

void keys_set_enabled(bool en) { s_enabled = en; }

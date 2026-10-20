#pragma once
#include "app_config.h"
#include "lvgl.h"

#ifdef __cplusplus
extern "C" {
#endif

/* ── display.c（与 esp32_pet_chat 工程相同）──────── */
lv_display_t *display_init(void);
void display_backlight(bool on);
void display_clear_dark(void);

/* ── emopet_face.c：核心 ─────────────────────────── */
/** 创建全屏 canvas（眼睛画在这里）。必须在 LVGL 就绪后调用。 */
lv_obj_t *emopet_canvas_create(lv_obj_t *parent);

/** 切换表情。内部会走"闭眼 → 换形 → 睁眼"的 300ms 转场。 */
void emopet_set_emotion(emo_id_t id);

/** 手动眨一下 */
void emopet_blink(void);

/** 设置眼睛配色（默认冰蓝）*/
void emopet_set_color(uint8_t r, uint8_t g, uint8_t b);

/** 开关叠加元素 */
void emopet_set_status_bar(bool on);    /* 顶部 时间/WiFi/电量 */
void emopet_set_wave(bool on);          /* 底部声波条 */
void emopet_set_auto_blink(bool on);
void emopet_set_breathe(bool on);

/** 每帧推进 + 渲染。由 LVGL timer 调用（建议 33ms）。 */
void emopet_tick(void);

/** 供 audio.c 驱动"说话"时眼睛跳动 */
void emopet_set_energy(float e);

/* ── keys.c ──────────────────────────────────────── */
typedef enum {
    KEY_EVT_NONE = 0,
    KEY_EVT_BOOT_SINGLE, KEY_EVT_BOOT_DOUBLE, KEY_EVT_BOOT_LONG,
    KEY_EVT_VOLUP_SINGLE, KEY_EVT_VOLUP_LONG,
    KEY_EVT_VOLDN_SINGLE, KEY_EVT_VOLDN_LONG,
    KEY_EVT_BOTH_VOL,
} key_event_t;
typedef void (*key_cb_t)(key_event_t evt);
void keys_init(key_cb_t cb);

/* ── audio.c ─────────────────────────────────────── */
void audio_start(void);
float audio_get_energy(void);

#ifdef __cplusplus
}
#endif

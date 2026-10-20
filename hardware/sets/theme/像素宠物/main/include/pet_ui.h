#pragma once
/* ============================================================
 * pet_ui.h — 模块接口
 * ============================================================ */
#include "app_config.h"
#include "lvgl.h"

#ifdef __cplusplus
extern "C" {
#endif

/* ── display.c ────────────────────────────────────── */
/** 初始化 SPI + ST7789 + LVGL port。返回 LVGL display 句柄。 */
lv_display_t *display_init(void);
/** 背光开关（开机动画的关键：先灭背光再初始化，避免花屏） */
void display_backlight(bool on);
/** 硬件清屏为暖黑（上电第一件事） */
void display_clear_dark(void);

/* ── pet_canvas.c ─────────────────────────────────── */
/** 创建全屏 canvas（宠物 / 涟漪 / 轮廓 / 角标都画在这里） */
lv_obj_t *pet_canvas_create(lv_obj_t *parent);
/**
 * 渲染一帧宠物到 canvas。
 * @param p          开机进度（NULL 表示已完成，全部置 1）
 * @param energy     音频能量 0..1（驱动嘴形与耳朵）
 * @param skin       表情皮肤
 * @param blink      是否闭眼（随机眨眼）
 */
void pet_canvas_render(const boot_prog_t *p, float energy, pet_skin_t skin, bool blink);

/* ── boot_anim.c ──────────────────────────────────── */
typedef void (*boot_done_cb_t)(void);
/** 启动开机动画。branch 见 boot_branch_t。done 为播放结束回调（可为 NULL）。 */
void boot_anim_start(boot_branch_t branch, boot_done_cb_t done);
/** 单击 BOOT 跳过（首开机未配网分支不响应） */
void boot_anim_skip(void);
bool boot_anim_is_done(void);
/** 取当前进度（供 canvas 渲染） */
const boot_prog_t *boot_anim_prog(void);

/* ── ui_screens.c ─────────────────────────────────── */
void ui_screens_init(lv_obj_t *canvas);
void ui_set_state(ui_state_t st);
ui_state_t ui_get_state(void);
void ui_set_volume(uint8_t v);          /* 0..10 */
void ui_show_bubble(const char *text);  /* NULL 隐藏 */
void ui_tick(void);                     /* 由 LVGL timer 调用，处理眨眼/待机动作 */
bool ui_is_skip_allowed(void);
void ui_show_qr_placeholder(void);      /* 未配网分支：显示二维码占位 */
void ui_reveal_after_boot(void);        /* 开机动画落位：显示控件层 */
void ui_menu_move(int delta);           /* 菜单导航（VOL±）*/
void ui_menu_confirm(void);             /* 菜单确认（BOOT）*/

/* boot_anim.c 额外导出 */
const char *boot_greeting(void);        /* 按时间/纪念日返回问候语 */

/* ── keys.c ───────────────────────────────────────── */
typedef enum {
    KEY_EVT_NONE = 0,
    KEY_EVT_BOOT_SINGLE,
    KEY_EVT_BOOT_DOUBLE,
    KEY_EVT_BOOT_LONG,
    KEY_EVT_VOLUP_SINGLE,
    KEY_EVT_VOLUP_LONG,
    KEY_EVT_VOLDN_SINGLE,
    KEY_EVT_VOLDN_LONG,
    KEY_EVT_BOTH_VOL,       /* VOL+ 与 VOL- 同按 */
} key_event_t;
typedef void (*key_cb_t)(key_event_t evt);
void keys_init(key_cb_t cb);
void keys_set_enabled(bool en);

/* ── audio.c ──────────────────────────────────────── */
void audio_start(void);
/** 返回平滑后的音频能量 0..1 */
float audio_get_energy(void);

#ifdef __cplusplus
}
#endif

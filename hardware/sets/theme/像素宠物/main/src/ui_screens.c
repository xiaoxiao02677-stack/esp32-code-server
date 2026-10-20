/* ============================================================
 * ui_screens.c — 顶栏 / 气泡 / 音量条 / 2x2 菜单（LVGL 标准控件）
 * 宠物由 pet_canvas 自绘，这里只管"控件层"
 * ============================================================ */
#include <string.h>
#include "esp_log.h"
#include "app_config.h"
#include "pet_ui.h"

static const char *TAG = "ui_screens";

#if defined(CONFIG_LV_FONT_SIMSUN_16_CJK)
extern const lv_font_t lv_font_simsun_16_cjk;
#define UI_FONT_CN (&lv_font_simsun_16_cjk)
#else
#define UI_FONT_CN LV_FONT_DEFAULT
#endif

#define MK(r, g, b) lv_color_make(r, g, b)

static lv_obj_t *s_lbl_time = NULL;
static lv_obj_t *s_lbl_status = NULL;
static lv_obj_t *s_bar_vol = NULL;
static lv_obj_t *s_bubble = NULL;
static lv_obj_t *s_lbl_bubble = NULL;
static lv_obj_t *s_menu[4] = {0};
static lv_obj_t *s_lbl_menu[4] = {0};
static lv_obj_t *s_lbl_hint = NULL;
static lv_obj_t *s_qr_box = NULL;

static ui_state_t s_state = UI_ST_IDLE;
static uint8_t    s_vol = 6;
static int        s_menu_sel = 0;

static const char *MENU_NAME[4] = { "音量", "表情", "亮度", "夜间" };
static const char *MENU_VAL[4]  = { "6", "猫", "70%", "自动" };

static void style_reset(lv_obj_t *o)
{
    lv_obj_remove_style_all(o);
}

void ui_screens_init(lv_obj_t *canvas)
{
    (void)canvas;
    lv_obj_t *scr = lv_screen_active();

    /* ── 顶栏 ───────────────────────────────────── */
    s_lbl_time = lv_label_create(scr);
    style_reset(s_lbl_time);
    lv_obj_set_style_text_font(s_lbl_time, UI_FONT_CN, 0);
    lv_obj_set_style_text_color(s_lbl_time, MK(196, 158, 138), 0);
    lv_label_set_text(s_lbl_time, "20:14");
    lv_obj_set_pos(s_lbl_time, 16, TOPBAR_Y - 8);

    s_lbl_status = lv_label_create(scr);
    style_reset(s_lbl_status);
    lv_obj_set_style_text_font(s_lbl_status, UI_FONT_CN, 0);
    lv_obj_set_style_text_color(s_lbl_status, MK(196, 158, 138), 0);
    lv_label_set_text(s_lbl_status, "WiFi 电量");
    lv_obj_set_pos(s_lbl_status, 170, TOPBAR_Y - 8);

    /* ── 底部音量条（方屏用直条，不用弧）────────── */
    s_bar_vol = lv_bar_create(scr);
    lv_obj_set_size(s_bar_vol, 160, 6);
    lv_obj_set_pos(s_bar_vol, 40, VOL_Y);
    lv_obj_set_style_radius(s_bar_vol, 3, LV_PART_MAIN);
    lv_obj_set_style_bg_color(s_bar_vol, MK(238, 216, 198), LV_PART_MAIN);
    lv_obj_set_style_bg_opa(s_bar_vol, LV_OPA_COVER, LV_PART_MAIN);
    lv_obj_set_style_bg_color(s_bar_vol, MK(255, 150, 130), LV_PART_INDICATOR);
    lv_obj_remove_style(s_bar_vol, NULL, LV_PART_KNOB);
    lv_bar_set_range(s_bar_vol, 0, 10);
    lv_bar_set_value(s_bar_vol, s_vol, LV_ANIM_OFF);

    /* ── 气泡（方屏可拉到 200 宽）───────────────── */
    s_bubble = lv_obj_create(scr);
    style_reset(s_bubble);
    lv_obj_set_size(s_bubble, BUBBLE_W, BUBBLE_H);
    lv_obj_set_pos(s_bubble, 20, 26);
    lv_obj_set_style_radius(s_bubble, 14, 0);
    lv_obj_set_style_bg_color(s_bubble, lv_color_white(), 0);
    lv_obj_set_style_bg_opa(s_bubble, LV_OPA_COVER, 0);
    lv_obj_set_style_border_width(s_bubble, 2, 0);
    lv_obj_set_style_border_color(s_bubble, MK(190, 118, 100), 0);
    lv_obj_add_flag(s_bubble, LV_OBJ_FLAG_HIDDEN);

    s_lbl_bubble = lv_label_create(s_bubble);
    style_reset(s_lbl_bubble);
    lv_obj_set_style_text_font(s_lbl_bubble, UI_FONT_CN, 0);
    lv_obj_set_style_text_color(s_lbl_bubble, MK(74, 59, 55), 0);
    lv_label_set_text(s_lbl_bubble, "");
    lv_obj_center(s_lbl_bubble);

    /* ── 2x2 菜单（方屏用网格，比环形好读）──────── */
    static const int gx[4] = { 26, 132, 26, 132 };
    static const int gy[4] = { 60, 60, 128, 128 };
    for (int i = 0; i < 4; i++) {
        s_menu[i] = lv_obj_create(scr);
        style_reset(s_menu[i]);
        lv_obj_set_size(s_menu[i], 82, 56);
        lv_obj_set_pos(s_menu[i], gx[i], gy[i]);
        lv_obj_set_style_radius(s_menu[i], 12, 0);
        lv_obj_set_style_bg_color(s_menu[i], lv_color_white(), 0);
        lv_obj_set_style_bg_opa(s_menu[i], LV_OPA_COVER, 0);
        lv_obj_set_style_border_width(s_menu[i], 2, 0);
        lv_obj_set_style_border_color(s_menu[i], MK(190, 118, 100), 0);
        lv_obj_add_flag(s_menu[i], LV_OBJ_FLAG_HIDDEN);

        s_lbl_menu[i] = lv_label_create(s_menu[i]);
        style_reset(s_lbl_menu[i]);
        lv_obj_set_style_text_font(s_lbl_menu[i], UI_FONT_CN, 0);
        lv_obj_set_style_text_color(s_lbl_menu[i], MK(74, 59, 55), 0);
        lv_label_set_text(s_lbl_menu[i], MENU_NAME[i]);
        lv_obj_center(s_lbl_menu[i]);
    }

    /* ── 底部提示 ───────────────────────────────── */
    s_lbl_hint = lv_label_create(scr);
    style_reset(s_lbl_hint);
    lv_obj_set_style_text_font(s_lbl_hint, UI_FONT_CN, 0);
    lv_obj_set_style_text_color(s_lbl_hint, MK(196, 158, 138), 0);
    lv_label_set_text(s_lbl_hint, "Zzz · 按 BOOT 说话");
    lv_obj_set_pos(s_lbl_hint, 60, 232);

    /* 开机动画期间隐藏控件层，落位后再显示 */
    lv_obj_add_flag(s_lbl_time, LV_OBJ_FLAG_HIDDEN);
    lv_obj_add_flag(s_lbl_status, LV_OBJ_FLAG_HIDDEN);
    lv_obj_add_flag(s_bar_vol, LV_OBJ_FLAG_HIDDEN);
    lv_obj_add_flag(s_lbl_hint, LV_OBJ_FLAG_HIDDEN);
}

void ui_set_state(ui_state_t st)
{
    s_state = st;
    const bool in_menu = (st == UI_ST_MENU);

    lv_obj_add_flag(s_bubble, LV_OBJ_FLAG_HIDDEN);
    for (int i = 0; i < 4; i++) lv_obj_add_flag(s_menu[i], LV_OBJ_FLAG_HIDDEN);

    if (in_menu) {
        for (int i = 0; i < 4; i++) lv_obj_remove_flag(s_menu[i], LV_OBJ_FLAG_HIDDEN);
        lv_label_set_text(s_lbl_hint, "VOL± 选择   BOOT 确认");
    } else {
        switch (st) {
        case UI_ST_LISTEN: lv_label_set_text(s_lbl_hint, "在听你说…"); break;
        case UI_ST_THINK:  lv_label_set_text(s_lbl_hint, "让我想想…"); break;
        case UI_ST_SPEAK:  lv_label_set_text(s_lbl_hint, "刚刚 · 已送达"); break;
        default:           lv_label_set_text(s_lbl_hint, "Zzz · 按 BOOT 说话"); break;
        }
    }
}

ui_state_t ui_get_state(void) { return s_state; }

void ui_set_volume(uint8_t v)
{
    if (v > 10) v = 10;
    s_vol = v;
    lv_bar_set_value(s_bar_vol, v, LV_ANIM_ON);
    MENU_VAL[0] = "6";  /* 若有动态字符串需求，用 snprintf 到静态缓冲 */
}

void ui_show_bubble(const char *text)
{
    if (!text) { lv_obj_add_flag(s_bubble, LV_OBJ_FLAG_HIDDEN); return; }
    lv_label_set_text(s_lbl_bubble, text);
    lv_obj_remove_flag(s_bubble, LV_OBJ_FLAG_HIDDEN);
}

void ui_tick(void)
{
    /* 空转占位：气泡超时隐藏、音量条高亮淡回等可在此扩展 */
}

bool ui_is_skip_allowed(void) { return true; }

/* 菜单导航（由按键回调调用） */
void ui_menu_move(int delta)
{
    s_menu_sel = (s_menu_sel + delta + 4) % 4;
    for (int i = 0; i < 4; i++) {
        if (i == s_menu_sel) {
            lv_obj_set_style_bg_color(s_menu[i], MK(255, 150, 130), 0);
            lv_obj_set_size(s_menu[i], 88, 60);   /* 选中项放大约 8% */
            lv_obj_set_style_text_color(s_lbl_menu[i], lv_color_white(), 0);
        } else {
            lv_obj_set_style_bg_color(s_menu[i], lv_color_white(), 0);
            lv_obj_set_size(s_menu[i], 82, 56);
            lv_obj_set_style_text_color(s_lbl_menu[i], MK(74, 59, 55), 0);
        }
    }
}

void ui_menu_confirm(void)
{
    ESP_LOGI(TAG, "菜单确认：%s = %s", MENU_NAME[s_menu_sel], MENU_VAL[s_menu_sel]);
    /* 这里接各设置项的实际逻辑：音量 / 表情 / 亮度 / 夜间 */
}

/* 开机动画落位：显示控件层 */
void ui_reveal_after_boot(void)
{
    lv_obj_remove_flag(s_lbl_time, LV_OBJ_FLAG_HIDDEN);
    lv_obj_remove_flag(s_lbl_status, LV_OBJ_FLAG_HIDDEN);
    lv_obj_remove_flag(s_bar_vol, LV_OBJ_FLAG_HIDDEN);
    lv_obj_remove_flag(s_lbl_hint, LV_OBJ_FLAG_HIDDEN);
    ui_show_bubble(NULL);
}

/* 未配网分支：显示二维码占位（真实二维码请用 esp-qrcode 生成） */
void ui_show_qr_placeholder(void)
{
    lv_obj_t *scr = lv_screen_active();
    s_qr_box = lv_obj_create(scr);
    style_reset(s_qr_box);
    lv_obj_set_size(s_qr_box, 144, 144);
    lv_obj_set_pos(s_qr_box, 48, 42);
    lv_obj_set_style_radius(s_qr_box, 6, 0);
    lv_obj_set_style_bg_color(s_qr_box, lv_color_white(), 0);
    lv_obj_set_style_border_width(s_qr_box, 2, 0);
    lv_obj_set_style_border_color(s_qr_box, MK(190, 118, 100), 0);

    lv_obj_t *lb = lv_label_create(s_qr_box);
    style_reset(lb);
    lv_obj_set_style_text_font(lb, UI_FONT_CN, 0);
    lv_obj_set_style_text_color(lb, MK(74, 59, 55), 0);
    lv_label_set_text(lb, "扫码配网\n(接 esp-qrcode)");
    lv_obj_center(lb);
}

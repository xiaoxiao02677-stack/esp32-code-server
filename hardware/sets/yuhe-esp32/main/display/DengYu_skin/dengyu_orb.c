// ════════════════════════════════════════════════════════════════════════
// 灯语 DengYu 主题 · 光萤渲染实现（dengyu_orb.c）
// ════════════════════════════════════════════════════════════════════════
// LVGL v9。纯 C（皮肤 C++ 侧调用）。
//
// 居中方案：所有子对象挂 wrapper（透明容器，尺寸 = 涟漪最大直径），
// 子对象 LV_ALIGN_CENTER 对齐。涟漪 size 动画只改宽度高度，LVGL 自动
// 按对齐规则重新居中——从根上消灭「set_size 不挪 pos 导致漂移」。
// 呼吸 zoom 作用于 core_box 容器（zoom 以对象中心为锚），内层圆不动。
//
// 性能预算：呼吸+涟漪慢动画，重绘区 ≈ 涟漪最大外接框（240 基准屏 34%），
// LVGL 脏区刷新 30fps 稳态；低配砍双道涟漪为单道（改 ripple_start 层数）。

#include "dengyu_orb.h"

#include <esp_log.h>
#include <stdlib.h>
#include <string.h>

#define TAG "DengYuOrb"

// 4 套轮换配色（RGB565 量化值，与 theme/DengYu 提案 token 表一致）
static const dengyu_orb_colors_t kPalettes[DENGYU_PALETTE_MAX] = {
    {0xFFF6E1, 0xFFEBC5, 0xFFCA8C, 0xC57D3A, 0xFFCA8C},  // 炭火（暖橙）
    {0xEAF6FF, 0xBFE4FF, 0x8CC8FF, 0x3D6BB8, 0x8CC8FF},  // 月光（青蓝）
    {0xF4EBFF, 0xDCC2FF, 0xB28CFA, 0x6B3DB8, 0xB28CFA},  // 紫暮（薰衣草）
    {0xFFF1EC, 0xF9B8A8, 0xEF715A, 0x8E4636, 0xEF715A},  // 珊瑚（蜜桃）
};

static const char* kPaletteNames[DENGYU_PALETTE_MAX] = {
    "炭火", "月光", "紫暮", "珊瑚",
};

// 聆听态青苔绿（状态色，非轮换盘）
static const dengyu_orb_colors_t kListenColors = {
    0xF2FFF3, 0xDDF3DF, 0xADDBB5, 0x5E8A66, 0xADDBB5,
};
// 断连态珊瑚红（与轮换珊瑚盘一致，芯偏白）
static const dengyu_orb_colors_t kErrorColors = {
    0xFFF1EC, 0xF9B8A8, 0xEF715A, 0x8E4636, 0xEF715A,
};

const dengyu_orb_colors_t* dengyu_orb_colors(dengyu_palette_t palette) {
    if (palette < 0 || palette >= DENGYU_PALETTE_MAX) {
        return &kPalettes[DENGYU_PALETTE_EMBER];
    }
    return &kPalettes[palette];
}

const char* dengyu_palette_name(dengyu_palette_t palette) {
    if (palette < 0 || palette >= DENGYU_PALETTE_MAX) {
        return kPaletteNames[0];
    }
    return kPaletteNames[palette];
}

const dengyu_geom_t* dengyu_default_geom(void) {
    static const dengyu_geom_t g = {
        .orb_d = 64, .orb_layer_d = 52, .ripple_max_d = 178, .mini_orb_d = 26,
    };
    return &g;
}

const dengyu_motion_t* dengyu_default_motion(void) {
    static const dengyu_motion_t m = {
        .breathe_half_ms = 2400,
        .ripple_period_ms = 6400,
        .ripple_phase_ms = 3200,
        .typewriter_ms = 120,
        .state_fade_ms = 300,
    };
    return &m;
}

struct dengyu_orb_s {
    lv_obj_t* wrapper;       // 透明容器（定位 cx,cy）
    lv_obj_t* core_box;      // 呼吸 zoom 作用点
    lv_obj_t* layers[4];     // l1 芯 → l4 外圈
    lv_obj_t* ripples[2];
    lv_obj_t* dots[3];
    lv_anim_t breathe_zoom;
    lv_anim_t breathe_opa;
    lv_anim_t ripple_size[2];
    lv_anim_t ripple_opa[2];
    lv_anim_t dot_y[3];
    lv_anim_t dot_opa[3];
    int cx, cy, d;
    bool mini;
    bool thinking;
};

// ---- 工具 ----

static void style_circle(lv_obj_t* obj, uint32_t color, int d) {
    lv_obj_set_size(obj, d, d);
    lv_obj_set_style_radius(obj, d / 2, 0);
    lv_obj_set_style_bg_color(obj, lv_color_hex(color), 0);
    lv_obj_set_style_bg_opa(obj, LV_OPA_COVER, 0);
    lv_obj_set_style_border_width(obj, 0, 0);
    lv_obj_set_style_pad_all(obj, 0, 0);
    lv_obj_remove_flag(obj, LV_OBJ_FLAG_SCROLLABLE);
    lv_obj_remove_flag(obj, LV_OBJ_FLAG_CLICKABLE);
}

static lv_obj_t* make_ripple(lv_obj_t* parent, int d, uint32_t color) {
    lv_obj_t* r = lv_obj_create(parent);
    lv_obj_set_size(r, d, d);
    lv_obj_set_style_radius(r, d / 2, 0);
    lv_obj_set_style_bg_opa(r, LV_OPA_TRANSP, 0);
    lv_obj_set_style_border_width(r, 2, 0);
    lv_obj_set_style_border_color(r, lv_color_hex(color), 0);
    lv_obj_set_style_border_opa(r, LV_OPA_60, 0);
    lv_obj_set_style_pad_all(r, 0, 0);
    lv_obj_remove_flag(r, LV_OBJ_FLAG_SCROLLABLE);
    lv_obj_remove_flag(r, LV_OBJ_FLAG_CLICKABLE);
    lv_obj_align(r, LV_ALIGN_CENTER, 0, 0);
    lv_obj_add_flag(r, LV_OBJ_FLAG_HIDDEN);
    return r;
}

static void make_dot(dengyu_orb_t* orb, int i, uint32_t color, int d) {
    orb->dots[i] = lv_obj_create(orb->wrapper);
    style_circle(orb->dots[i], color, d);
    lv_obj_align(orb->dots[i], LV_ALIGN_CENTER, (i - 1) * (d + d / 3), 0);
    lv_obj_add_flag(orb->dots[i], LV_OBJ_FLAG_HIDDEN);
}

// ---- anim 回调（作用于不同对象，互不冲突）----

static void zoom_cb(void* var, int32_t v) {
    lv_obj_set_style_transform_zoom((lv_obj_t*)var, (uint32_t)v, 0);
}
static void opa_cb(void* var, int32_t v) {
    lv_obj_set_style_opa((lv_obj_t*)var, (lv_opa_t)v, 0);
}
static void size_cb(void* var, int32_t v) {
    lv_obj_set_size((lv_obj_t*)var, v, v);
}
static void y_cb(void* var, int32_t v) {
    lv_obj_set_y((lv_obj_t*)var, v);
}

// ---- 呼吸（zoom + opa，reverse 对称）----

static void breathe_start(dengyu_orb_t* orb, uint32_t half_ms, int opa_from, int opa_to) {
    if (orb->core_box == NULL) {
        return;
    }
    lv_anim_del(orb->core_box, zoom_cb);
    lv_anim_del(orb->core_box, opa_cb);

    lv_anim_t a;
    lv_anim_init(&a);
    lv_anim_set_var(&a, orb->core_box);
    lv_anim_set_exec_cb(&a, zoom_cb);
    lv_anim_set_values(&a, 256, 322);
    lv_anim_set_duration(&a, half_ms);
    lv_anim_set_reverse_duration(&a, half_ms);
    lv_anim_set_repeat_count(&a, LV_ANIM_REPEAT_INFINITE);
    lv_anim_set_path_cb(&a, lv_anim_path_ease_in_out);
    lv_anim_start(&a);
    orb->breathe_zoom = a;

    lv_anim_t o;
    lv_anim_init(&o);
    lv_anim_set_var(&o, orb->core_box);
    lv_anim_set_exec_cb(&o, opa_cb);
    lv_anim_set_values(&o, opa_from, opa_to);
    lv_anim_set_duration(&o, half_ms);
    lv_anim_set_reverse_duration(&o, half_ms);
    lv_anim_set_repeat_count(&o, LV_ANIM_REPEAT_INFINITE);
    lv_anim_set_path_cb(&o, lv_anim_path_ease_in_out);
    lv_anim_start(&o);
    orb->breathe_opa = o;
}

// ---- 涟漪（size 扩散 + 淡出；CENTER 对齐自动保持居中）----

static void ripple_start(dengyu_orb_t* orb, uint32_t period_ms, uint32_t phase_ms,
                         uint8_t layers) {
    int from = orb->d;
    int to = orb->d * 178 / 64;
    for (int i = 0; i < 2; i++) {
        if (orb->ripples[i] == NULL || i >= layers) {
            continue;
        }
        lv_obj_clear_flag(orb->ripples[i], LV_OBJ_FLAG_HIDDEN);
        lv_anim_del(orb->ripples[i], size_cb);
        lv_anim_del(orb->ripples[i], opa_cb);

        lv_anim_t a;
        lv_anim_init(&a);
        lv_anim_set_var(&a, orb->ripples[i]);
        lv_anim_set_exec_cb(&a, size_cb);
        lv_anim_set_values(&a, from, to);
        lv_anim_set_duration(&a, period_ms);
        lv_anim_set_delay(&a, i * phase_ms);
        lv_anim_set_repeat_count(&a, LV_ANIM_REPEAT_INFINITE);
        lv_anim_set_path_cb(&a, lv_anim_path_ease_out);
        lv_anim_start(&a);
        orb->ripple_size[i] = a;

        lv_anim_t o;
        lv_anim_init(&o);
        lv_anim_set_var(&o, orb->ripples[i]);
        lv_anim_set_exec_cb(&o, opa_cb);
        lv_anim_set_values(&o, LV_OPA_60, LV_OPA_TRANSP);
        lv_anim_set_duration(&o, period_ms);
        lv_anim_set_delay(&o, i * phase_ms);
        lv_anim_set_repeat_count(&o, LV_ANIM_REPEAT_INFINITE);
        lv_anim_set_path_cb(&o, lv_anim_path_ease_out);
        lv_anim_start(&o);
        orb->ripple_opa[i] = o;
    }
}

static void ripple_stop(dengyu_orb_t* orb) {
    for (int i = 0; i < 2; i++) {
        if (orb->ripples[i] == NULL) {
            continue;
        }
        lv_anim_del(orb->ripples[i], size_cb);
        lv_anim_del(orb->ripples[i], opa_cb);
        lv_obj_add_flag(orb->ripples[i], LV_OBJ_FLAG_HIDDEN);
    }
}

// ---- 思考三点 ----

static void dots_start(dengyu_orb_t* orb) {
    if (orb->mini || orb->dots[0] == NULL) {
        return;
    }
    for (int i = 0; i < 3; i++) {
        lv_obj_clear_flag(orb->dots[i], LV_OBJ_FLAG_HIDDEN);
        lv_anim_del(orb->dots[i], y_cb);
        lv_anim_del(orb->dots[i], opa_cb);
        int base_y = lv_obj_get_y(orb->dots[i]);

        lv_anim_t y;
        lv_anim_init(&y);
        lv_anim_set_var(&y, orb->dots[i]);
        lv_anim_set_exec_cb(&y, y_cb);
        lv_anim_set_values(&y, base_y, base_y - orb->d / 16);
        lv_anim_set_duration(&y, 720);
        lv_anim_set_reverse_duration(&y, 720);
        lv_anim_set_repeat_count(&y, LV_ANIM_REPEAT_INFINITE);
        lv_anim_set_delay(&y, i * 240);
        lv_anim_set_path_cb(&y, lv_anim_path_ease_in_out);
        lv_anim_start(&y);
        orb->dot_y[i] = y;

        lv_anim_t o;
        lv_anim_init(&o);
        lv_anim_set_var(&o, orb->dots[i]);
        lv_anim_set_exec_cb(&o, opa_cb);
        lv_anim_set_values(&o, LV_OPA_50, LV_OPA_COVER);
        lv_anim_set_duration(&o, 720);
        lv_anim_set_reverse_duration(&o, 720);
        lv_anim_set_repeat_count(&o, LV_ANIM_REPEAT_INFINITE);
        lv_anim_set_delay(&o, i * 240);
        lv_anim_set_path_cb(&o, lv_anim_path_ease_in_out);
        lv_anim_start(&o);
        orb->dot_opa[i] = o;
    }
    orb->thinking = true;
}

static void dots_stop(dengyu_orb_t* orb) {
    if (!orb->thinking) {
        return;
    }
    for (int i = 0; i < 3; i++) {
        if (orb->dots[i] == NULL) {
            continue;
        }
        lv_anim_del(orb->dots[i], y_cb);
        lv_anim_del(orb->dots[i], opa_cb);
        lv_obj_add_flag(orb->dots[i], LV_OBJ_FLAG_HIDDEN);
    }
    orb->thinking = false;
}

// ---- 生命周期 ----

static dengyu_orb_t* orb_alloc(lv_obj_t* parent, int cx, int cy, int d, bool mini) {
    dengyu_orb_t* orb = (dengyu_orb_t*)calloc(1, sizeof(dengyu_orb_t));
    if (orb == NULL) {
        return NULL;
    }
    orb->cx = cx;
    orb->cy = cy;
    orb->d = d;
    orb->mini = mini;

    // wrapper：涟漪最大尺寸的透明容器，定位中心
    int wrap_d = mini ? d : d * 178 / 64;
    orb->wrapper = lv_obj_create(parent);
    lv_obj_set_size(orb->wrapper, wrap_d, wrap_d);
    lv_obj_set_pos(orb->wrapper, cx - wrap_d / 2, cy - wrap_d / 2);
    lv_obj_set_style_bg_opa(orb->wrapper, LV_OPA_TRANSP, 0);
    lv_obj_set_style_border_width(orb->wrapper, 0, 0);
    lv_obj_set_style_pad_all(orb->wrapper, 0, 0);
    lv_obj_remove_flag(orb->wrapper, LV_OBJ_FLAG_SCROLLABLE);
    lv_obj_remove_flag(orb->wrapper, LV_OBJ_FLAG_CLICKABLE);

    // core_box（呼吸作用点）
    orb->core_box = lv_obj_create(orb->wrapper);
    lv_obj_set_size(orb->core_box, d, d);
    lv_obj_set_style_bg_opa(orb->core_box, LV_OPA_TRANSP, 0);
    lv_obj_set_style_border_width(orb->core_box, 0, 0);
    lv_obj_set_style_pad_all(orb->core_box, 0, 0);
    lv_obj_remove_flag(orb->core_box, LV_OBJ_FLAG_SCROLLABLE);
    lv_obj_remove_flag(orb->core_box, LV_OBJ_FLAG_CLICKABLE);
    lv_obj_align(orb->core_box, LV_ALIGN_CENTER, 0, 0);

    // 圆层：4 层（迷你 3 层）
    int layers_n = mini ? 3 : 4;
    for (int i = 0; i < layers_n; i++) {
        orb->layers[i] = lv_obj_create(orb->core_box);
        lv_obj_align(orb->layers[i], LV_ALIGN_CENTER, 0, 0);
    }
    style_circle(orb->layers[0], kPalettes[DENGYU_PALETTE_EMBER].core, d * 20 / 64);
    style_circle(orb->layers[1], kPalettes[DENGYU_PALETTE_EMBER].l2, d * 36 / 64);
    style_circle(orb->layers[2], kPalettes[DENGYU_PALETTE_EMBER].l3, d * 52 / 64);
    if (!mini) {
        style_circle(orb->layers[3], kPalettes[DENGYU_PALETTE_EMBER].l4, d);
    }

    // 涟漪
    orb->ripples[0] = make_ripple(orb->wrapper, d, kPalettes[DENGYU_PALETTE_EMBER].ripple);
    if (!mini) {
        orb->ripples[1] = make_ripple(orb->wrapper, d, kPalettes[DENGYU_PALETTE_EMBER].ripple);
    }

    // 思考点
    if (!mini) {
        int dot_d = d / 9;
        for (int i = 0; i < 3; i++) {
            make_dot(orb, i, kPalettes[DENGYU_PALETTE_EMBER].l3, dot_d);
        }
    }
    return orb;
}

dengyu_orb_t* dengyu_orb_create(lv_obj_t* parent, int cx, int cy, int d) {
    return orb_alloc(parent, cx, cy, d, false);
}

dengyu_orb_t* dengyu_mini_orb_create(lv_obj_t* parent, int cx, int cy, int d) {
    return orb_alloc(parent, cx, cy, d, true);
}

void dengyu_orb_destroy(dengyu_orb_t* orb) {
    if (orb == NULL) {
        return;
    }
    lv_anim_del(orb->core_box, zoom_cb);
    lv_anim_del(orb->core_box, opa_cb);
    for (int i = 0; i < 2; i++) {
        if (orb->ripples[i] != NULL) {
            lv_anim_del(orb->ripples[i], size_cb);
            lv_anim_del(orb->ripples[i], opa_cb);
        }
    }
    for (int i = 0; i < 3; i++) {
        if (orb->dots[i] != NULL) {
            lv_anim_del(orb->dots[i], y_cb);
            lv_anim_del(orb->dots[i], opa_cb);
        }
    }
    if (orb->wrapper != NULL) {
        lv_obj_delete(orb->wrapper);  // 子对象随之删除
    }
    free(orb);
}

void dengyu_orb_set_visible(dengyu_orb_t* orb, bool visible) {
    if (orb == NULL || orb->wrapper == NULL) {
        return;
    }
    if (visible) {
        lv_obj_clear_flag(orb->wrapper, LV_OBJ_FLAG_HIDDEN);
    } else {
        lv_obj_add_flag(orb->wrapper, LV_OBJ_FLAG_HIDDEN);
    }
}

void dengyu_orb_set_palette(dengyu_orb_t* orb, const dengyu_orb_colors_t* colors) {
    if (orb == NULL || colors == NULL) {
        return;
    }
    uint32_t cs[4] = {colors->core, colors->l2, colors->l3, colors->l4};
    int layers_n = orb->mini ? 3 : 4;
    for (int i = 0; i < layers_n; i++) {
        if (orb->layers[i] != NULL) {
            lv_obj_set_style_bg_color(orb->layers[i], lv_color_hex(cs[i]), 0);
        }
    }
    for (int i = 0; i < 2; i++) {
        if (orb->ripples[i] != NULL) {
            lv_obj_set_style_border_color(orb->ripples[i], lv_color_hex(colors->ripple), 0);
        }
    }
    for (int i = 0; i < 3; i++) {
        if (orb->dots[i] != NULL) {
            lv_obj_set_style_bg_color(orb->dots[i], lv_color_hex(colors->l3), 0);
        }
    }
}

// ---- 状态入口 ----

void dengyu_orb_idle(dengyu_orb_t* orb) {
    if (orb == NULL) {
        return;
    }
    dots_stop(orb);
    lv_obj_clear_flag(orb->core_box, LV_OBJ_FLAG_HIDDEN);
    lv_obj_set_style_opa(orb->core_box, LV_OPA_COVER, 0);
    const dengyu_motion_t* m = dengyu_default_motion();
    breathe_start(orb, m->breathe_half_ms, LV_OPA_80, LV_OPA_COVER);
    ripple_start(orb, m->ripple_period_ms, m->ripple_phase_ms, 2);
}

void dengyu_orb_listen(dengyu_orb_t* orb) {
    if (orb == NULL) {
        return;
    }
    dots_stop(orb);
    dengyu_orb_set_palette(orb, &kListenColors);
    lv_obj_set_style_opa(orb->core_box, LV_OPA_COVER, 0);
    breathe_start(orb, 1600, LV_OPA_80, LV_OPA_COVER);
    ripple_start(orb, 2900, 1450, 2);
}

void dengyu_orb_think(dengyu_orb_t* orb) {
    if (orb == NULL) {
        return;
    }
    // 圆层整体压暗（保持形态可见），涟漪停
    ripple_stop(orb);
    lv_obj_set_style_opa(orb->core_box, LV_OPA_40, 0);
    lv_anim_del(orb->core_box, zoom_cb);
    lv_anim_del(orb->core_box, opa_cb);
    lv_obj_set_style_transform_zoom(orb->core_box, 256, 0);
    dots_start(orb);
}

void dengyu_orb_speak(dengyu_orb_t* orb) {
    if (orb == NULL) {
        return;
    }
    dots_stop(orb);
    ripple_stop(orb);
    lv_obj_set_style_opa(orb->core_box, LV_OPA_COVER, 0);
    breathe_start(orb, 1900, LV_OPA_80, LV_OPA_COVER);
}

void dengyu_orb_error(dengyu_orb_t* orb) {
    if (orb == NULL) {
        return;
    }
    dots_stop(orb);
    ripple_stop(orb);
    dengyu_orb_set_palette(orb, &kErrorColors);
    lv_obj_set_style_opa(orb->core_box, LV_OPA_50, 0);
    breathe_start(orb, 3600, LV_OPA_40, LV_OPA_60);
}

void dengyu_orb_stop(dengyu_orb_t* orb) {
    if (orb == NULL) {
        return;
    }
    dots_stop(orb);
    ripple_stop(orb);
    if (orb->core_box != NULL) {
        lv_anim_del(orb->core_box, zoom_cb);
        lv_anim_del(orb->core_box, opa_cb);
        lv_obj_set_style_transform_zoom(orb->core_box, 256, 0);
        lv_obj_set_style_opa(orb->core_box, LV_OPA_COVER, 0);
    }
}

void dengyu_mini_orb_idle(dengyu_orb_t* orb) {
    if (orb == NULL || orb->core_box == NULL) {
        return;
    }
    lv_anim_del(orb->core_box, zoom_cb);
    lv_anim_del(orb->core_box, opa_cb);
    lv_anim_t a;
    lv_anim_init(&a);
    lv_anim_set_var(&a, orb->core_box);
    lv_anim_set_exec_cb(&a, zoom_cb);
    lv_anim_set_values(&a, 256, 300);
    lv_anim_set_duration(&a, 2100);
    lv_anim_set_reverse_duration(&a, 2100);
    lv_anim_set_repeat_count(&a, LV_ANIM_REPEAT_INFINITE);
    lv_anim_set_path_cb(&a, lv_anim_path_ease_in_out);
    lv_anim_start(&a);
    orb->breathe_zoom = a;

    lv_anim_t o;
    lv_anim_init(&o);
    lv_anim_set_var(&o, orb->core_box);
    lv_anim_set_exec_cb(&o, opa_cb);
    lv_anim_set_values(&o, LV_OPA_80, LV_OPA_COVER);
    lv_anim_set_duration(&o, 2100);
    lv_anim_set_reverse_duration(&o, 2100);
    lv_anim_set_repeat_count(&o, LV_ANIM_REPEAT_INFINITE);
    lv_anim_set_path_cb(&o, lv_anim_path_ease_in_out);
    lv_anim_start(&o);
    orb->breathe_opa = o;
}

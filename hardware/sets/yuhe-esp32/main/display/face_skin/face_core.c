// ════════════════════════════════════════════════════════════════════════
// 极简脸 face 主题 · 渲染核心实现（face_core.c）
// ════════════════════════════════════════════════════════════════════════
// LVGL v9。纯 C（皮肤 C++ 侧调用），设计原稿：
//   theme/face/docs/face_ui_preview.html（Square Face · Minimal）
//
// 与 HTML 原稿的对应关系：
//   CSS transform: translate/scale   → 每帧直接 set_pos/set_size（多层同心
//     圆等比换算，不用 transform 样式——dengyu 光萤同款纪律，从根上避免
//     pivot/zoom 像素采样误差）
//   box-shadow 双层辉光 → 3 层同心圆（glow 20% / glow2 40% / body 不透明）
//   rAF loop()         → face_core_tick()（显示层 30fps lv_timer 驱动）
//   Math.random()      → esp_random()
//
// 尺寸换算基准：眼径 72（240 原稿）。表情参数表按 240 基准 px 存储，
// 渲染时统一乘 eye_d/72 比例因子——四板 profile 只要 eye_d 对，全脸自适。
//
// 性能预算：呼吸 ±2.5% 让眼/嘴每帧都有 1~2px 尺寸变化，脏区 ≈ 两眼
// 外接框 + 嘴（240 屏约 18% 面积），LVGL 脏区刷新 30fps 稳态；
// 说话态由显示层隔帧降到 15fps（嘴 90ms 开合周期在 15fps 下仍有
// ~5.4 采样点/周期，平滑度可接受——pet 皮肤同款先例）。

#include "face_core.h"

#include <esp_log.h>
#include <esp_random.h>

#include <math.h>
#include <stdlib.h>

#define TAG "FaceCore"

#ifndef M_PI
#define M_PI 3.14159265358979323846f
#endif

// ---- 表情参数表（HTML expressions 配置表 1:1 搬运，240 基准 px）----
// 眼缩放：idle100 / happy+8 / shy-8 / think-4 / sleepy-12 / surprise+18 / angry-5
// 游荡：仅 idle 开（±3.5px 取整为 x4/y3），其余表情锁定直视（talking 由
//       点头替代、sleepy 由缓呼吸替代）
// 嘴：  idle 36×7r4@158 / talking 30×10r5@158（开合叠加） / happy 48×14r7@154
//       shy 22×6r3@156 / think 18×5r2@158 / sleepy 40×5r2@158
//       surprise 16×22r8@158 / angry 32×6r4@161
static const face_expr_params_t kExprTable[FACE_EXPR_MAX] = {
    // eye_scale, look_x, look_y, m_w, m_h, m_r, m_y
    [FACE_EXPR_IDLE] = {100, 4, 3, 36, 7, 4, 158},
    [FACE_EXPR_TALKING] = {100, 0, 0, 30, 10, 5, 158},
    [FACE_EXPR_HAPPY] = {108, 0, 0, 48, 14, 7, 154},
    [FACE_EXPR_SHY] = {92, 0, 0, 22, 6, 3, 156},
    [FACE_EXPR_THINK] = {96, 0, 0, 18, 5, 2, 158},
    [FACE_EXPR_SLEEPY] = {88, 0, 0, 40, 5, 2, 158},
    [FACE_EXPR_SURPRISE] = {118, 0, 0, 16, 22, 8, 158},
    [FACE_EXPR_ANGRY] = {95, 0, 0, 32, 6, 4, 161},
};

const face_expr_params_t* face_expr_params(face_expr_t expr) {
    if (expr < 0 || expr >= FACE_EXPR_MAX) {
        return &kExprTable[FACE_EXPR_IDLE];
    }
    return &kExprTable[expr];
}

// ---- 状态辉光色表（face_core.h 的 face_glow_t 逐项）----
static const uint32_t kGlowColors[FACE_GLOW_MAX] = {
    [FACE_GLOW_IDLE] = 0xB4DCFF,       // 原稿淡蓝
    [FACE_GLOW_LISTENING] = 0x7BE8A0,  // 青绿
    [FACE_GLOW_SPEAKING] = 0xF7B96A,   // 暖橙
    [FACE_GLOW_CONNECTING] = 0xF7D96A, // 琥珀（慢闪）
    [FACE_GLOW_ERROR] = 0xF76E5E,      // 珊瑚红
};

// ---- 动效参数（概率已从 HTML 60fps 换算到 30fps：每帧概率 ×2）----
const face_motion_t* face_default_motion(void) {
    static const face_motion_t m = {
        .blink_ms = 160,
        .blink_prob_permyriad = 70,    // 30fps 下 0.7%/帧（平均 ~4.8s 眨一次）
        .wander_prob_permyriad = 120,  // 30fps 下 1.2%/帧（平均 ~2.8s 重选）
        .interact_ms = 520,
        .interact_amp_pct = 16,
        .talk_nod_period = 180,
        .talk_mouth_period = 90,
        .talk_mouth_amp = 10,
        .lerp_follow = 5,
        .lerp_mouth = 8,
    };
    return &m;
}

// ---- 几何（240 基准 → 实际屏型）----
face_geom_t face_geom_make(int width, int height, bool round_screen) {
    // 圆屏不做额外收缩：眼/嘴均落在 240 内切圆内（左右最宽点 = 辉光外缘
    // x 28-11=17 / x 212+11=223，y 47~169，到圆心距离均 < 120）
    (void)round_screen;
    face_geom_t g;
    g.screen_w = (int16_t)width;
    g.screen_h = (int16_t)height;
    const int short_side = (width < height) ? width : height;
    // 与 YhSkinProfile::scaled 同式：四舍五入等比
#define FACE_SC(px) ((int16_t)(((px) * short_side + 120) / 240))
    g.eye_d = FACE_SC(72);
    g.eye_y = FACE_SC(58);
    g.mouth_cx = (int16_t)(width / 2);
    g.mouth_y = FACE_SC(158);
    if (width > height + 8) {
        // 横屏 320x240：眼距拉开（中心距基准 56 → 78px），脸横向居中
        const int16_t sep = FACE_SC(78);
        g.eye_l_x = (int16_t)(width / 2 - sep - g.eye_d / 2);
        g.eye_r_x = (int16_t)(width / 2 + sep - g.eye_d / 2);
    } else if (height > width + 8) {
        // 竖屏 240x320：原稿坐标本身就在上区（脸占 y 47~169，底部自然
        // 留白 ~150px），原样保留即可
        const int16_t sep = FACE_SC(56);
        g.eye_l_x = (int16_t)(width / 2 - sep - g.eye_d / 2);
        g.eye_r_x = (int16_t)(width / 2 + sep - g.eye_d / 2);
    } else {
        // 方屏 240x240（圆屏同此）：原稿坐标原样
        g.eye_l_x = FACE_SC(28);
        g.eye_r_x = FACE_SC(140);
    }
#undef FACE_SC
    g.glow_d = (int16_t)((g.eye_d * 122 + 99) / 100);
    return g;
}

// ---- 内部状态 ----
struct face_core_s {
    lv_obj_t* root;             // 全屏透明容器（删它即拆整棵树）
    lv_obj_t* eye_wrap[2];      // 眼容器（尺寸 = 辉光外圈，子层 CENTER 对齐）
    lv_obj_t* eye_layer[2][3];  // [眼][glow / glow2 / body]
    lv_obj_t* mouth;

    face_geom_t geom;
    face_expr_t expr;

    // 眨眼
    bool blinking;
    uint32_t blink_start_ms;
    // interact 回弹 + 彩蛋表情窗口
    uint32_t interact_start_ms;  // 0 = 无回弹
    uint32_t expr_until_ms;      // 0 = 无窗口（set_expr 外部驱动时清零）
    // 状态辉光
    face_glow_t glow;
    uint32_t glow_switch_ms;     // 辉光切换时刻（换色 250ms 渐入用）
    // 游荡（当前值 + 目标值，240 基准 px）
    int16_t look_x, look_y;
    int16_t look_tx, look_ty;
    // 嘴四参数当前值 + 眼缩放当前值（lerp 渐进，240 基准）
    int16_t m_w, m_h, m_r, m_y;
    int16_t eye_scale_pct;

    bool visible;
};

// ---- 工具 ----

static void plain_obj(lv_obj_t* obj) {
    lv_obj_remove_flag(obj, LV_OBJ_FLAG_SCROLLABLE);
    lv_obj_remove_flag(obj, LV_OBJ_FLAG_CLICKABLE);
    lv_obj_set_style_border_width(obj, 0, 0);
    lv_obj_set_style_pad_all(obj, 0, 0);
    lv_obj_set_style_radius(obj, 0, 0);
}

static lv_obj_t* make_circle_layer(lv_obj_t* parent, uint32_t color, lv_opa_t opa) {
    lv_obj_t* o = lv_obj_create(parent);
    plain_obj(o);
    lv_obj_set_style_bg_color(o, lv_color_hex(color), 0);
    lv_obj_set_style_bg_opa(o, opa, 0);
    lv_obj_align(o, LV_ALIGN_CENTER, 0, 0);
    return o;
}

// ---- 创建 / 销毁 ----

face_core_t* face_core_create(lv_obj_t* parent, const face_geom_t* geom) {
    if (parent == nullptr || geom == nullptr) {
        return nullptr;
    }
    face_core_t* core = (face_core_t*)calloc(1, sizeof(face_core_t));
    if (core == nullptr) {
        ESP_LOGE(TAG, "alloc failed");
        return nullptr;
    }
    core->geom = *geom;
    core->expr = FACE_EXPR_IDLE;
    core->visible = true;

    // 全屏透明容器：不参与布局、不吃点击
    core->root = lv_obj_create(parent);
    plain_obj(core->root);
    lv_obj_set_size(core->root, geom->screen_w, geom->screen_h);
    lv_obj_set_pos(core->root, 0, 0);
    lv_obj_set_style_bg_opa(core->root, LV_OPA_TRANSP, 0);

    // 两只眼：容器尺寸 = 辉光外圈（子层比容器小不会裁；LVGL 默认按父裁剪，
    // 所以容器取最大层尺寸，body/glow2 居中缩小）
    const face_expr_params_t* p = face_expr_params(FACE_EXPR_IDLE);
    core->eye_scale_pct = p->eye_scale_pct;
    core->m_w = p->mouth_w;
    core->m_h = p->mouth_h;
    core->m_r = p->mouth_r;
    core->m_y = p->mouth_y;
    for (int i = 0; i < 2; ++i) {
        core->eye_wrap[i] = lv_obj_create(core->root);
        plain_obj(core->eye_wrap[i]);
        lv_obj_set_style_bg_opa(core->eye_wrap[i], LV_OPA_TRANSP, 0);
        // 层序：先建的在底 → glow（最底最淡）/ glow2 / body（最上不透明）
        core->eye_layer[i][0] = make_circle_layer(core->eye_wrap[i], FACE_COLOR_GLOW, LV_OPA_20);
        core->eye_layer[i][1] = make_circle_layer(core->eye_wrap[i], FACE_COLOR_GLOW, LV_OPA_40);
        core->eye_layer[i][2] = make_circle_layer(core->eye_wrap[i], FACE_COLOR_BODY, LV_OPA_COVER);
    }

    // 嘴：圆角矩形，主体色
    core->mouth = lv_obj_create(core->root);
    plain_obj(core->mouth);
    lv_obj_set_style_bg_color(core->mouth, lv_color_hex(FACE_COLOR_BODY), 0);
    lv_obj_set_style_bg_opa(core->mouth, LV_OPA_COVER, 0);

    // 初帧落位（中心值，无呼吸）
    face_core_tick(core, true);
    return core;
}

void face_core_destroy(face_core_t* core) {
    if (core == nullptr) {
        return;
    }
    if (core->root != nullptr && lv_obj_is_valid(core->root)) {
        lv_obj_delete(core->root);
    }
    free(core);
}

void face_core_set_visible(face_core_t* core, bool visible) {
    if (core == nullptr || core->visible == visible) {
        return;
    }
    core->visible = visible;
    if (core->root != nullptr) {
        if (visible) {
            lv_obj_remove_flag(core->root, LV_OBJ_FLAG_HIDDEN);
        } else {
            lv_obj_add_flag(core->root, LV_OBJ_FLAG_HIDDEN);
        }
    }
}

// ---- 状态驱动 ----

void face_core_set_expr(face_core_t* core, face_expr_t expr) {
    if (core == nullptr || expr < 0 || expr >= FACE_EXPR_MAX) {
        return;
    }
    core->expr = expr;
    core->expr_until_ms = 0;  // 外部驱动接管，彩蛋自动回退窗口作废
}

face_expr_t face_core_expr(const face_core_t* core) {
    return (core == nullptr) ? FACE_EXPR_IDLE : core->expr;
}

// ---- 状态辉光 ----

void face_core_set_glow(face_core_t* core, face_glow_t glow) {
    if (core == nullptr || glow < 0 || glow >= FACE_GLOW_MAX || glow == core->glow) {
        return;
    }
    core->glow = glow;
    core->glow_switch_ms = lv_tick_get();
}

void face_core_interact(face_core_t* core) {
    if (core == nullptr) {
        return;
    }
    const uint32_t now = lv_tick_get();
    core->interact_start_ms = now;
    // 傲娇三选一：开心 / 害羞 / 惊讶（HTML interact() 同款随机）
    static const face_expr_t kPicks[3] = {FACE_EXPR_HAPPY, FACE_EXPR_SHY, FACE_EXPR_SURPRISE};
    core->expr = kPicks[esp_random() % 3];
    core->expr_until_ms = now + 1800;  // 1.8s 后自动回 idle
}

bool face_core_in_interact(const face_core_t* core) {
    if (core == nullptr) {
        return false;
    }
    const face_motion_t* mo = face_default_motion();
    const uint32_t now = lv_tick_get();
    if (core->interact_start_ms != 0 && now - core->interact_start_ms < mo->interact_ms) {
        return true;  // 回弹进行中
    }
    return core->expr_until_ms != 0 && now < core->expr_until_ms;
}

void face_core_blink(face_core_t* core) {
    if (core == nullptr) {
        return;
    }
    core->blinking = true;
    core->blink_start_ms = lv_tick_get();
}

// ---- 渲染推进 ----

static int16_t lerp_i16(int16_t cur, int16_t target, uint8_t pct) {
    return (int16_t)(cur + (target - cur) * pct / 100);
}

// 像素坐标四舍五入（截断会让 ±3.5px 游荡的 0.175px/帧步进全部沉没在同
// 一像素里，动作变僵）
static int16_t f2px(float v) {
    return (int16_t)(v >= 0.0f ? v + 0.5f : v - 0.5f);
}

void face_core_tick(face_core_t* core, bool render_this_frame) {
    if (core == nullptr) {
        return;
    }
    const face_motion_t* mo = face_default_motion();
    const face_expr_params_t* p = face_expr_params(core->expr);
    const uint32_t now = lv_tick_get();

    // ---- 状态推进（render_this_frame=false 时也要推进，跳帧不跳状态）----

    // 彩蛋窗口到期 → 回 idle
    if (core->expr_until_ms != 0 && now >= core->expr_until_ms) {
        core->expr_until_ms = 0;
        core->expr = FACE_EXPR_IDLE;
        p = face_expr_params(core->expr);
    }
    // 回弹结束
    if (core->interact_start_ms != 0 && now - core->interact_start_ms >= mo->interact_ms) {
        core->interact_start_ms = 0;
    }
    // 眨眼：进行中到期 / 空闲概率触发
    if (core->blinking) {
        if (now - core->blink_start_ms >= mo->blink_ms) {
            core->blinking = false;
        }
    } else if ((int)(esp_random() % 10000) < (int)mo->blink_prob_permyriad) {
        core->blinking = true;
        core->blink_start_ms = now;
    }
    // 游荡：仅 idle 开（amp>0 才有意义）
    if (p->look_amp_x > 0 || p->look_amp_y > 0) {
        if ((int)(esp_random() % 10000) < (int)mo->wander_prob_permyriad) {
            core->look_tx = (int16_t)((int)(esp_random() % (2 * p->look_amp_x + 1)) - p->look_amp_x);
            core->look_ty = (int16_t)((int)(esp_random() % (2 * p->look_amp_y + 1)) - p->look_amp_y);
        }
    } else {
        core->look_tx = 0;
        core->look_ty = 0;
    }
    core->look_x = lerp_i16(core->look_x, core->look_tx, mo->lerp_follow);
    core->look_y = lerp_i16(core->look_y, core->look_ty, mo->lerp_follow);
    // 嘴四参数 + 眼缩放 lerp 到表情目标
    core->m_w = lerp_i16(core->m_w, p->mouth_w, mo->lerp_mouth);
    core->m_h = lerp_i16(core->m_h, p->mouth_h, mo->lerp_mouth);
    core->m_r = lerp_i16(core->m_r, p->mouth_r, mo->lerp_mouth);
    core->m_y = lerp_i16(core->m_y, p->mouth_y, mo->lerp_mouth);
    core->eye_scale_pct = lerp_i16(core->eye_scale_pct, p->eye_scale_pct, mo->lerp_mouth);

    if (!render_this_frame) {
        return;  // 说话态隔帧：状态已推进，本帧不碰对象
    }

    // ---- 本帧参数合成 ----

    // 呼吸：idle 1.1s / sleepy 1.6s（更缓），±2.5%
    const float breath_period =
        (core->expr == FACE_EXPR_SLEEPY) ? 1600.0f : 1100.0f;
    const float bf = 1.0f + 0.025f * sinf(2.0f * (float)M_PI * (float)now / breath_period);

    // interact 回弹：sin(π·p) × 16%（0 → +16% → 0）
    float extra = 1.0f;
    if (core->interact_start_ms != 0) {
        float ip = (float)(now - core->interact_start_ms) / (float)mo->interact_ms;
        if (ip < 1.0f) {
            extra = 1.0f + ((float)mo->interact_amp_pct / 100.0f) * sinf((float)M_PI * ip);
        }
    }

    // 眨眼压扁：cos 缓动 1 → 0.04 → 1
    float hs = 1.0f;
    if (core->blinking) {
        float bp = (float)(now - core->blink_start_ms) / (float)mo->blink_ms;
        if (bp > 1.0f) bp = 1.0f;
        hs = 1.0f - 0.96f * (0.5f - 0.5f * cosf(2.0f * (float)M_PI * bp));
        if (hs < 0.04f) hs = 0.04f;
    }

    // talking 点头：±1.8px 正弦（180ms 周期）
    float nod_y = 0.0f;
    if (core->expr == FACE_EXPR_TALKING) {
        nod_y = 1.8f * sinf(2.0f * (float)M_PI * (float)now / (float)mo->talk_nod_period);
    }

    // 尺寸换算因子：240 基准 → 实际屏（以眼径为锚，表情参数全用它缩放）
    const float k_scale = (float)core->geom.eye_d / 72.0f;

    // ---- 眼睛 ----
    const float d_base =
        (float)core->geom.eye_d * (float)core->eye_scale_pct / 100.0f * bf * extra;
    const float eye_w = d_base;
    const float eye_h = d_base * hs;
    const float glow_w = eye_w * 1.22f;
    const float glow_h = eye_h * 1.22f;
    const float glow2_w = eye_w * 1.10f;
    const float glow2_h = eye_h * 1.10f;

    // 状态辉光：色/透明度（connecting 慢闪 1.6s，0↔π 正弦呼吸）
    lv_opa_t glow_opa_base = LV_OPA_20;
    lv_opa_t glow2_opa_base = LV_OPA_40;
    if (core->glow == FACE_GLOW_CONNECTING) {
        const float flick = 0.5f + 0.5f * sinf(2.0f * (float)M_PI * (float)now / 1600.0f);
        glow_opa_base = (lv_opa_t)(30 + 45 * flick);   // 30~75
        glow2_opa_base = (lv_opa_t)(60 + 60 * flick);  // 60~120
    }
    // 换色后 250ms 内辉光透明度从 0 渐入（避免硬切跳变）
    lv_opa_t glow_opa = glow_opa_base;
    lv_opa_t glow2_opa = glow2_opa_base;
    const uint32_t since_switch = now - core->glow_switch_ms;
    if (since_switch < 250) {
        const lv_opa_t k = (lv_opa_t)((since_switch * 255u) / 250u);
        glow_opa = (lv_opa_t)((glow_opa_base * k) / 255u);
        glow2_opa = (lv_opa_t)((glow2_opa_base * k) / 255u);
    }
    const uint32_t glow_color = kGlowColors[core->glow];

    for (int i = 0; i < 2; ++i) {
        const int16_t eye_x = (i == 0) ? core->geom.eye_l_x : core->geom.eye_r_x;
        const float cx = (float)(eye_x + core->geom.eye_d / 2) +
                         (float)core->look_x * k_scale;
        const float cy = (float)(core->geom.eye_y + core->geom.eye_d / 2) +
                         (float)core->look_y * k_scale + nod_y * k_scale;
        // 容器 = 辉光外圈尺寸，圆心对齐（子层 CENTER 自动跟）
        lv_obj_set_pos(core->eye_wrap[i], f2px(cx - glow_w / 2.0f), f2px(cy - glow_h / 2.0f));
        lv_obj_set_size(core->eye_wrap[i], f2px(glow_w), f2px(glow_h));
        lv_obj_t* l0 = core->eye_layer[i][0];
        lv_obj_t* l1 = core->eye_layer[i][1];
        lv_obj_t* l2 = core->eye_layer[i][2];
        // 状态辉光：色 + 透明度落在两层辉光上（主体圆不动）
        lv_obj_set_style_bg_color(l0, lv_color_hex(glow_color), 0);
        lv_obj_set_style_bg_opa(l0, glow_opa, 0);
        lv_obj_set_style_bg_color(l1, lv_color_hex(glow_color), 0);
        lv_obj_set_style_bg_opa(l1, glow2_opa, 0);
        lv_obj_set_size(l0, f2px(glow_w), f2px(glow_h));
        lv_obj_set_style_radius(l0, f2px(glow_w / 2.0f), 0);
        lv_obj_set_size(l1, f2px(glow2_w), f2px(glow2_h));
        lv_obj_set_style_radius(l1, f2px(glow2_w / 2.0f), 0);
        lv_obj_set_size(l2, f2px(eye_w), f2px(eye_h));
        // 半径钳制 min(w,h)/2：眨眼压扁到 0.04 时高度仅 ~3px，圆角若按
        // 宽径 36 落，LVGL 按 radius=min 半径钳制虽能兜住，显式钳制
        // 更稳（不赌内部实现细节）
        lv_obj_set_style_radius(l2, f2px(eye_w < eye_h ? eye_w / 2.0f : eye_h / 2.0f), 0);
    }

    // ---- 嘴 ----
    float mw = (float)core->m_w * k_scale;
    float mh = (float)core->m_h * k_scale * bf;  // 嘴随呼吸轻微起伏
    // talking 开合：90ms 周期、幅度 10px 的正弦叠加（拟态，非真实音频能量）
    if (core->expr == FACE_EXPR_TALKING) {
        float mp = 0.5f + 0.5f * sinf(2.0f * (float)M_PI * (float)now /
                                      (float)mo->talk_mouth_period);
        mh += (float)mo->talk_mouth_amp * k_scale * mp;
    }
    if (mw < 2.0f) mw = 2.0f;
    if (mh < 2.0f) mh = 2.0f;
    const int16_t r = (int16_t)((float)core->m_r * k_scale);
    lv_obj_set_size(core->mouth, f2px(mw), f2px(mh));
    lv_obj_set_style_radius(core->mouth, r, 0);
    lv_obj_set_pos(core->mouth,
                   f2px((float)core->geom.mouth_cx - mw / 2.0f),
                   f2px((float)core->m_y * k_scale - mh / 2.0f));
}

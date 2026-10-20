/* ============================================================
 * pet_canvas.c — 像素宠物绘制（全屏 lv_canvas 自绘）
 *
 * 为什么用 canvas 而不是几十个 lv_obj：
 *   1) 像素风需要关掉抗锯齿、按 8px 网格对齐，LVGL 控件做不到
 *   2) 开机动画的"中心扩散注入"需要逐块裁剪，canvas 最直接
 *   3) 全部在 PSRAM 的一块 buffer 里，零对象开销
 * ============================================================ */
#include <math.h>
#include <string.h>
#include "esp_log.h"
#include "esp_heap_caps.h"
#include "app_config.h"
#include "pet_ui.h"

static const char *TAG = "pet_canvas";

/* ── 配色（与预览 HTML 完全一致）────────────────────
 * 注意：lv_color_make() 在 LVGL 里是函数而非编译期常量，
 * 因此不能在 static const 初始化器里调用 —— 改为运行时填充。 */
#define MK(r, g, b) lv_color_make(r, g, b)
static lv_color_t C_BG_DARK, C_BG_LIT, C_LINE_D, C_INK, C_SUB, C_PINK, C_SEED, C_WHITE;

/* 各皮肤的脸 / 描边色 */
typedef struct { lv_color_t face, line; uint8_t ear; } skin_t;
static skin_t SKINS[PET_SKIN_MAX];

static void colors_init(void)
{
    C_BG_DARK = MK(26, 20, 18);
    C_BG_LIT  = MK(255, 243, 228);
    C_LINE_D  = MK(255, 195, 168);
    C_INK     = MK(74, 59, 55);
    C_SUB     = MK(196, 158, 138);
    C_PINK    = MK(255, 158, 158);
    C_SEED    = MK(255, 210, 180);
    C_WHITE   = MK(255, 255, 255);

    SKINS[PET_SKIN_CAT].face   = MK(255, 202, 184);
    SKINS[PET_SKIN_CAT].line   = MK(190, 118, 100);
    SKINS[PET_SKIN_CAT].ear    = 0;      /* 猫 · 尖耳   */

    SKINS[PET_SKIN_BEAR].face  = MK(232, 195, 154);
    SKINS[PET_SKIN_BEAR].line  = MK(168, 123, 85);
    SKINS[PET_SKIN_BEAR].ear   = 1;      /* 小熊 · 圆耳 */

    SKINS[PET_SKIN_CLOUD].face = MK(220, 235, 247);
    SKINS[PET_SKIN_CLOUD].line = MK(143, 180, 208);
    SKINS[PET_SKIN_CLOUD].ear  = 2;      /* 云兽 · 云耳 */
}

static lv_obj_t     *s_canvas = NULL;
static lv_color_t   *s_buf    = NULL;

/* ── 工具：像素椭圆（按 grid 网格填方块，天然像素风）── */
static void pixel_ellipse(lv_obj_t *cv, int cx, int cy, int rx, int ry,
                          int grid, lv_color_t col, lv_opa_t opa, float clip_r)
{
    lv_draw_rect_dsc_t d; lv_draw_rect_dsc_init(&d);
    d.bg_color = col; d.bg_opa = opa; d.radius = 0; d.border_width = 0;

    int x0 = ((cx - rx) / grid) * grid;
    int y0 = ((cy - ry) / grid) * grid;
    for (int y = y0; y <= cy + ry; y += grid) {
        for (int x = x0; x <= cx + rx; x += grid) {
            float dx = (float)(x + grid / 2 - cx) / (float)rx;
            float dy = (float)(y + grid / 2 - cy) / (float)ry;
            if (dx * dx + dy * dy > 1.0f) continue;
            if (clip_r >= 0.0f) {   /* 中心扩散裁剪 */
                float ddx = (float)(x + grid / 2 - cx);
                float ddy = (float)(y + grid / 2 - cy);
                if (ddx * ddx + ddy * ddy > clip_r * clip_r) continue;
            }
            lv_canvas_draw_rect(cv, x, y, grid, grid, &d);
        }
    }
}

/* ── 工具：椭圆弧（采样点连线，宽度/透明度可叠层做辉光）── */
static void ellipse_arc(lv_obj_t *cv, int cx, int cy, int rx, int ry,
                        float a0_deg, float a1_deg, lv_color_t col,
                        int width, lv_opa_t opa)
{
    if (a1_deg - a0_deg < 1.0f) return;
    lv_draw_line_dsc_t d; lv_draw_line_dsc_init(&d);
    d.color = col; d.width = width; d.opa = opa;
    d.round_start = 1; d.round_end = 1;

    const int seg = 40;
    lv_point_precise_t pts[48];
    int n = 0;
    for (int i = 0; i <= seg && n < 48; i++) {
        float a = (a0_deg + (a1_deg - a0_deg) * (float)i / (float)seg) * 3.14159265f / 180.0f;
        pts[n].x = (lv_value_precise_t)(cx + rx * cosf(a));
        pts[n].y = (lv_value_precise_t)(cy + ry * sinf(a));
        n++;
    }
    lv_canvas_draw_line(cv, pts, n, &d);
}

/* ── 工具：实心三角（耳朵）── */
static void tri(lv_obj_t *cv, const lv_point_t *p, lv_color_t col, lv_opa_t opa)
{
    lv_draw_polygon_dsc_t d; lv_draw_polygon_dsc_init(&d);
    d.bg_color = col; d.bg_opa = opa;
    lv_canvas_draw_polygon(cv, p, 3, &d);
}

/* ── 四角取景框（方屏专属，圆屏做不了）── */
static void corner_marks(lv_obj_t *cv, lv_opa_t opa)
{
    if (opa <= LV_OPA_MIN) return;
    lv_draw_line_dsc_t d; lv_draw_line_dsc_init(&d);
    d.color = C_SUB; d.width = 2; d.opa = (lv_opa_t)(opa * 55 / 100);
    const int m = 9, L = 14;
    lv_point_precise_t pts[2];
    /* 左上 */
    pts[0].x = m;             pts[0].y = m;
    pts[1].x = m + L;         pts[1].y = m;
    lv_canvas_draw_line(cv, pts, 2, &d);
    /* 右上 */
    pts[0].x = SCR_W - m - L; pts[0].y = m;
    pts[1].x = SCR_W - m;     pts[1].y = m;
    lv_canvas_draw_line(cv, pts, 2, &d);
    /* 左下 */
    pts[0].x = m;             pts[0].y = SCR_H - m;
    pts[1].x = m + L;         pts[1].y = SCR_H - m;
    lv_canvas_draw_line(cv, pts, 2, &d);
    /* 右下 */
    pts[0].x = SCR_W - m - L; pts[0].y = SCR_H - m;
    pts[1].x = SCR_W - m;     pts[1].y = SCR_H - m;
    lv_canvas_draw_line(cv, pts, 2, &d);
}

/* ── 耳朵：三种形状，随进度缩放 ─────────────────── */
static void draw_ears(lv_obj_t *cv, int cy, float scale, const skin_t *sk, bool dark)
{
    if (scale <= 0.01f) return;
    lv_color_t line = dark ? C_LINE_D : sk->line;

    for (int k = 0; k < 2; k++) {
        int sgn = k ? 1 : -1;
        int sx = 120 + sgn * 34;
        int base_y = cy - 46;
        int tip_y   = cy - 74;
        /* 缩放中心：耳朵根部 */
        int ax = sx + sgn * 10, ay = tip_y + 22;

        if (sk->ear == 0) {                    /* 猫 · 尖耳（双层三角）*/
            lv_point_t outer[3] = {
                { sx - 6, base_y }, { sx + 6, base_y }, { sx + sgn * 27, tip_y }
            };
            lv_point_t inner[3] = {
                { sx - 1, base_y }, { sx + 5, base_y }, { sx + sgn * 19, tip_y + 6 }
            };
            for (int i = 0; i < 3; i++) {
                outer[i].x = (int)((outer[i].x - ax) * scale + ax);
                outer[i].y = (int)((outer[i].y - ay) * scale + ay);
                inner[i].x = (int)((inner[i].x - ax) * scale + ax);
                inner[i].y = (int)((inner[i].y - ay) * scale + ay);
            }
            tri(cv, outer, line, LV_OPA_COVER);
            tri(cv, inner, sk->face, LV_OPA_COVER);
        } else if (sk->ear == 1) {             /* 小熊 · 圆耳 */
            int ex = sx + sgn * 17, ey = tip_y + 12;
            int r  = (int)(15 * scale);
            ex = (int)((ex - ax) * scale + ax);
            ey = (int)((ey - ay) * scale + ay);
            lv_draw_rect_dsc_t d; lv_draw_rect_dsc_init(&d);
            d.radius = LV_RADIUS_CIRCLE; d.border_width = 0;
            d.bg_color = line; d.bg_opa = LV_OPA_COVER;
            lv_canvas_draw_rect(cv, ex - r, ey - r, r * 2, r * 2, &d);
            d.bg_color = sk->face;
            lv_canvas_draw_rect(cv, ex - r + 4, ey - r + 4, (r - 4) * 2, (r - 4) * 2, &d);
        } else {                               /* 云兽 · 三圆叠云 */
            for (int i = 0; i < 3; i++) {
                int rr = (int)((15 - i * 2) * scale);
                int cxx = (int)((sx + sgn * (i * 11) - ax) * scale + ax);
                int cyy = (int)((base_y - 18 + i * 3 - ay) * scale + ay);
                lv_draw_rect_dsc_t d; lv_draw_rect_dsc_init(&d);
                d.radius = LV_RADIUS_CIRCLE; d.border_width = 0;
                d.bg_color = line; d.bg_opa = LV_OPA_COVER;
                lv_canvas_draw_rect(cv, cxx - rr, cyy - rr, rr * 2, rr * 2, &d);
                d.bg_color = sk->face;
                lv_canvas_draw_rect(cv, cxx - rr + 4, cyy - rr + 4, (rr - 4) * 2, (rr - 4) * 2, &d);
            }
        }
    }
}

/* ── 创建 canvas ─────────────────────────────────── */
lv_obj_t *pet_canvas_create(lv_obj_t *parent)
{
    colors_init();

    size_t bytes = (size_t)SCR_W * SCR_H * sizeof(lv_color_t);
    s_buf = heap_caps_malloc(bytes, MALLOC_CAP_SPIRAM);
    if (!s_buf) {
        ESP_LOGW(TAG, "PSRAM 分配失败，退回内部 RAM");
        s_buf = heap_caps_malloc(bytes, MALLOC_CAP_8BIT);
    }
    if (!s_buf) { ESP_LOGE(TAG, "canvas buffer 分配失败"); return NULL; }

    s_canvas = lv_canvas_create(parent);
    lv_obj_set_size(s_canvas, SCR_W, SCR_H);
    lv_obj_center(s_canvas);
#if LVGL_VERSION_MAJOR >= 9
    lv_canvas_set_buffer(s_canvas, s_buf, SCR_W, SCR_H, LV_COLOR_FORMAT_RGB565);
#else
    lv_canvas_set_buffer(s_canvas, s_buf, SCR_W, SCR_H, LV_IMG_CF_TRUE_COLOR);
#endif
    lv_canvas_fill_bg(s_canvas, C_BG_DARK, LV_OPA_COVER);
    return s_canvas;
}

/* ── 主渲染 ──────────────────────────────────────── */
void pet_canvas_render(const boot_prog_t *in, float energy, pet_skin_t skin_id, bool blink)
{
    if (!s_canvas) return;

    /* 已完成时全部置 1 */
    boot_prog_t full;
    if (!in) {
        memset(&full, 0, sizeof(full));
        full.seed = full.ripple = full.outline = full.fill = full.bg =
        full.ear = full.blush = full.eye = full.settle = 1.0f;
        in = &full;
    }

    const skin_t *sk = &SKINS[skin_id % PET_SKIN_MAX];
    bool dark = in->bg < 0.55f;
    lv_color_t line = lv_color_mix(C_LINE_D, sk->line, (uint8_t)(in->bg * 255));
    lv_color_t bg   = lv_color_mix(C_BG_DARK, C_BG_LIT, (uint8_t)(in->bg * 255));

    /* 宠物中心：回应时下移让位气泡，落位时回归 */
    int cy = CY_BASE + (int)((float)(CY_SPEAK - CY_BASE) * in->bubble * (1.0f - in->settle));

    lv_canvas_fill_bg(s_canvas, bg, LV_OPA_COVER);

    /* ① 种子微光：3 层递减透明度的圆模拟辉光（比模糊便宜得多）*/
    float seed_op = in->seed * (1.0f - in->ripple);
    if (seed_op > 0.02f && in->bg < 0.9f) {
        for (int k = 3; k >= 1; k--) {
            lv_draw_rect_dsc_t d; lv_draw_rect_dsc_init(&d);
            d.radius = LV_RADIUS_CIRCLE; d.border_width = 0;
            d.bg_color = C_SEED;
            d.bg_opa = (lv_opa_t)(200 * seed_op / (k * 2));
            int r = (int)(4 * k * (1.0f + 0.4f * seed_op));
            lv_canvas_draw_rect(s_canvas, 120 - r, cy - r, r * 2, r * 2, &d);
        }
    }

    /* ② 涟漪 */
    if (in->bg < 0.9f) {
        for (int k = 0; k < 3; k++) {
            float pk = in->ripple * 3.0f - (float)k * 0.35f;
            if (pk <= 0.0f) continue;
            if (pk > 1.0f) pk = 1.0f;
            float rr = 8.0f + 70.0f * pk;
            ellipse_arc(s_canvas, 120, cy, (int)rr, (int)rr, 0.0f, 360.0f, C_SEED, 3,
                        (lv_opa_t)(150 * (1.0f - pk) * (1.0f - in->bg)));
        }
    }

    /* ⑤ 耳朵（画在脸之下，根部被脸盖住）*
     * 落位后回落 15%，避免一直"竖到顶"显得僵硬 */
    draw_ears(s_canvas, cy, in->ear * (1.0f - 0.15f * in->settle), sk, dark);

    /* ③ 轮廓：从 12 点双向展开，最后在底部合拢 */
    if (in->outline > 0.01f && in->bg < 0.98f) {
        float e = in->outline * 180.0f;
        const lv_opa_t op = LV_OPA_COVER;
        if (dark) {  /* 辉光：同一条弧画三次（外晕/中层/芯）*/
            ellipse_arc(s_canvas, 120, cy, FACE_RX, FACE_RY, -90.0f, -90.0f + e, line, 16, (lv_opa_t)(op * 25 / 100));
            ellipse_arc(s_canvas, 120, cy, FACE_RX, FACE_RY, -90.0f - e, -90.0f, line, 16, (lv_opa_t)(op * 25 / 100));
            ellipse_arc(s_canvas, 120, cy, FACE_RX, FACE_RY, -90.0f, -90.0f + e, line, 10, (lv_opa_t)(op * 60 / 100));
            ellipse_arc(s_canvas, 120, cy, FACE_RX, FACE_RY, -90.0f - e, -90.0f, line, 10, (lv_opa_t)(op * 60 / 100));
        }
        ellipse_arc(s_canvas, 120, cy, FACE_RX, FACE_RY, -90.0f, -90.0f + e, line, 8, op);
        ellipse_arc(s_canvas, 120, cy, FACE_RX, FACE_RY, -90.0f - e, -90.0f, line, 8, op);
    }

    /* ④ 填充注入：以中心扩散圆为裁剪半径 */
    if (in->fill > 0.01f) {
        float clip = FACE_RX * in->fill;
        pixel_ellipse(s_canvas, 120, cy, FACE_RX, FACE_RY, 8, sk->face, LV_OPA_COVER, clip);
    }

    /* ④′ 描边实体化：填充之后才出现，读起来是"虚影 → 实体" */
    float solid = (in->bg - 0.55f) / 0.35f;
    if (solid > 0.01f) {
        if (solid > 1.0f) solid = 1.0f;
        float clip = (FACE_RX + 12) * (in->fill > 0.55f ? (in->fill - 0.55f) / 0.45f : 0.0f);
        pixel_ellipse(s_canvas, 120, cy, FACE_RX + 4, FACE_RY + 4, 8, sk->line, LV_OPA_COVER, clip);
        pixel_ellipse(s_canvas, 120, cy, FACE_RX,     FACE_RY,     8, sk->face, LV_OPA_COVER, clip);
    }

    /* ⑥ 腮红（左右错开）*/
    {
        for (int i = 0; i < 2; i++) {
            float lp = (in->blush - (float)i * 0.05f) / 0.95f;
            if (lp <= 0.0f) continue;
            int bx = i ? 164 : 76;
            lv_draw_rect_dsc_t d; lv_draw_rect_dsc_init(&d);
            d.radius = 0; d.border_width = 0;
            d.bg_color = C_PINK; d.bg_opa = (lv_opa_t)(170 * lp);
            for (int k = 0; k < 3; k++) {
                lv_canvas_draw_rect(s_canvas, bx - 8 + k * 8, cy + 20, 6, 6, &d);
            }
        }
    }

    /* ⑦ 眼睛 + 嘴 */
    {
        float ep = in->eye;
        if (ep < 0.0f) ep = 0.0f;
        if (ep > 1.0f) ep = 1.0f;
        bool open_eye = (ep > 0.5f) && !blink;

        lv_draw_rect_dsc_t d; lv_draw_rect_dsc_init(&d);
        d.radius = 0; d.border_width = 0; d.bg_color = C_INK; d.bg_opa = LV_OPA_COVER;
        for (int k = 0; k < 2; k++) {
            int ex = k ? 142 : 98;
            if (open_eye) {
                int w = 16, h = 24, yc = cy - 8;
                lv_canvas_draw_rect(s_canvas, ex - w / 2, yc - h / 2, w, h, &d);
                /* 高光：先有眼睛，再有眼神 */
                if (ep > 0.7f) {
                    d.bg_color = C_WHITE;
                    lv_canvas_draw_rect(s_canvas, ex - 4, yc - h / 2 + 4, 3, 4, &d);
                    d.bg_color = C_INK;
                }
            } else if (ep > 0.01f) {
                /* 眯眼 / 闭眼：细横条 */
                lv_canvas_draw_rect(s_canvas, ex - 9, cy - 9, 18, 6, &d);
            }
        }
        if (ep > 0.5f) {
            int mh = (int)(2 + 6 * (ep - 0.5f) / 0.5f + 26 * energy * in->settle);
            if (mh < 2) mh = 2;
            lv_draw_rect_dsc_t m; lv_draw_rect_dsc_init(&m);
            m.radius = LV_RADIUS_CIRCLE; m.border_width = 0;
            m.bg_color = C_INK; m.bg_opa = LV_OPA_COVER;
            lv_canvas_draw_rect(s_canvas, 120 - 9, cy + 30 - mh, 18, mh * 2, &m);
        }
    }

    /* ⑨ 四角取景框 */
    corner_marks(s_canvas, (lv_opa_t)(255 * in->settle));

    lv_obj_invalidate(s_canvas);
}

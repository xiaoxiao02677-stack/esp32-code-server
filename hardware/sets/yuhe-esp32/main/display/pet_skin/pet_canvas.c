/* ============================================================
 * pet_canvas.c — 像素宠物绘制实现（直写 buffer 版）
 *
 * 移植自 hardware/sets/theme/像素宠物/main/src/pet_canvas.c，
 * 几何经 pet_layout_t 换算（240 基准 → 任意屏）。
 * 像素风：关抗锯齿、8px 网格对齐；全部画在一个 PSRAM canvas buffer 里。
 *
 * ★★ 性能架构（本文件为什么长这样）★★
 * 旧版每帧向 LVGL 派发 ~2700 个绘制任务（pixel_ellipse 逐网格格
 * lv_draw_rect + 猫耳扫描线逐行 lv_draw_line），经软件光栅器逐任务
 * 光栅化写入 PSRAM canvas；再加每帧无条件全屏 fill_bg + 全屏失效
 * → 全屏 blit + 全屏 flush。说话态 30fps 直接把 SPI 屏刷成幻灯片。
 *
 * 现在整条管线零绘制任务、零 layer 往返，直接写 RGB565 buffer：
 *   · px_span / fill_disc / fill_capsule：直写原语（自动裁剪出界）
 *   · pixel_ellipse：凸形逐网格行解析连续跨度，一行一次写
 *   · 粗弧线：采样点圆盘笔触（视觉 = 原版圆头粗线）
 *   · 背景色不变时跳过全屏填充（说话/待机态恒定）
 *   · 完成态只失效宠物包围盒（说话/眨眼），动画期才全屏失效
 * RGB565 位序经 lv_color_to_u16() 官方换算，与 LVGL 内部一致。
 * ============================================================ */
#include "pet_canvas.h"

#include <math.h>
#include <string.h>

#include "esp_heap_caps.h"
#include "esp_log.h"

static const char *TAG = "pet_canvas";

/* ── 配色（与预览 HTML 完全一致；lv_color_make 非编译期常量，运行时填）── */
#define MK(r, g, b) lv_color_make(r, g, b)

/* 各皮肤的脸 / 描边色 + 耳型 */
typedef struct { lv_color_t face, line; uint8_t ear; } skin_t;

/* 单实例 canvas 状态（由 PetSkinDisplay 持有生命周期）*/
static lv_obj_t     *s_canvas = NULL;
static uint8_t      *s_buf    = NULL;   /* RGB565 像素流 */
static uint32_t      s_stride = 0;      /* 每行字节数（含对齐）*/
static int           s_w = 0, s_h = 0;
static pet_layout_t  s_layout;

/* 背景跳过填充：上一次全屏填充色。说话/待机态 bg 恒定 → 整屏填充直接跳过 */
static uint16_t s_bg_last = 0;
static bool     s_bg_valid = false;
/* 动画→完成态过渡帧：涟漪等残迹可能在包围盒外，需要一次性全屏清屏 */
static bool s_was_animating = false;

/* 调色板索引（colors_init 填充后经 s_pal[] 取用）*/
enum { P_BG_DARK, P_BG_LIT, P_LINE_D, P_INK, P_SUB, P_PINK, P_SEED, P_WHITE, P_N };
static lv_color_t s_pal[P_N];
static skin_t     s_skins[PET_SKIN_MAX];

static void colors_init(void)
{
    s_pal[P_BG_DARK] = MK(26, 20, 18);
    s_pal[P_BG_LIT]  = MK(255, 243, 228);
    s_pal[P_LINE_D]  = MK(255, 195, 168);
    s_pal[P_INK]     = MK(74, 59, 55);
    s_pal[P_SUB]     = MK(196, 158, 138);
    s_pal[P_PINK]    = MK(255, 158, 158);
    s_pal[P_SEED]    = MK(255, 210, 180);
    s_pal[P_WHITE]   = MK(255, 255, 255);

    s_skins[PET_SKIN_CAT].face   = MK(255, 202, 184);
    s_skins[PET_SKIN_CAT].line   = MK(190, 118, 100);
    s_skins[PET_SKIN_CAT].ear    = 0;      /* 猫 · 尖耳   */

    s_skins[PET_SKIN_BEAR].face  = MK(232, 195, 154);
    s_skins[PET_SKIN_BEAR].line  = MK(168, 123, 85);
    s_skins[PET_SKIN_BEAR].ear   = 1;      /* 小熊 · 圆耳 */

    s_skins[PET_SKIN_CLOUD].face = MK(220, 235, 247);
    s_skins[PET_SKIN_CLOUD].line = MK(143, 180, 208);
    s_skins[PET_SKIN_CLOUD].ear  = 2;      /* 云兽 · 云耳 */
}

/* ── 布局换算（240 基准）─────────────────────────── */
pet_layout_t pet_layout_make(int width, int height)
{
    pet_layout_t L;
    memset(&L, 0, sizeof(L));
    L.width  = width;
    L.height = height;
    L.short_side = width < height ? width : height;
    /* 短边等比：240 基准 * 短边 / 240，四舍五入 */
    #define SC(v) (((v) * L.short_side + 120) / 240)
    L.cx          = width / 2;
    L.cy_base     = SC(PET_CY_BASE);
    L.cy_speak    = SC(PET_CY_SPEAK);
    L.face_rx     = SC(PET_FACE_RX);
    L.face_ry     = SC(PET_FACE_RY);
    L.ear_dx      = SC(PET_EAR_DX);
    L.ear_base_dy = SC(PET_EAR_BASE_DY);
    L.ear_tip_dy  = SC(PET_EAR_TIP_DY);
    L.eye_dx      = SC(PET_EYE_DX);
    L.blush_dx    = SC(PET_BLUSH_DX);
    L.grid        = SC(PET_GRID);
    if (L.grid < 4) L.grid = 4;
    #undef SC
    /* 竖屏（240x320）：宠物整体上移，给底部提示条留位；横屏居中即可 */
    if (height > width) {
        L.cy_base  -= L.short_side / 10;
        L.cy_speak -= L.short_side / 10;
    }
    return L;
}

/* ══════════════════════════════════════════════════
 * 直写原语（全部自带出界裁剪，坐标系 = canvas 内容坐标）
 * ══════════════════════════════════════════════════ */

static inline uint16_t *row_ptr(int y)
{
    return (uint16_t *)(s_buf + (size_t)y * s_stride);
}

static inline uint16_t to_u16(lv_color_t c)
{
    return lv_color_to_u16(c);
}

/* src-over 混合（+128 四舍五入，像素风格下无可见误差）*/
static inline uint16_t blend565(uint16_t dst, uint16_t src, uint16_t a)
{
    uint32_t sr = src >> 11, sg = (src >> 5) & 0x3F, sb = src & 0x1F;
    uint32_t dr = dst >> 11, dg = (dst >> 5) & 0x3F, db = dst & 0x1F;
    uint32_t ia = 256 - a;
    return (uint16_t)((((sr * a + dr * ia) + 128) >> 8 << 11)
                    | (((sg * a + dg * ia) + 128) >> 8 << 5)
                    |  ((sb * a + db * ia) + 128) >> 8);
}

/* 水平跨度：不透明 */
static void px_span(int x0, int x1, int y, uint16_t c)
{
    if (y < 0 || y >= s_h || x0 > x1) return;
    if (x0 < 0) x0 = 0;
    if (x1 >= s_w) x1 = s_w - 1;
    uint16_t *p = row_ptr(y) + x0;
    uint16_t *end = row_ptr(y) + x1;
    while (p <= end) *p++ = c;
}

/* 水平跨度：半透明（a: 0..255）*/
static void px_span_blend(int x0, int x1, int y, uint16_t c, uint16_t a)
{
    if (a >= 255) { px_span(x0, x1, y, c); return; }
    if (a == 0 || y < 0 || y >= s_h || x0 > x1) return;
    if (x0 < 0) x0 = 0;
    if (x1 >= s_w) x1 = s_w - 1;
    uint16_t *p = row_ptr(y) + x0;
    for (int x = x0; x <= x1; x++, p++) *p = blend565(*p, c, a);
}

/* 实心圆盘（弧线笔触 / 圆耳 / 种子辉光）*/
static void fill_disc(int cx, int cy, int r, uint16_t c, uint16_t a)
{
    if (r < 1) r = 1;
    int r2 = r * r;
    for (int dy = -r; dy <= r; dy++) {
        int y = cy + dy;
        if (y < 0 || y >= s_h) continue;
        int dx = (int)sqrtf((float)(r2 - dy * dy));
        if (a >= 255) px_span(cx - dx, cx + dx, y, c);
        else          px_span_blend(cx - dx, cx + dx, y, c, a);
    }
}

/* 实心矩形（像素风块）*/
static void fill_rect(int x0, int y0, int w, int h, uint16_t c, uint16_t a)
{
    for (int y = y0; y < y0 + h; y++) {
        if (a >= 255) px_span(x0, x0 + w - 1, y, c);
        else          px_span_blend(x0, x0 + w - 1, y, c, a);
    }
}

/* 胶囊（圆角矩形，嘴部）*/
static void fill_capsule(int x0, int y0, int w, int h, uint16_t c)
{
    if (w <= 0 || h <= 0) return;
    int r = w / 2;
    if (h <= w) {  /* 矮胶囊：中段矩形 + 上下圆 */
        fill_rect(x0, y0 + r, w, h - 2 * r + 1, c, 255);
        fill_disc(x0 + r, y0 + r, r, c, 255);
        fill_disc(x0 + r, y0 + h - r - 1, r, c, 255);
    } else {
        fill_rect(x0, y0, w, h, c, 255);
    }
}

/* ── 像素椭圆：凸形逐网格行解析连续跨度 ──────────────
 * 视觉与旧版逐格判定完全一致（同一判据），但一行只写一次。
 * clip_r >= 0 时以中心扩散圆裁剪（填充注入动画）。*/
static void pixel_ellipse(int cx, int cy, int rx, int ry,
                          int grid, lv_color_t col, lv_opa_t opa, float clip_r)
{
    if (rx <= 0 || ry <= 0 || grid <= 0) return;
    const uint16_t c16 = to_u16(col);
    const bool cover = (opa >= LV_OPA_COVER);
    const float clip2 = clip_r >= 0.0f ? clip_r * clip_r : -1.0f;

    int y0 = ((cy - ry) / grid) * grid;
    for (int y = y0; y <= cy + ry; y += grid) {
        const float dyf = (float)(y + grid / 2 - cy) / (float)ry;
        if (dyf <= -1.0f || dyf >= 1.0f) continue;
        const float dxw = rx * sqrtf(1.0f - dyf * dyf);
        int xs = (int)floorf((float)cx - dxw);
        int xe = (int)ceilf((float)cx + dxw);
        if (clip2 >= 0.0f) {
            const float ddy = (float)(y + grid / 2 - cy);
            if (ddy * ddy >= clip2) continue;
            const float ddx = sqrtf(clip2 - ddy * ddy);
            int cxs = (int)ceilf((float)cx - ddx);
            int cxe = (int)floorf((float)cx + ddx);
            if (xs < cxs) xs = cxs;
            if (xe > cxe) xe = cxe;
        }
        if (xs > xe) continue;
        if (cover) px_span(xs, xe, y, c16);
        else       px_span_blend(xs, xe, y, c16, opa);
    }
}

/* ── 椭圆弧：采样点圆盘笔触（视觉 = 圆头粗线）────────
 * 步数按弧长自适应：相邻笔触圆盘重叠 ≥ 50%，无缝且不 oversample。*/
static void ellipse_arc(int cx, int cy, int rx, int ry,
                        float a0_deg, float a1_deg, lv_color_t col,
                        int width, lv_opa_t opa)
{
    if (a1_deg - a0_deg < 1.0f) return;
    const uint16_t c16 = to_u16(col);
    int r = width / 2;
    if (r < 1) r = 1;
    const float arc_len = (a1_deg - a0_deg) * 0.0174533f * (float)(rx + ry) * 0.5f;
    int steps = (int)(arc_len / (r * 0.5f));
    if (steps < 8) steps = 8;
    if (steps > 220) steps = 220;
    for (int i = 0; i <= steps; i++) {
        const float ang = (a0_deg + (a1_deg - a0_deg) * (float)i / (float)steps)
                          * 0.0174533f;
        fill_disc((int)(cx + rx * cosf(ang)), (int)(cy + ry * sinf(ang)), r, c16, opa);
    }
}

/* ── 实心三角（猫耳）：水平扫描线直写 ──────────────── */
static void tri(const lv_point_t *p, lv_color_t col, lv_opa_t opa)
{
    lv_point_t t[3] = {p[0], p[1], p[2]};
    if (t[0].y > t[1].y) { lv_point_t tmp = t[0]; t[0] = t[1]; t[1] = tmp; }
    if (t[1].y > t[2].y) { lv_point_t tmp = t[1]; t[1] = t[2]; t[2] = tmp; }
    if (t[0].y > t[1].y) { lv_point_t tmp = t[0]; t[0] = t[1]; t[1] = tmp; }

    const uint16_t c16 = to_u16(col);
    for (int y = t[0].y; y <= t[2].y; y++) {
        if (y < 0 || y >= s_h) continue;
        float xa = (t[2].y != t[0].y)
            ? t[0].x + (float)(y - t[0].y) * (t[2].x - t[0].x) / (t[2].y - t[0].y)
            : (float)t[0].x;
        float xb;
        if (y < t[1].y && t[1].y != t[0].y) {
            xb = t[0].x + (float)(y - t[0].y) * (t[1].x - t[0].x) / (t[1].y - t[0].y);
        } else if (t[2].y != t[1].y) {
            xb = t[1].x + (float)(y - t[1].y) * (t[2].x - t[1].x) / (t[2].y - t[1].y);
        } else {
            xb = (y < t[1].y) ? (float)t[0].x : (float)t[1].x;
        }
        if (xa > xb) { float tmp = xa; xa = xb; xb = tmp; }
        if (opa >= LV_OPA_COVER) px_span((int)xa, (int)xb, y, c16);
        else                     px_span_blend((int)xa, (int)xb, y, c16, opa);
    }
}

/* ── 耳朵：三种形状，随进度缩放 ─────────────────── */
static void draw_ears(int cy, float scale, const skin_t *sk, bool dark)
{
    if (scale <= 0.01f) return;
    lv_color_t line = dark ? s_pal[P_LINE_D] : sk->line;
    lv_color_t face = sk->face;
    const int cx = s_layout.cx;
    const int ear_dx      = s_layout.ear_dx;
    const int base_dy     = s_layout.ear_base_dy;
    const int tip_dy      = s_layout.ear_tip_dy;
    const int outer_w     = (s_layout.short_side * 27 + 120) / 240;  /* 27px 基准 */
    const int inner_w     = (s_layout.short_side * 19 + 120) / 240;
    const int base_half   = (s_layout.short_side * 6  + 120) / 240;
    const int ear_radius  = (s_layout.short_side * 15 + 120) / 240;

    for (int k = 0; k < 2; k++) {
        int sgn = k ? 1 : -1;
        int sx = cx + sgn * ear_dx;
        int base_y = cy + base_dy;
        int tip_y  = cy + tip_dy;
        /* 缩放中心：耳朵根部 */
        int ax = sx + sgn * (s_layout.short_side * 10 + 120) / 240;
        int ay = tip_y + (s_layout.short_side * 22 + 120) / 240;

        if (sk->ear == 0) {                    /* 猫 · 尖耳（双层三角）*/
            lv_point_t outer[3] = {
                { sx - base_half, base_y }, { sx + base_half, base_y }, { sx + sgn * outer_w, tip_y }
            };
            lv_point_t inner[3] = {
                { sx - 1, base_y }, { sx + base_half - 1, base_y }, { sx + sgn * inner_w, tip_y + s_layout.grid }
            };
            for (int i = 0; i < 3; i++) {
                outer[i].x = (int)((outer[i].x - ax) * scale + ax);
                outer[i].y = (int)((outer[i].y - ay) * scale + ay);
                inner[i].x = (int)((inner[i].x - ax) * scale + ax);
                inner[i].y = (int)((inner[i].y - ay) * scale + ay);
            }
            tri(outer, line, LV_OPA_COVER);
            tri(inner, face, LV_OPA_COVER);
        } else if (sk->ear == 1) {             /* 小熊 · 圆耳 */
            int ex = sx + sgn * (s_layout.short_side * 17 + 120) / 240;
            int ey = tip_y + (s_layout.short_side * 12 + 120) / 240;
            int r  = (int)(ear_radius * scale);
            if (r < 2) r = 2;
            ex = (int)((ex - ax) * scale + ax);
            ey = (int)((ey - ay) * scale + ay);
            fill_disc(ex, ey, r, to_u16(line), 255);
            int inner_r = r - s_layout.grid / 2;
            if (inner_r < 1) inner_r = 1;
            fill_disc(ex, ey, inner_r, to_u16(face), 255);
        } else {                               /* 云兽 · 三圆叠云 */
            for (int i = 0; i < 3; i++) {
                int rr = (int)((ear_radius - i * s_layout.grid / 4) * scale);
                if (rr < 2) rr = 2;
                int cxx = (int)((sx + sgn * (i * s_layout.grid + s_layout.grid / 2) - ax) * scale + ax);
                int cyy = (int)((base_y - (s_layout.short_side * 18 + 120) / 240 + i * s_layout.grid / 2 - ay) * scale + ay);
                fill_disc(cxx, cyy, rr, to_u16(line), 255);
                int inner_r = rr - s_layout.grid / 2;
                if (inner_r < 1) inner_r = 1;
                fill_disc(cxx, cyy, inner_r, to_u16(face), 255);
            }
        }
    }
}

/* ── 创建 canvas ─────────────────────────────────── */
lv_obj_t *pet_canvas_create(lv_obj_t *parent, const pet_layout_t *layout)
{
    colors_init();
    s_layout = *layout;
    s_w = s_layout.width;
    s_h = s_layout.height;

    /* stride 走官方换算（RGB565，含对齐），按真实字节数分配 */
    s_stride = lv_draw_buf_width_to_stride((uint32_t)s_w, LV_COLOR_FORMAT_RGB565);
    size_t bytes = (size_t)s_stride * s_h;
    s_buf = heap_caps_malloc(bytes, MALLOC_CAP_SPIRAM);
    if (!s_buf) {
        ESP_LOGW(TAG, "PSRAM 分配失败，退回内部 RAM");
        s_buf = heap_caps_malloc(bytes, MALLOC_CAP_8BIT);
    }
    if (!s_buf) { ESP_LOGE(TAG, "canvas buffer 分配失败"); return NULL; }

    s_canvas = lv_canvas_create(parent);
    lv_obj_set_size(s_canvas, s_w, s_h);
    lv_obj_center(s_canvas);
    lv_canvas_set_buffer(s_canvas, s_buf, s_w, s_h, LV_COLOR_FORMAT_RGB565);

    /* 初次底色直写 */
    s_bg_valid = false;
    s_was_animating = false;
    const uint16_t bg0 = to_u16(s_pal[P_BG_DARK]);
    for (int y = 0; y < s_h; y++) px_span(0, s_w - 1, y, bg0);
    s_bg_last = bg0;
    s_bg_valid = true;
    return s_canvas;
}

void pet_canvas_destroy(void)
{
    if (s_canvas) {
        lv_obj_delete(s_canvas);
        s_canvas = NULL;
    }
    if (s_buf) {
        heap_caps_free(s_buf);
        s_buf = NULL;
    }
    s_bg_valid = false;
}

bool pet_canvas_ready(void) { return s_canvas != NULL; }

/* ── 宠物包围盒（完成态脏区 + 局部清屏）────────────── */
static void pet_bbox(lv_area_t *a)
{
    const int g = s_layout.grid;
    const int pad = g + 4;
    const int top = s_layout.cy_base + s_layout.ear_tip_dy - g * 2;
    const int bot = s_layout.cy_speak + s_layout.face_ry;
    a->x1 = s_layout.cx - s_layout.face_rx - pad;
    a->x2 = s_layout.cx + s_layout.face_rx + pad;
    a->y1 = top - pad;
    a->y2 = bot + pad;
}

/* ── 主渲染 ──────────────────────────────────────── */
void pet_canvas_render(const pet_boot_prog_t *in, float energy,
                       pet_skin_id_t skin_id, pet_expr_t expr, bool blink)
{
    if (!s_canvas) return;

    /* 已完成时全部置 1 */
    pet_boot_prog_t full;
    if (!in) {
        memset(&full, 0, sizeof(full));
        full.seed = full.ripple = full.outline = full.fill = full.bg =
        full.ear = full.blush = full.eye = full.settle = 1.0f;
        in = &full;
    }

    const skin_t *sk = &s_skins[skin_id % PET_SKIN_MAX];
    bool dark = in->bg < 0.55f;
    lv_color_t line = lv_color_mix(s_pal[P_LINE_D], sk->line, (uint8_t)(in->bg * 255));
    lv_color_t bg   = lv_color_mix(s_pal[P_BG_DARK], s_pal[P_BG_LIT], (uint8_t)(in->bg * 255));

    const int cx = s_layout.cx;
    /* 宠物中心：回应时下移让位气泡，落位时回归 */
    int cy = s_layout.cy_base + (int)((float)(s_layout.cy_speak - s_layout.cy_base)
                                      * in->bubble * (1.0f - in->settle));

    /* 动画期（bg 渐变 / 位移 / 涟漪全屏元素）= 全屏帧；完成态 = 包围盒帧。
     * 过渡帧（上一帧还是动画）也按全屏处理：涟漪/位移残迹在包围盒外。 */
    const bool animating = (in->bg < 0.999f) || (in->settle < 0.999f);
    const bool full_frame = animating || s_was_animating;

    if (full_frame) {
        /* 动画期无条件全屏填充：色值在渐变，且涟漪/种子等元素会被上一帧
         * 残影污染——绝不能因色值相同跳过。 */
        uint16_t bg16 = to_u16(bg);
        for (int y = 0; y < s_h; y++) px_span(0, s_w - 1, y, bg16);
        s_bg_last = bg16;
        s_bg_valid = true;
    } else {
        /* 完成态：只清宠物包围盒（擦掉上一帧的嘴/眼残影），背景保持 */
        lv_area_t box;
        pet_bbox(&box);
        fill_rect(box.x1, box.y1, box.x2 - box.x1 + 1, box.y2 - box.y1 + 1, to_u16(bg), 255);
    }

    /* ① 种子微光：3 层递减透明度的圆盘模拟辉光 */
    float seed_op = in->seed * (1.0f - in->ripple);
    if (seed_op > 0.02f && in->bg < 0.9f) {
        for (int k = 3; k >= 1; k--) {
            int r = (int)(s_layout.grid / 2 * k * (1.0f + 0.4f * seed_op));
            if (r < 1) r = 1;
            uint16_t opa = (uint16_t)(200 * seed_op / (k * 2));
            fill_disc(cx, cy, r, to_u16(s_pal[P_SEED]), opa);
        }
    }

    /* ② 涟漪 */
    if (in->bg < 0.9f) {
        for (int k = 0; k < 3; k++) {
            float pk = in->ripple * 3.0f - (float)k * 0.35f;
            if (pk <= 0.0f) continue;
            if (pk > 1.0f) pk = 1.0f;
            float rr = s_layout.grid + 70.0f * pk * s_layout.short_side / 240.0f;
            ellipse_arc(cx, cy, (int)rr, (int)rr, 0.0f, 360.0f, s_pal[P_SEED], 3,
                        (lv_opa_t)(150 * (1.0f - pk) * (1.0f - in->bg)));
        }
    }

    /* ⑤ 耳朵（画在脸之下，根部被脸盖住；落位后回落 15%）*/
    draw_ears(cy, in->ear * (1.0f - 0.15f * in->settle), sk, dark);

    /* ③ 轮廓：从 12 点双向展开，最后在底部合拢 */
    if (in->outline > 0.01f && in->bg < 0.98f) {
        float e = in->outline * 180.0f;
        const lv_opa_t op = LV_OPA_COVER;
        if (dark) {  /* 辉光：同一条弧画三次（外晕/中层/芯）*/
            ellipse_arc(cx, cy, s_layout.face_rx, s_layout.face_ry, -90.0f, -90.0f + e, line, 16, (lv_opa_t)(op * 25 / 100));
            ellipse_arc(cx, cy, s_layout.face_rx, s_layout.face_ry, -90.0f - e, -90.0f, line, 16, (lv_opa_t)(op * 25 / 100));
            ellipse_arc(cx, cy, s_layout.face_rx, s_layout.face_ry, -90.0f, -90.0f + e, line, 10, (lv_opa_t)(op * 60 / 100));
            ellipse_arc(cx, cy, s_layout.face_rx, s_layout.face_ry, -90.0f - e, -90.0f, line, 10, (lv_opa_t)(op * 60 / 100));
        }
        ellipse_arc(cx, cy, s_layout.face_rx, s_layout.face_ry, -90.0f, -90.0f + e, line, 8, op);
        ellipse_arc(cx, cy, s_layout.face_rx, s_layout.face_ry, -90.0f - e, -90.0f, line, 8, op);
    }

    /* ④ 填充注入：以中心扩散圆为裁剪半径 */
    if (in->fill > 0.01f) {
        float clip = s_layout.face_rx * in->fill;
        pixel_ellipse(cx, cy, s_layout.face_rx, s_layout.face_ry,
                      s_layout.grid, sk->face, LV_OPA_COVER, clip);
    }

    /* ④′ 描边实体化：填充之后才出现 */
    float solid = (in->bg - 0.55f) / 0.35f;
    if (solid > 0.01f) {
        if (solid > 1.0f) solid = 1.0f;
        float clip = (s_layout.face_rx + 12) * (in->fill > 0.55f ? (in->fill - 0.55f) / 0.45f : 0.0f);
        pixel_ellipse(cx, cy, s_layout.face_rx + s_layout.grid / 2, s_layout.face_ry + s_layout.grid / 2,
                      s_layout.grid, sk->line, LV_OPA_COVER, clip);
        pixel_ellipse(cx, cy, s_layout.face_rx, s_layout.face_ry,
                      s_layout.grid, sk->face, LV_OPA_COVER, clip);
    }

    /* ⑥ 腮红（左右错开）*/
    for (int i = 0; i < 2; i++) {
        float lp = (in->blush - (float)i * 0.05f) / 0.95f;
        if (lp <= 0.0f) continue;
        int bx = i ? cx + s_layout.blush_dx : cx - s_layout.blush_dx;
        int cell = s_layout.grid * 3 / 4;
        if (cell < 1) cell = 1;
        uint16_t opa = (uint16_t)(170 * lp);
        for (int k = 0; k < 3; k++) {
            int px = bx - s_layout.grid + k * s_layout.grid;
            int py = cy + s_layout.short_side * 20 / 240;
            fill_rect(px, py, cell, cell, to_u16(s_pal[P_PINK]), opa);
        }
    }

    /* ⑦ 眼睛 + 嘴（表情五态）*/
    {
        float ep = in->eye;
        if (ep < 0.0f) ep = 0.0f;
        if (ep > 1.0f) ep = 1.0f;
        bool open_eye = (ep > 0.5f) && !blink;
        const int eye_w   = s_layout.grid * 2;           /* 基准 16 */
        const int eye_h   = s_layout.grid * 3;           /* 基准 24 */
        const int eye_yc  = cy - s_layout.grid;          /* 基准 cy-8 */
        const int brow_dy = s_layout.grid * 2;           /* 基准 16 */

        const uint16_t ink = to_u16(s_pal[P_INK]);
        for (int k = 0; k < 2; k++) {
            int ex = k ? cx + s_layout.eye_dx : cx - s_layout.eye_dx;
            if (open_eye) {
                fill_rect(ex - eye_w / 2, eye_yc - eye_h / 2, eye_w, eye_h, ink, 255);
                if (ep > 0.7f) {  /* 高光 */
                    int hw = s_layout.grid * 3 / 8;
                    if (hw < 1) hw = 1;
                    fill_rect(ex - eye_w / 4, eye_yc - eye_h / 2 + eye_h / 6,
                              hw, eye_h / 2, to_u16(s_pal[P_WHITE]), 255);
                }
            } else if (ep > 0.01f) {
                /* 闭眼细横条 */
                int lw = eye_w * 5 / 8;
                int lh = s_layout.grid * 3 / 4;
                if (lh < 1) lh = 1;
                int ly = cy - s_layout.grid - 1;
                fill_rect(ex - lw, ly, lw * 2, lh, ink, 255);
            }
            /* 表情附加笔画（仅完成态且睁眼时）*/
            if (in->settle > 0.9f && ep > 0.7f) {
                switch (expr) {
                case PET_EXPR_HAPPY:    /* 笑眼：外侧小括号弧 */
                    ellipse_arc(ex, eye_yc + s_layout.grid, eye_w / 2 + s_layout.grid / 2,
                                eye_h / 3, k ? 0.0f : 180.0f, k ? 90.0f : 270.0f, s_pal[P_INK], 3, LV_OPA_COVER);
                    break;
                case PET_EXPR_SAD:      /* 下垂眼：眉线外侧向下 */
                    {
                        int y0 = eye_yc - eye_h / 2 - brow_dy;
                        fill_rect(ex - eye_w, y0, eye_w * 2, 2, ink, 255);
                        fill_rect(ex + (k ? -eye_w : eye_w - s_layout.grid / 2), y0,
                                  s_layout.grid / 2, s_layout.grid, ink, 255);
                    }
                    break;
                case PET_EXPR_SURPRISE: /* 圆睁：黑瞳缩小 */
                    {
                        int shrink = 2;
                        fill_rect(ex - eye_w / 2 + shrink, eye_yc - eye_h / 2 + shrink,
                                  eye_w - shrink * 2, eye_h - shrink * 2,
                                  to_u16(s_pal[P_BG_DARK]), 255);
                    }
                    break;
                case PET_EXPR_SLEEPY:   /* 困倦：上眼睑压下半格 */
                    {
                        int lh = s_layout.grid / 2;
                        if (lh < 1) lh = 1;
                        fill_rect(ex - eye_w / 2, eye_yc - eye_h / 2, eye_w, lh,
                                  to_u16(sk->face), 255);
                    }
                    break;
                case PET_EXPR_NEUTRAL:
                default:
                    break;
                }
            }
        }
        /* 嘴：能量驱动高度 + 表情微调 */
        if (ep > 0.5f) {
            int mh = (int)(2 + 6 * (ep - 0.5f) / 0.5f + 26 * energy * in->settle);
            if (expr == PET_EXPR_HAPPY) mh += s_layout.grid / 2;      /* 笑：嘴巴更大 */
            if (expr == PET_EXPR_SAD)   mh = s_layout.grid / 2;       /* 难过：嘴角下沉（用短横条）*/
            if (mh < 2) mh = 2;
            int mx = cx - s_layout.grid - 1;
            int my = cy + s_layout.short_side * 30 / 240 - mh;
            fill_capsule(mx, my, s_layout.grid * 2 + 2, mh * 2, ink);
        }
    }

    /* 失效：全屏帧失效全屏，完成态只失效宠物包围盒（blit/flush 量降 75%）*/
    if (full_frame) {
        lv_obj_invalidate(s_canvas);
    } else {
        lv_area_t box;
        pet_bbox(&box);
        lv_obj_invalidate_area(s_canvas, &box);
    }
    s_was_animating = animating;
}

void pet_canvas_render_idle(float energy, pet_skin_id_t skin_id, pet_expr_t expr, bool blink)
{
    pet_canvas_render(NULL, energy, skin_id, expr, blink);
}

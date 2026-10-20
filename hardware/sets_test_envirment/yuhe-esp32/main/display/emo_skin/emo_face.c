/* ============================================================
 * emo_face.c — EMOpet 风格机器人发光眼（主固件移植版）
 *
 * 移植自 hardware/sets/theme/EMOpet/main/src/emopet_face.c（240x240）。
 * 设计原样保留：情绪 = 形状/大小/倾角/辉光四维表达；切换走
 * "闭眼→换形→睁眼"300ms 转场；辉光 = 尺寸递减+透明度递增三层
 * 模拟（ESP32 上绝不做高斯模糊）；零位图全参数化。
 *
 * ★★ 与源工程的差异（为什么这样改）★★
 * 1) 绘制层：源用 lv_canvas_draw_rect/line/polygon/arc——LVGL 9.5
 *    已删除这些旧 API，且绘制任务管线在 ESP32-S3 上每帧数百任务
 *    卡成 PPT（2026-10-19 像素宠物同款教训）。本文件全部直写
 *    RGB565 buffer：px_span/blend565/fill_blob/stroke_seg/fill_poly，
 *    零绘制任务、零 layer 往返。
 * 2) 几何：源写死 SCR_W/H=240；本文件经 emo_layout_t 换算，适配
 *    240 圆屏 / 320x240 横屏 / 240x320 竖屏（眼距相对屏心对称）。
 * 3) 脏区：源每帧 fill_bg 全屏 + invalidate 全屏；本文件跟踪
 *    s_dirty（上帧失效区 ∪ 本帧绘制区）局部清+局部失效，
 *    20MHz SPI 大屏的 flush 量降 ~60%。反射光晕用行裁剪版
 *    fill_disc 只重画脏区内的部分。
 * 4) 顶部点阵状态栏（时间/WiFi/电量）不移植——主固件基类 chrome
 *    已有；配网二维码（EM_QR）同理走基类系统卡片。
 * 5) 底部声波条保留，但频段数据改由 SpeakingEnergy 拟态驱动
 *    （原版 overlay_get_bands 的真实 RMS 链路不进主题层）。
 * ============================================================ */
#include "emo_face.h"

#include <math.h>
#include <string.h>

#include "esp_heap_caps.h"
#include "esp_log.h"
#include "esp_random.h"

static const char *TAG = "emo_face";

#define MK(r, g, b) lv_color_make(r, g, b)

/* ── 声波条参数（与源工程一致，240 基准经 SC 换算）── */
#define EMO_WAVE_BARS   22
#define EMO_WAVE_BW      5
#define EMO_WAVE_GAP     3

/* ── 表情表（emo_id_t 15 态；源表去掉 BOOT/WIFI/OFFLINE/QR）──
 * 与源 emopet_face.c 的 EMO[] 数值逐项一致（240 基准像素）。 */
static const emo_t EMO[EMO_MAX] = {
    /* id            shape      w     h   bend  glow  offY  tilt  pulse blush */
    [EMO_IDLE]     = { EM_DOT,    54,  62,  0.0f, 1.00f,   0, 0.0f, 0, 0 },
    [EMO_LISTEN]   = { EM_DOT,    60,  70,  0.0f, 1.35f,  -2, 0.0f, 0, 0 },
    [EMO_SPEAK]    = { EM_DOT,    56,  64,  0.0f, 1.20f,   0, 0.0f, 0, 0 },
    [EMO_HAPPY]    = { EM_ARC,    50,  18,  1.0f, 1.25f,   2, 0.0f, 0, 0 },
    [EMO_LOVE]     = { EM_HEART,  48,  45,  0.0f, 1.55f,   0, 0.0f, 0, 0 },
    [EMO_SLEEPY]   = { EM_ARC,    46,  10, 0.35f, 0.62f,   4, 0.0f, 0, 0 },
    [EMO_SAD]      = { EM_ARC,    44,  15, -0.85f, 0.75f,  2, -0.3f, 0, 0 },
    [EMO_SURPRISE] = { EM_DOT,    48,  78,  0.0f, 1.60f,  -4, 0.0f, 0, 0 },
    [EMO_ANGRY]    = { EM_DOT,    56,  46,  0.0f, 1.45f,   0, 0.55f, 0, 0 },
    [EMO_WINK]     = { EM_DOT,    54,  58,  0.0f, 1.20f,   0, 0.0f, 0, 0 },
    [EMO_STAR]     = { EM_STAR,   50,  48,  0.0f, 1.55f,   0, 0.0f, 0, 0 },
    [EMO_DIZZY]    = { EM_SPIRAL, 44,  44,  0.0f, 0.95f,   0, 0.0f, 0, 0 },
    [EMO_THINK]    = { EM_DOT,    50,  50,  0.0f, 1.05f,  -8, 0.28f, 0, 0 },
    [EMO_SHY]      = { EM_DOT,    50,  46,  0.0f, 1.10f,   6, 0.0f, 0, 1 },
    [EMO_LOWBATT]  = { EM_DOT,    46,  40,  0.0f, 0.45f,   0, 0.0f, 1, 0 },
};

/* 眨眼用的右眼覆盖（wink：左眼 dot，右眼笑弧）——与源一致 */
typedef struct {
    bool  use;
    emo_t e;
} r_override_t;
static const r_override_t R_OVER[EMO_MAX] = {
    [EMO_WINK] = { true, { EM_ARC, 54, 18, 1.0f, 1.20f, 0, 0.0f, 0, 0 } },
};

/* ── 运行时状态 ──────────────────────────────────── */
static lv_obj_t   *s_canvas = NULL;
static uint8_t    *s_buf    = NULL;   /* RGB565 像素流 */
static uint32_t    s_stride = 0;
static int         s_w = 0, s_h = 0;
static emo_layout_t s_layout;

static lv_color_t s_main;             /* 主色（辉光）*/
static lv_color_t s_core;             /* 芯色（近白）*/

static emo_t       s_cur, s_tgt;
static uint8_t     s_cur_id = EMO_IDLE;
static float       s_blink_t = -1.0f;
static bool        s_blink = false;
static float       s_switch_t = 0.0f;
static bool        s_switching = false;
static em_shape_t  s_pending_shape = EM_DOT;
static bool        s_pending_r = false;
static int         s_next_blink = 90;
static float       s_energy = 0.0f;
static float       s_time = 0.0f;
static bool        s_wave = false, s_auto_blink = true, s_breathe = true;
static bool        s_batt_low = false;

/* 脏区跟踪：局部清屏 + 局部失效的核心。 */
static lv_area_t   s_dirty = { 0, 0, 0, 0 };
static bool        s_dirty_valid = false;
static bool        s_full_redraw = true;   /* 换色/关声波等残迹场景 */

/* 隔帧分频：静止态 15fps，眨眼/转场/说话自动全速 30fps */
static bool        s_skip = false;

/* ══════════════════════════════════════════════════
 * 直写原语（自带出界裁剪，坐标系 = canvas 内容坐标）
 * ══════════════════════════════════════════════════ */

static inline uint16_t *row_ptr(int y)
{
    return (uint16_t *)(s_buf + (size_t)y * s_stride);
}

static inline uint16_t to_u16(lv_color_t c)
{
    return lv_color_to_u16(c);
}

/* src-over 混合（+128 四舍五入）*/
static inline uint16_t blend565(uint16_t dst, uint16_t src, uint16_t a)
{
    uint32_t sr = src >> 11, sg = (src >> 5) & 0x3F, sb = src & 0x1F;
    uint32_t dr = dst >> 11, dg = (dst >> 5) & 0x3F, db = dst & 0x1F;
    uint32_t ia = 256 - a;
    return (uint16_t)((((sr * a + dr * ia) + 128) >> 8 << 11)
                    | (((sg * a + dg * ia) + 128) >> 8 << 5)
                    | (((sb * a + db * ia) + 128) >> 8));
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

/* 实心矩形 */
static void fill_rect(int x0, int y0, int w, int h, uint16_t c, uint16_t a)
{
    if (w <= 0 || h <= 0) return;
    for (int y = y0; y < y0 + h; y++) {
        if (a >= 255) px_span(x0, x0 + w - 1, y, c);
        else          px_span_blend(x0, x0 + w - 1, y, c, a);
    }
}

/* 实心圆盘（可带 y 裁剪范围——反射光晕只重画脏区内部分用）*/
static void fill_disc_y(int cx, int cy, int r, uint16_t c, uint16_t a,
                        int y_min, int y_max)
{
    if (r < 1) r = 1;
    int r2 = r * r;
    int lo = -r, hi = r;
    if (y_min > lo) lo = y_min - cy;
    if (y_max < hi) hi = y_max - cy;
    for (int dy = lo; dy <= hi; dy++) {
        int y = cy + dy;
        if (y < 0 || y >= s_h) continue;
        int dx = (int)sqrtf((float)(r2 - dy * dy));
        if (a >= 255) px_span(cx - dx, cx + dx, y, c);
        else          px_span_blend(cx - dx, cx + dx, y, c, a);
    }
}

static void fill_disc(int cx, int cy, int r, uint16_t c, uint16_t a)
{
    fill_disc_y(cx, cy, r, c, a, -1, s_h);
}

/* 圆角胶囊/椭圆眼体：radius = min(w,h)/2，视觉 = 源 draw_blob
 * （LVGL 大圆角矩形）。宽>高 → 横向泳池形；高>宽 → 竖向。 */
static void fill_blob(int cx, int cy, int w, int h, uint16_t c, uint16_t a)
{
    if (w < 2 || h < 2) {
        fill_rect(cx - w / 2, cy - h / 2, w, h, c, a);
        return;
    }
    int r = (w < h ? w : h) / 2;
    int x0 = cx - w / 2, y0 = cy - h / 2;
    if (w >= h) {
        fill_rect(x0 + r, y0, w - 2 * r, h, c, a);
        fill_disc(x0 + r, cy, r, c, a);
        fill_disc(x0 + w - r - 1, cy, r, c, a);
    } else {
        fill_rect(x0, y0 + r, w, h - 2 * r, c, a);
        fill_disc(cx, y0 + r, r, c, a);
        fill_disc(cx, y0 + h - r - 1, r, c, a);
    }
}

/* 线段笔触：沿段以 r*0.45 步距落圆盘，相邻盘重叠 >55% 视觉连续
 * （替代源 lv_canvas_draw_line 的圆头粗线）*/
static void stroke_seg(float x0, float y0, float x1, float y1,
                       int r, uint16_t c, uint16_t a)
{
    float dx = x1 - x0, dy = y1 - y0;
    float len = sqrtf(dx * dx + dy * dy);
    int steps = (int)(len / (r * 0.45f)) + 1;
    if (steps > 220) steps = 220;
    for (int i = 0; i <= steps; i++) {
        float t = (float)i / (float)steps;
        fill_disc((int)(x0 + dx * t), (int)(y0 + dy * t), r, c, a);
    }
}

/* 简单多边形填充（even-odd 扫描线；爱心 6 点 / 五角星 10 点够用）*/
static void fill_poly(const float *xs, const float *ys, int n,
                      uint16_t c, uint16_t a)
{
    if (n < 3) return;
    float ymin = ys[0], ymax = ys[0];
    for (int i = 1; i < n; i++) {
        if (ys[i] < ymin) ymin = ys[i];
        if (ys[i] > ymax) ymax = ys[i];
    }
    float xint[14];
    for (int y = (int)ceilf(ymin); y <= (int)floorf(ymax); y++) {
        if (y < 0 || y >= s_h) continue;
        int cnt = 0;
        for (int i = 0; i < n; i++) {
            int j = (i + 1) % n;
            float yi = ys[i], yj = ys[j];
            if ((yi <= (float)y && yj > (float)y) || (yj <= (float)y && yi > (float)y)) {
                if (cnt < 14) {
                    xint[cnt++] = xs[i] + ((float)y - yi) * (xs[j] - xs[i]) / (yj - yi);
                }
            }
        }
        /* 插入排序（cnt ≤ 顶点数，个位数）*/
        for (int i = 1; i < cnt; i++) {
            float v = xint[i];
            int k = i - 1;
            while (k >= 0 && xint[k] > v) { xint[k + 1] = xint[k]; k--; }
            xint[k + 1] = v;
        }
        for (int k = 0; k + 1 < cnt; k += 2) {
            px_span_blend((int)ceilf(xint[k]), (int)floorf(xint[k + 1]), y, c, a);
        }
    }
}

/* 二次贝塞尔采样（弯月笑眼/哭眼）——与源 quad_points 一致 */
#define BEZ_N 16
static void quad_bezier(float *xs, float *ys,
                        float x0, float y0, float xc, float yc,
                        float x1, float y1)
{
    for (int i = 0; i < BEZ_N; i++) {
        float t = (float)i / (float)(BEZ_N - 1);
        float mt = 1.0f - t;
        xs[i] = mt * mt * x0 + 2 * mt * t * xc + t * t * x1;
        ys[i] = mt * mt * y0 + 2 * mt * t * yc + t * t * y1;
    }
}

/* ══════════════════════════════════════════════════
 * 布局换算（240 基准 → 实际屏）
 * ══════════════════════════════════════════════════ */
emo_layout_t emo_layout_make(int width, int height)
{
    emo_layout_t L;
    memset(&L, 0, sizeof(L));
    L.width = width;
    L.height = height;
    L.short_side = width < height ? width : height;
    #define SC(v) (((v) * L.short_side + 120) / 240)
    /* 眼距 80 基准（中心 ±40），相对屏心对称而非写死绝对坐标：
     * 240 屏 → 80/160，320 横屏 → 120/200，均居中 */
    L.eye_lx = width / 2 - SC(40);
    L.eye_rx = width / 2 + SC(40);
    L.eye_cy = SC(EMO_EYE_CY);
    L.blush_dy = SC(EMO_BLUSH_DY);
    L.wave_base = height - SC(30);   /* 贴底，避开基类 hint 条（底部 -12）*/
    L.scale = (float)L.short_side / 240.0f;
    /* 竖屏（240x320）：眼部整体上移，给底部气泡/提示留位 */
    if (height > width) {
        L.eye_cy -= L.short_side / 10;
    }
    #undef SC
    return L;
}

/* ══════════════════════════════════════════════════
 * 眼睛绘制
 * ══════════════════════════════════════════════════ */

/* 可爱版圆眼：外晕 → 主体 → 亮芯 → 主高光 → 次高光。
 * ★ 主高光是「灯」和「眼睛」的分界线——没有它只是两颗 LED，
 *   有了它才是一双会说话的眼睛。（源码注释原样保留精神）*/
static void draw_cute_eye(int cx, int cy, float w, float h, float g)
{
    const uint16_t mc = to_u16(s_main);
    const uint16_t core = to_u16(lv_color_mix(s_main, lv_color_white(), 150));
    const uint16_t white = to_u16(lv_color_white());
    int W = (int)w, H = (int)h;
    if (W < 2 || H < 2) return;

    fill_blob(cx, cy, (int)(W * 1.22f), (int)(H * 1.16f), mc,
              (uint16_t)(95 * g));                                    /* ① 外光晕 */
    fill_blob(cx, cy, W, H, mc, 255);                                 /* ② 主体 */
    fill_blob(cx, (int)(cy - H * 0.05f), (int)(W * 0.74f),
              (int)(H * 0.70f), core, 255);                           /* ③ 亮芯 */
    fill_blob((int)(cx + W * 0.17f), (int)(cy - H * 0.29f),
              (int)(W * 0.38f), (int)(H * 0.29f), white, 230);        /* ④ 主高光 */
    fill_blob((int)(cx - W * 0.21f), (int)(cy + H * 0.28f),
              (int)(W * 0.21f), (int)(H * 0.14f), white, 128);        /* ⑤ 次高光 */
}

static void draw_eye(int cx, int cy, const emo_t *e, float h_scale)
{
    /* 尺寸经 layout.scale 换算（240 基准 → 实际屏）*/
    float w = e->w * s_layout.scale;
    float h = e->h * s_layout.scale * h_scale;
    if (h < 1.0f) h = 1.0f;

    float g = e->glow;
    if (e->pulse || s_batt_low) g *= (0.55f + 0.45f * fabsf(sinf(s_time * 2.2f)));
    if (g <= 0.02f) return;

    /* 圆眼走专门的可爱分层绘制 */
    if (e->shape == EM_DOT) {
        draw_cute_eye(cx, cy, w, h, g < 1.2f ? g : 1.2f);
        return;
    }

    const uint16_t mc = to_u16(s_main);
    const uint16_t cc = to_u16(s_core);

    /* 3 层：{ 尺寸倍率, 透明度 }——与源一致 */
    const float sc[3] = { 1.00f, 0.90f, 0.78f };
    const int   op[3] = { (int)(70 * g), (int)(150 * g), 255 };

    for (int L = 0; L < 3; L++) {
        uint16_t c = (L == 2) ? cc : mc;
        uint16_t opa = (uint16_t)(op[L] > 255 ? 255 : op[L]);
        int ww = (int)(w * sc[L]), hh = (int)(h * sc[L]);
        if (ww < 1 || hh < 1) continue;

        switch (e->shape) {
        case EM_ARC: {
            /* 弯月：bend>0 笑 ∩（中间上凸），bend<0 哭 ∪ */
            float lift = fabsf(e->bend) * h * 0.55f * (e->bend >= 0 ? 1.0f : -1.0f);
            float xs[BEZ_N], ys[BEZ_N];
            quad_bezier(xs, ys,
                        cx - ww / 2.0f, cy + lift * 0.5f,
                        (float)cx,       cy - lift,
                        cx + ww / 2.0f, cy + lift * 0.5f);
            int lw = (int)(hh * 0.62f) + 3;
            int lr = lw / 2; if (lr < 1) lr = 1;
            for (int i = 1; i < BEZ_N; i++) {
                stroke_seg(xs[i - 1], ys[i - 1], xs[i], ys[i], lr, c, opa);
            }
            break;
        }

        case EM_HEART: {
            /* 简化 6 点心形：上宽下尖，配合辉光很接近真爱心 */
            float xs[6], ys[6];
            xs[0] = (float)cx;                  ys[0] = cy + hh * 0.45f;
            xs[1] = cx - ww * 0.60f;            ys[1] = cy - hh * 0.20f;
            xs[2] = cx - ww * 0.46f;            ys[2] = cy - hh * 0.52f;
            xs[3] = cx - ww * 0.06f;            ys[3] = cy - hh * 0.40f;
            xs[4] = cx + ww * 0.46f;            ys[4] = cy - hh * 0.52f;
            xs[5] = cx + ww * 0.60f;            ys[5] = cy - hh * 0.20f;
            fill_poly(xs, ys, 6, c, opa);
            break;
        }

        case EM_STAR: {
            /* 五角星（y 轴纵横比 1.15 拉长，与源一致）*/
            float xs[10], ys[10];
            float R = ww / 2.0f, r = R * 0.44f;
            for (int i = 0; i < 10; i++) {
                float ang = -1.5707963f + (float)i * 0.62831853f;  /* π/5 */
                float rr = (i % 2) ? r : R;
                xs[i] = cx + rr * cosf(ang);
                ys[i] = cy + rr * sinf(ang) * ((float)hh / (float)ww * 1.15f);
            }
            fill_poly(xs, ys, 10, c, opa);
            break;
        }

        case EM_SPIRAL: {
            /* 螺旋（晕）：3 圈阿基米德螺线，圆盘笔触 */
            float px = (float)cx, py = (float)cy;
            for (int i = 0; i < 40; i++) {
                float t = (float)i / 39.0f;
                float ang = t * 3.0f * 6.2831853f;
                float rr = (ww / 2.0f) * t;
                float x = cx + rr * cosf(ang);
                float y = cy + rr * sinf(ang) * ((float)hh / (float)ww);
                stroke_seg(px, py, x, y, 2, c, opa);
                px = x; py = y;
            }
            break;
        }

        case EM_X: {
            /* 叉（断线/死机）*/
            int s = (int)(ww / 2.0f * 0.72f);
            int lw = (int)(ww * 0.26f) + 2;
            int lr = lw / 2; if (lr < 1) lr = 1;
            stroke_seg((float)(cx - s), (float)(cy - s), (float)(cx + s), (float)(cy + s), lr, c, opa);
            stroke_seg((float)(cx + s), (float)(cy - s), (float)(cx - s), (float)(cy + s), lr, c, opa);
            break;
        }

        default:
            break;
        }
    }
}

/* 腮红（害羞）：3 层递减透明椭圆，与源一致 */
static void draw_blush(int cx, int cy)
{
    const uint16_t mc = to_u16(s_main);
    for (int k = 3; k >= 1; k--) {
        int r = (int)(6 * k * s_layout.scale);
        if (r < 2) r = 2;
        fill_blob(cx, cy, r * 2, r, mc, (uint16_t)(30 / k));
    }
}

/* 底部声波：22 条，能量拟态驱动（无真实频段数据时的降级方案，
 * 与原版"静止时也像在听"的时间抖动语义一致）*/
static void draw_wave(void)
{
    const int n = EMO_WAVE_BARS;
    const int bw = (EMO_WAVE_BW * s_layout.short_side + 120) / 240;
    const int gap = (EMO_WAVE_GAP * s_layout.short_side + 120) / 240;
    const int total = n * bw + (n - 1) * gap;
    const int x0 = (s_w - total) / 2;
    const int base = s_layout.wave_base;
    const uint16_t mc = to_u16(s_main);

    for (int i = 0; i < n; i++) {
        float d = fabsf((float)(i - n / 2)) / (float)(n / 2);
        /* 拟态频段：低频慢、高频快，视觉接近真实频谱 */
        float fi = (float)i / (float)(n - 1);
        float band = s_energy * (0.35f + 0.65f * fabsf(sinf(s_time * (2.0f + 7.0f * fi) + fi * 9.0f)));
        float amp = (1.0f - d * 0.55f) * band;
        float jit = 0.72f + 0.28f * fabsf(sinf(s_time * 6.5f + (float)i * 0.62f));
        int hh = (int)((3 + amp * 28.0f * jit) * s_layout.scale);
        if (hh < 3) hh = 3;
        fill_blob(x0 + i * (bw + gap) + bw / 2, base - hh / 2, bw, hh,
                  mc, (uint16_t)(70 + 150 * amp));
    }
}

/* ══════════════════════════════════════════════════
 * 脏区估计
 * ══════════════════════════════════════════════════ */

/* 单眼绘制范围（外晕 1.22/1.16 倍 + 高光/腮红余量）*/
static void eye_bbox(int cx, int cy, const emo_t *e, lv_area_t *a)
{
    float w = e->w * s_layout.scale * 1.25f;
    float h = e->h * s_layout.scale * 1.20f + 4.0f;
    int pad = 6;
    a->x1 = cx - (int)w / 2 - pad;
    a->x2 = cx + (int)w / 2 + pad;
    a->y1 = cy - (int)h / 2 - pad;
    a->y2 = cy + (int)h / 2 + pad + s_layout.blush_dy / 2;  /* 腮红下垂余量 */
}

static void union_area(const lv_area_t *a, const lv_area_t *b, lv_area_t *out)
{
    out->x1 = (a->x1 < b->x1) ? a->x1 : b->x1;
    out->y1 = (a->y1 < b->y1) ? a->y1 : b->y1;
    out->x2 = (a->x2 > b->x2) ? a->x2 : b->x2;
    out->y2 = (a->y2 > b->y2) ? a->y2 : b->y2;
}

static void clamp_area(lv_area_t *a)
{
    if (a->x1 < 0) a->x1 = 0;
    if (a->y1 < 0) a->y1 = 0;
    if (a->x2 >= s_w) a->x2 = s_w - 1;
    if (a->y2 >= s_h) a->y2 = s_h - 1;
}

/* ══════════════════════════════════════════════════
 * 创建 / 公共 API
 * ══════════════════════════════════════════════════ */
lv_obj_t *emo_canvas_create(lv_obj_t *parent, const emo_layout_t *layout)
{
    s_layout = *layout;
    s_w = s_layout.width;
    s_h = s_layout.height;

    s_main = MK(47, 216, 255);            /* 冰蓝（EMOPET 默认）*/
    s_core = lv_color_mix(s_main, lv_color_white(), 205);

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

    /* 全屏铺底色（深黑蓝，与源一致）*/
    const uint16_t bg = to_u16(MK(8, 9, 12));
    for (int y = 0; y < s_h; y++) px_span(0, s_w - 1, y, bg);

    /* 开机即"渐亮睁开"：当前态 = 压扁零光，目标态 = IDLE。
     * 之后 tick 的插值（k=0.16）自然完成 0.5s 睁眼 + 辉光点亮，
     * 取代像素宠物的独立出生动画模块。 */
    memcpy(&s_tgt, &EMO[EMO_IDLE], sizeof(emo_t));
    s_cur = s_tgt;
    s_cur.h = 2;
    s_cur.glow = 0.0f;
    s_cur_id = EMO_IDLE;

    s_blink = false; s_blink_t = -1.0f;
    s_switching = false;
    s_next_blink = 90;
    s_energy = 0.0f;
    s_time = 0.0f;
    s_wave = false; s_auto_blink = true; s_breathe = true; s_batt_low = false;
    s_dirty_valid = false;
    s_full_redraw = true;

    return s_canvas;
}

void emo_canvas_destroy(void)
{
    if (s_canvas) {
        lv_obj_delete(s_canvas);
        s_canvas = NULL;
    }
    if (s_buf) {
        heap_caps_free(s_buf);
        s_buf = NULL;
    }
    s_dirty_valid = false;
}

bool emo_canvas_ready(void) { return s_canvas != NULL; }

void emo_set_color(uint8_t r, uint8_t g, uint8_t b)
{
    s_main = MK(r, g, b);
    s_core = lv_color_mix(s_main, lv_color_white(), 205);
    s_full_redraw = true;   /* 眼区外的反射光晕要整屏换色 */
}

void emo_set_emotion(emo_id_t id)
{
    if ((int)id < 0 || id >= EMO_MAX) return;
    s_cur_id = (uint8_t)id;
    memcpy(&s_tgt, &EMO[id], sizeof(emo_t));

    /* 形状变化 → 走闭眼转场；只改大小/辉光则直接插值 */
    if (s_tgt.shape != s_cur.shape) {
        s_pending_shape = s_tgt.shape;
        s_pending_r = R_OVER[id].use;
        s_switching = true;
        s_switch_t = 0.0f;
    }
    ESP_LOGI(TAG, "表情 → %d", (int)id);
}

void emo_blink(void) { s_blink = true; s_blink_t = 0.0f; }
void emo_set_wave(bool on)
{
    if (s_wave == on) return;
    s_wave = on;
    s_full_redraw = true;   /* 关闭时波条残迹需整屏清 */
}
void emo_set_auto_blink(bool on) { s_auto_blink = on; }
void emo_set_breathe(bool on) { s_breathe = on; }
void emo_set_energy(float e) { s_energy = e; }
void emo_set_battery_low(bool low) { s_batt_low = low; }

/* ══════════════════════════════════════════════════
 * 每帧推进 + 渲染（33ms / 30fps，静止态自动降 15fps）
 * ══════════════════════════════════════════════════ */
void emo_tick(void)
{
    if (!s_canvas) return;

    const float dt = 0.033f;
    s_time += dt;

    /* ── 参数插值（大小 / 辉光 / 偏移 / 弯曲）────── */
    const float k = 0.16f;
    s_cur.w     += (s_tgt.w    - s_cur.w)    * k;
    s_cur.h     += (s_tgt.h    - s_cur.h)    * k;
    s_cur.glow  += (s_tgt.glow - s_cur.glow) * k;
    s_cur.bend  += (s_tgt.bend - s_cur.bend) * k;
    s_cur.offY  += (int)((float)(s_tgt.offY - s_cur.offY) * k);
    s_cur.blush  = s_tgt.blush;
    s_cur.pulse  = s_tgt.pulse;
    s_cur.tilt   = s_tgt.tilt;

    /* ── 转场：闭眼 → 换形 → 睁眼（300ms）────────── */
    if (s_switching) {
        s_switch_t += dt;
        const float p = s_switch_t / 0.30f;
        /* 闭到最低点时才换形状——肉眼看不到"变形"，只看到"眨眼后换了表情" */
        if (p >= 0.135f && s_cur.shape != s_pending_shape) {
            s_cur.shape = s_pending_shape;
        }
        if (p >= 1.0f) { s_switching = false; }
    }

    /* ── 眨眼 ───────────────────────────────────── */
    if (s_blink) {
        s_blink_t += dt;
        if (s_blink_t >= 0.14f) { s_blink = false; s_blink_t = -1.0f; }
    } else if (s_auto_blink && s_cur.shape == EM_DOT && !s_switching) {
        if (--s_next_blink <= 0) {
            s_blink = true; s_blink_t = 0.0f;
            s_next_blink = 60 + (int)(esp_random() % 140);
        }
    }

    /* ── h 缩放：眨眼 / 转场 ─────────────────────── */
    float hs = 1.0f;
    if (s_blink && s_blink_t < 0.14f) {
        /* 对称三角波：0.07s 闭合 + 0.07s 睁开 */
        float p = s_blink_t / 0.14f;
        hs = (p < 0.5f) ? (1.0f - p * 2.0f * 0.96f)
                        : (0.04f + (p - 0.5f) * 2.0f * 0.96f);
        if (hs < 0.04f) hs = 0.04f;
    }
    if (s_switching) {
        float p = s_switch_t / 0.30f;
        float f = 1.0f;
        if (p < 0.45f)       f = 1.0f - p / 0.45f;
        else if (p < 0.55f)  f = 0.04f;
        else                 f = (p - 0.55f) / 0.45f;
        hs = (f < hs) ? f : hs;
    }

    /* ── 呼吸 + 说话跳动 ─────────────────────────── */
    float bf = 1.0f;
    if (s_breathe && s_cur.shape == EM_DOT) bf = 1.0f + 0.035f * sinf(s_time * 1.7f);
    float sf = 1.0f;
    if (s_cur_id == EMO_SPEAK) sf = 1.0f + 0.16f * s_energy;

    /* ── 渲染 ─────────────────────────────────────
     * 隔帧分频放在状态推进之后：眨眼/转场/插值恒 30fps 精确推进
     *（眨眼 0.14s 的三角波在 15fps 下会肉眼跳帧），只跳过静止态
     * 的重复绘制（呼吸/辉光缓变在 15fps 下依然平滑）。*/
    s_skip ^= 1;
    const bool calm = !s_blink && !s_switching && s_energy < 0.05f;
    if (calm && s_skip) return;

    emo_t L = s_cur;
    L.w *= bf * sf * (1.0f + 0.12f * (1.0f - hs));   /* 眨眼横向挤压（squash & stretch）*/
    L.h *= bf * sf * hs;
    L.offY = s_cur.offY;

    const int cy = s_layout.eye_cy + (int)(L.offY * s_layout.scale);

    /* 本帧绘制区：两眼 ∪ 腮红（含在 eye_bbox 余量里）*/
    lv_area_t a1, a2, cur_area;
    eye_bbox(s_layout.eye_lx, cy, &L, &a1);
    eye_bbox(s_layout.eye_rx, cy, &L, &a2);
    union_area(&a1, &a2, &cur_area);
    if (s_wave) {
        lv_area_t wv = { 0, s_layout.wave_base - (int)(34 * s_layout.scale) - 2,
                         s_w - 1, s_layout.wave_base + 2 };
        union_area(&cur_area, &wv, &cur_area);
    }

    /* 清屏区 = 上帧失效区 ∪ 本帧绘制区（上一帧更大的眼睛/更长的波条
     * 残影必须被擦掉）；换色/关波条等残迹场景直接整屏。*/
    lv_area_t clear_area;
    if (s_full_redraw || !s_dirty_valid) {
        clear_area.x1 = 0; clear_area.y1 = 0;
        clear_area.x2 = s_w - 1; clear_area.y2 = s_h - 1;
        s_full_redraw = false;
    } else {
        clear_area = s_dirty;
        union_area(&clear_area, &cur_area, &clear_area);
    }
    clamp_area(&clear_area);

    /* 局部清屏（反射光晕随清随画：fill_disc_y 只扫清屏区行范围）*/
    const uint16_t bg = to_u16(MK(8, 9, 12));
    fill_rect(clear_area.x1, clear_area.y1,
              clear_area.x2 - clear_area.x1 + 1, clear_area.y2 - clear_area.y1 + 1,
              bg, 255);

    /* 眼睛在面板上的反射光晕：一层淡淡的同色大圆，增强 LED 质感 */
    if (s_cur.glow > 0.05f) {
        float gg = s_cur.glow > 1.3f ? 1.3f : s_cur.glow;
        fill_disc_y(s_w / 2, s_h / 2, (int)(150 * s_layout.scale),
                    to_u16(s_main), (uint16_t)(34 * gg),
                    clear_area.y1 - 2, clear_area.y2 + 2);
    }

    if (L.blush) {
        draw_blush(s_layout.eye_lx - (int)(6 * s_layout.scale), cy + s_layout.blush_dy);
        draw_blush(s_layout.eye_rx + (int)(6 * s_layout.scale), cy + s_layout.blush_dy);
    }

    draw_eye(s_layout.eye_lx, cy, &L, 1.0f);

    /* 右眼：wink 等支持独立形状 */
    emo_t R = L;
    if (R_OVER[s_cur_id].use) {
        R.shape = R_OVER[s_cur_id].e.shape;
        R.h     = R_OVER[s_cur_id].e.h * bf * sf * hs * s_layout.scale;
        R.bend  = R_OVER[s_cur_id].e.bend;
    }
    draw_eye(s_layout.eye_rx, cy, &R, 1.0f);

    if (s_wave) draw_wave();

    /* 失效 = 清屏区（局部帧只报脏区，20MHz SPI 大屏 flush 量降 ~60%）*/
    lv_obj_invalidate_area(s_canvas, &clear_area);
    s_dirty = clear_area;
    s_dirty_valid = true;
}

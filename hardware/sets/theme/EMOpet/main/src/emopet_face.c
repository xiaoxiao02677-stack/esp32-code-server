/* ============================================================
 * emopet_face.c — EMOPET 风格机器人脸
 *
 * 设计要点：
 *  1) 眼睛即全部：情绪由 形状 / 大小 / 倾角 / 辉光 四个维度表达
 *  2) 切换表情走"闭眼 → 换形 → 睁眼"，比直接变形自然得多
 *  3) 辉光 = 同一形状画 3 层（大模糊低的替代：放大 + 低透明）
 *     —— ESP32 上绝不做高斯模糊，用"尺寸递减 + 透明度递增"模拟
 *  4) 零位图：所有形状都是参数化路径，flash 占用几乎为零
 * ============================================================ */
#include <math.h>
#include <string.h>
#include "esp_log.h"
#include "esp_random.h"
#include "esp_heap_caps.h"
#include "lvgl.h"
#include "app_config.h"
#include "emopet_ui.h"
#include "overlay.h"

static const char *TAG = "emopet";

#define MK(r, g, b) lv_color_make(r, g, b)

/* ── 表情表（与 docs/emopet_face_preview.html 完全一致）────── */
static const emo_t EMO[EMO_MAX] = {
    /* id            shape      w     h   bend  glow  offY  tilt  pulse blush */
    [EMO_IDLE]     = { EM_DOT,    54,  62,  0.0f, 1.00f,   0, 0.0f, 0, 0 },
    [EMO_LISTEN]   = { EM_DOT,    60,  70,  0.0f, 1.35f,  -2, 0.0f, 0, 0 },
    [EMO_SPEAK]    = { EM_DOT,    56,  64,  0.0f, 1.20f,   0, 0.0f, 0, 0 },
    [EMO_HAPPY]    = { EM_ARC,    50,  18,  1.0f, 1.25f,   2, 0.0f, 0, 0 },
    [EMO_LOVE]     = { EM_HEART,  48,  45,  0.0f, 1.55f,   0, 0.0f, 0, 0 },
    [EMO_SLEEPY]   = { EM_ARC,    46,  10, 0.35f, 0.62f,   4, 0.0f, 0, 0 },
    [EMO_SAD]      = { EM_ARC,    44,  15,-0.85f, 0.75f,   2,-0.3f, 0, 0 },
    [EMO_SURPRISE] = { EM_DOT,    48,  78,  0.0f, 1.60f,  -4, 0.0f, 0, 0 },
    [EMO_ANGRY]    = { EM_DOT,    56,  46,  0.0f, 1.45f,   0,0.55f, 0, 0 },
    [EMO_WINK]     = { EM_DOT,    54,  58,  0.0f, 1.20f,   0, 0.0f, 0, 0 },
    [EMO_STAR]     = { EM_STAR,   50,  48,  0.0f, 1.55f,   0, 0.0f, 0, 0 },
    [EMO_DIZZY]    = { EM_SPIRAL, 44,  44,  0.0f, 0.95f,   0, 0.0f, 0, 0 },
    [EMO_THINK]    = { EM_DOT,    50,  50,  0.0f, 1.05f,  -8,0.28f, 0, 0 },
    [EMO_SHY]      = { EM_DOT,    50,  46,  0.0f, 1.10f,   6, 0.0f, 0, 1 },
    [EMO_OFFLINE]  = { EM_X,      42,  42,  0.0f, 0.70f,   0, 0.0f, 0, 0 },
    [EMO_LOWBATT]  = { EM_DOT,    46,  40,  0.0f, 0.45f,   0, 0.0f, 1, 0 },
    [EMO_BOOT]     = { EM_DOT,    54,  62,  0.0f, 0.00f,   0, 0.0f, 0, 0 },
    [EMO_WIFI]     = { EM_QR,      0,   0,  0.0f, 1.00f,   0, 0.0f, 0, 0 },
};

/* 眨眼用的右眼覆盖（wink：左眼 dot，右眼笑弧）*/
typedef struct {
    bool  use;
    emo_t e;
} r_override_t;
static const r_override_t R_OVER[EMO_MAX] = {
    [EMO_WINK] = { true, { EM_ARC, 54, 18, 1.0f, 1.20f, 0, 0.0f, 0, 0 } },
};

/* ── 运行时状态 ──────────────────────────────────── */
static lv_obj_t   *s_cv = NULL;
static lv_color_t *s_buf = NULL;
static eye_color_t s_col;
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
static float       s_bands[WAVE_BARS];
static float       s_time = 0.0f;
static bool        s_status = false, s_wave = false, s_auto_blink = true, s_breathe = true;

/* ── 工具：像素级"圆角矩形"——用 LVGL 的 rect + 大圆角 ── */
static void draw_blob(lv_obj_t *cv, int cx, int cy, int w, int h,
                      lv_color_t col, lv_opa_t opa)
{
    if (w < 1 || h < 1) return;
    lv_draw_rect_dsc_t d; lv_draw_rect_dsc_init(&d);
    d.bg_color = col; d.bg_opa = opa; d.border_width = 0;
    d.radius = (w < h ? w : h) / 2;      /* 圆角 = 短边一半 → 胶囊/椭圆 */
    lv_canvas_draw_rect(cv, cx - w/2, cy - h/2, w, h, &d);
}

/* ── 工具：二次贝塞尔采样（笑眼 / 哭眼 / 爱心的弯月线）── */
#define BEZ_N 16
static void quad_points(lv_point_precise_t *out, int n,
                        float x0, float y0, float xc, float yc, float x1, float y1)
{
    for (int i = 0; i < n; i++) {
        float t = (float)i / (float)(n - 1);
        float mt = 1.0f - t;
        out[i].x = (lv_value_precise_t)(mt*mt*x0 + 2*mt*t*xc + t*t*x1);
        out[i].y = (lv_value_precise_t)(mt*mt*y0 + 2*mt*t*yc + t*t*y1);
    }
}

/* ── 工具：填充多边形 ────────────────────────────── */
static void fill_poly(lv_obj_t *cv, const lv_point_t *pts, int n,
                      lv_color_t col, lv_opa_t opa)
{
    lv_draw_polygon_dsc_t d; lv_draw_polygon_dsc_init(&d);
    d.bg_color = col; d.bg_opa = opa;
    lv_canvas_draw_polygon(cv, pts, (uint32_t)n, &d);
}

/* ── 工具：描折线 ────────────────────────────────── */
static void stroke_poly(lv_obj_t *cv, const lv_point_precise_t *pts, int n,
                        lv_color_t col, lv_opa_t opa, int width)
{
    lv_draw_line_dsc_t d; lv_draw_line_dsc_init(&d);
    d.color = col; d.opa = opa; d.width = width;
    d.round_start = 1; d.round_end = 1;
    lv_canvas_draw_line(cv, pts, (uint32_t)n, &d);
}

/* ═══════════════════════════════════════════════════
 * 单只眼睛：3 层辉光
 *   层1 大尺寸 + 低透明  = 外晕（替代高斯模糊）
 *   层2 中尺寸 + 中透明
 *   层3 芯尺寸 + 高亮近白
 * ═══════════════════════════════════════════════════ */
/* ── 可爱版圆眼：外晕 → 主体 → 亮芯 → 主高光 → 次高光 ──────────
 * ★ 第 ④ 步的高光点是「灯」和「眼睛」的分界线。
 *   没有它，画出来只是两颗发光的 LED；有了它，才是一双会说话的眼睛。 */
static void draw_cute_eye(lv_obj_t *cv, int cx, int cy, float w, float h, float g)
{
    const lv_color_t mc = s_col.main;
    int W = (int)w, H = (int)h;
    if (W < 2 || H < 2) return;

    /* ① 外光晕：柔和扩散到黑色面板上 —— EMOPET 质感的来源 */
    draw_blob(cv, cx, cy, (int)(W * 1.22f), (int)(H * 1.16f), mc, (lv_opa_t)(95 * g));

    /* ② 主体（主色，满不透明）*/
    draw_blob(cv, cx, cy, W, H, mc, LV_OPA_COVER);

    /* ③ 亮芯：主色向白混合，位置略偏上 —— 发光体的正确结构 */
    draw_blob(cv, cx, (int)(cy - H * 0.05f),
              (int)(W * 0.74f), (int)(H * 0.70f),
              lv_color_mix(mc, lv_color_white(), 150), LV_OPA_COVER);

    /* ④ 主高光：上方偏右的小白椭圆 —— 关键的一笔 */
    draw_blob(cv, (int)(cx + W * 0.17f), (int)(cy - H * 0.29f),
              (int)(W * 0.38f), (int)(H * 0.29f),
              lv_color_white(), (lv_opa_t)230);

    /* ⑤ 次高光（反射）：下方偏左，更小更淡 —— 增加球面湿润感 */
    draw_blob(cv, (int)(cx - W * 0.21f), (int)(cy + H * 0.28f),
              (int)(W * 0.21f), (int)(H * 0.14f),
              lv_color_white(), (lv_opa_t)128);
}

static void draw_eye(lv_obj_t *cv, int cx, int cy, const emo_t *e, float h_scale)
{
    float w = e->w;
    float h = e->h * h_scale;
    if (h < 1.0f) h = 1.0f;

    float g = e->glow;
    if (e->pulse) g *= (0.55f + 0.45f * fabsf(sinf(s_time * 2.2f)));
    if (g <= 0.02f) return;

    /* 圆眼走专门的可爱分层绘制 */
    if (e->shape == EM_DOT) {
        draw_cute_eye(cv, cx, cy, w, h, g < 1.2f ? g : 1.2f);
        return;
    }

    const lv_color_t mc = s_col.main;
    const lv_color_t cc = s_col.core;

    /* 3 层：{ 尺寸倍率, 透明度 } */
    const float sc[3] = { 1.00f, 0.90f, 0.78f };
    const int   op[3] = { (int)(70 * g), (int)(150 * g), 255 };

    for (int L = 0; L < 3; L++) {
        lv_color_t c = (L == 2) ? cc : mc;
        lv_opa_t  opa = (lv_opa_t)(op[L] > 255 ? 255 : op[L]);
        int ww = (int)(w * sc[L]), hh = (int)(h * sc[L]);
        if (ww < 1 || hh < 1) continue;

        switch (e->shape) {
        case EM_ARC: {
            /* 弯月：bend>0 笑 ∩（中间上凸），bend<0 哭 ∪ */
            float lift = fabsf(e->bend) * h * 0.55f * (e->bend >= 0 ? 1.0f : -1.0f);
            lv_point_precise_t pts[BEZ_N];
            quad_points(pts, BEZ_N,
                        cx - ww/2.0f, cy + lift * 0.5f,
                        (float)cx,     cy - lift,
                        cx + ww/2.0f, cy + lift * 0.5f);
            stroke_poly(cv, pts, BEZ_N, c, opa, (int)(hh * 0.62f) + 3);
            break;
        }

        case EM_HEART: {
            lv_point_t pts[4];
            pts[0].x = cx;                          pts[0].y = (int)(cy + hh*0.45f);
            pts[1].x = (int)(cx - ww*0.62f);        pts[1].y = (int)(cy - hh*0.42f);
            pts[2].x = (int)(cx - ww*0.10f);        pts[2].y = (int)(cy - hh*0.55f);
            pts[3].x = (int)(cx + ww*0.30f);        pts[3].y = (int)(cy - hh*0.15f);
            /* 简化的 4 点心形：上宽下尖，配合辉光很接近真爱心 */
            lv_point_t p6[6];
            p6[0] = pts[0];
            p6[1].x = (int)(cx - ww*0.60f); p6[1].y = (int)(cy - hh*0.20f);
            p6[2].x = (int)(cx - ww*0.46f); p6[2].y = (int)(cy - hh*0.52f);
            p6[3].x = (int)(cx - ww*0.06f); p6[3].y = (int)(cy - hh*0.40f);
            p6[4].x = (int)(cx + ww*0.46f); p6[4].y = (int)(cy - hh*0.52f);
            p6[5].x = (int)(cx + ww*0.60f); p6[5].y = (int)(cy - hh*0.20f);
            fill_poly(cv, p6, 6, c, opa);
            break;
        }

        case EM_STAR: {
            lv_point_t p[10];
            float R = ww / 2.0f, r = R * 0.44f;
            for (int i = 0; i < 10; i++) {
                float ang = -1.5707963f + (float)i * 0.62831853f;  /* π/5 */
                float rr = (i % 2) ? r : R;
                p[i].x = (int)(cx + rr * cosf(ang));
                p[i].y = (int)(cy + rr * sinf(ang) * ((float)hh/(float)ww * 1.15f));
            }
            fill_poly(cv, p, 10, c, opa);
            break;
        }

        case EM_SPIRAL: {
            lv_point_precise_t p[40];
            const int n = 40, turns = 3;
            for (int i = 0; i < n; i++) {
                float t = (float)i / (float)(n - 1);
                float ang = t * turns * 6.2831853f;
                float rr = (ww / 2.0f) * t;
                p[i].x = (lv_value_precise_t)(cx + rr * cosf(ang));
                p[i].y = (lv_value_precise_t)(cy + rr * sinf(ang) * ((float)hh/(float)ww));
            }
            stroke_poly(cv, p, n, c, opa, 4);
            break;
        }

        case EM_X: {
            lv_point_precise_t a[2], b[2];
            int s = (int)(ww / 2.0f * 0.72f);
            a[0].x = cx - s; a[0].y = cy - s; a[1].x = cx + s; a[1].y = cy + s;
            b[0].x = cx + s; b[0].y = cy - s; b[1].x = cx - s; b[1].y = cy + s;
            stroke_poly(cv, a, 2, c, opa, (int)(ww * 0.26f) + 2);
            stroke_poly(cv, b, 2, c, opa, (int)(ww * 0.26f) + 2);
            break;
        }

        default: break;
        }
    }
}

/* ── 腮红（害羞）─────────────────────────────────── */
static void draw_blush(lv_obj_t *cv, int cx, int cy)
{
    for (int k = 3; k >= 1; k--) {
        lv_draw_rect_dsc_t d; lv_draw_rect_dsc_init(&d);
        d.radius = LV_RADIUS_CIRCLE; d.border_width = 0;
        d.bg_color = s_col.main;
        d.bg_opa = (lv_opa_t)(30 / k);
        int r = 6 * k;
        lv_canvas_draw_rect(cv, cx - r, cy - r/2, r*2, r, &d);
    }
}

/* ── 3×5 点阵数字（零字体依赖，机械感，和机器人脸统一）────── */
static const uint8_t DIGIT35[10][5] = {
    {7,5,5,5,7},  /* 0 */
    {2,6,2,2,7},  /* 1 */
    {7,1,7,4,7},  /* 2 */
    {7,1,7,1,7},  /* 3 */
    {5,5,7,1,1},  /* 4 */
    {7,4,7,1,7},  /* 5 */
    {7,4,7,5,7},  /* 6 */
    {7,1,1,1,1},  /* 7 */
    {7,5,7,5,7},  /* 8 */
    {7,5,7,1,7},  /* 9 */
};

/* 画一个 3×5 点阵字符。px = 每个点的像素边长 */
static void draw_glyph(lv_obj_t *cv, int x, int y, const uint8_t rows[5], int px, lv_opa_t opa)
{
    lv_draw_rect_dsc_t d; lv_draw_rect_dsc_init(&d);
    d.radius = 0; d.border_width = 0;
    d.bg_color = s_col.main; d.bg_opa = opa;
    for (int r = 0; r < 5; r++) {
        for (int c = 0; c < 3; c++) {
            if (rows[r] & (1 << (2 - c))) {
                lv_canvas_draw_rect(cv, x + c*px, y + r*px, px, px, &d);
            }
        }
    }
}

/* 冒号（两个方点）*/
static void draw_colon(lv_obj_t *cv, int x, int y, int px, lv_opa_t opa)
{
    lv_draw_rect_dsc_t d; lv_draw_rect_dsc_init(&d);
    d.radius = 0; d.border_width = 0;
    d.bg_color = s_col.main; d.bg_opa = opa;
    lv_canvas_draw_rect(cv, x, y + px,     px, px, &d);
    lv_canvas_draw_rect(cv, x, y + 3*px,   px, px, &d);
}

/* ── 顶部状态：时间 / Wi-Fi / 电量（数据来自 overlay.c）────── */
static void draw_status(lv_obj_t *cv)
{
    const overlay_state_t *st = overlay_get();
    const int px = 2;               /* 点阵像素边长 */
    const int gw = 3 * px;          /* 单个数字宽 = 6 */
    const int gap = 1;
    int x = 14;
    const int y = 10;

    /* 左：HH:MM */
    draw_glyph(cv, x, y, DIGIT35[st->hour / 10],   px, 178); x += gw + gap;
    draw_glyph(cv, x, y, DIGIT35[st->hour % 10],   px, 178); x += gw + gap;
    draw_colon(cv,  x, y, px, 178);                          x += px + gap;
    draw_glyph(cv, x, y, DIGIT35[st->minute / 10], px, 178); x += gw + gap;
    draw_glyph(cv, x, y, DIGIT35[st->minute % 10], px, 178);

    /* 未校时：在时分前面点一个低亮度的点做提示 */
    if (!st->time_valid) {
        lv_draw_rect_dsc_t d; lv_draw_rect_dsc_init(&d);
        d.radius = LV_RADIUS_CIRCLE; d.border_width = 0;
        d.bg_color = s_col.main; d.bg_opa = 127;
        lv_canvas_draw_rect(cv, 8, y + 4, 3, 3, &d);
    }

    /* 右：Wi-Fi 信号弧（按 RSSI 亮 1..3 格）；未连接则画断开斜线 */
    lv_draw_arc_dsc_t a; lv_draw_arc_dsc_init(&a);
    a.width = 2; a.rounded = 0;
    for (int i = 0; i < 3; i++) {
        bool on = st->wifi_connected && (st->wifi_level > i);
        a.color = s_col.main;
        a.opa = on ? 204 : 51;
        lv_canvas_draw_arc(cv, 192, 18, 4 + i*4, 225, 315, &a);
    }

    /* 右：电量 */
    lv_draw_rect_dsc_t r; lv_draw_rect_dsc_init(&r);
    r.border_width = 1; r.border_color = s_col.main; r.border_opa = 127;
    r.bg_opa = 0;
    lv_canvas_draw_rect(cv, 208, 12, 18, 11, &r);
    /* 正极小帽 */
    r.border_width = 0; r.bg_opa = 127; r.bg_color = s_col.main;
    lv_canvas_draw_rect(cv, 227, 15, 2, 5, &r);
    /* 填充：低电量用闪烁提示 */
    int cells = (st->battery_pct * 14) / 100;      /* 内宽 16 → 最多 14 格 */
    if (cells < 1 && st->battery_pct > 0) cells = 1;
    bool low = (st->battery_pct <= 15);
    lv_opa_t fill_opa = 230;
    if (low && st->battery_pct > 0) {
        fill_opa = (lv_opa_t)((fabsf(sinf(s_time * 2.0f)) > 0.5f) ? 230 : 76);
    }
    r.bg_opa = fill_opa; r.bg_color = s_col.main; r.border_width = 0;
    lv_canvas_draw_rect(cv, 210, 14, cells, 7, &r);

    /* 充电：电池框上叠一个闪电（简化为一条斜线）*/
    if (st->charging) {
        lv_point_precise_t p[3];
        p[0].x = 218; p[0].y = 13;
        p[1].x = 214; p[1].y = 18;
        p[2].x = 221; p[2].y = 21;
        lv_draw_line_dsc_t ln; lv_draw_line_dsc_init(&ln);
        ln.color = lv_color_white(); ln.width = 2; ln.opa = LV_OPA_COVER;
        ln.round_start = 1; ln.round_end = 1;
        lv_canvas_draw_line(cv, p, 3, &ln);
    }
}

/* ── 底部声波：真实频段能量驱动 ──────────────────────
 * 条形高度 = 插值后的频段能量 × 时间抖动
 * 中间高两边低（能量衰减 + 视觉聚焦）*/
static void draw_wave(lv_obj_t *cv)
{
    overlay_get_bands(s_bands, WAVE_BARS);

    const int n = WAVE_BARS, bw = 5, gap = 3;
    const int total = n*bw + (n-1)*gap;
    const int x0 = (SCR_W - total) / 2;
    const int base = 216;

    for (int i = 0; i < n; i++) {
        float d = fabsf((float)(i - n/2)) / (float)(n/2);
        float amp = (1.0f - d * 0.55f) * s_bands[i];
        /* 加一点时间抖动，静止时也像在"听" */
        float jit = 0.72f + 0.28f * fabsf(sinf(s_time * 6.5f + (float)i * 0.62f));
        int hh = (int)(3 + amp * 28.0f * jit);
        if (hh < 3) hh = 3;

        lv_draw_rect_dsc_t r; lv_draw_rect_dsc_init(&r);
        r.radius = 2; r.border_width = 0;
        r.bg_color = s_col.main;
        r.bg_opa = (lv_opa_t)(70 + 150 * amp);
        lv_canvas_draw_rect(cv, x0 + i*(bw+gap), base - hh, bw, hh, &r);
    }
}

/* ── 配网二维码占位（真实二维码请用 espressif/qrcode）── */
static void draw_qr(lv_obj_t *cv)
{
    const int x0 = 52, y0 = 46, size = 136;
    lv_draw_rect_dsc_t bg; lv_draw_rect_dsc_init(&bg);
    bg.radius = 6; bg.border_width = 0; bg.bg_opa = LV_OPA_COVER;
    bg.bg_color = lv_color_white();
    lv_canvas_draw_rect(cv, x0 - 6, y0 - 6, size + 12, size + 12, &bg);

    const int n = 21;
    const float cell = (float)size / (float)n;
    uint32_t sd = 20250818;
    lv_draw_rect_dsc_t m; lv_draw_rect_dsc_init(&m);
    m.radius = 0; m.border_width = 0; m.bg_opa = LV_OPA_COVER;
    m.bg_color = lv_color_make(16, 18, 22);
    for (int i = 0; i < n; i++) {
        for (int j = 0; j < n; j++) {
            if ((i < 7 && j < 7) || (i >= n-7 && j < 7) || (i < 7 && j >= n-7)) continue;
            sd = sd * 1103515245u + 12345u;
            if ((sd >> 16) % 100 > 48) {
                lv_canvas_draw_rect(cv, (int)(x0 + i*cell), (int)(y0 + j*cell),
                                    (int)cell + 1, (int)cell + 1, &m);
            }
        }
    }
    /* 三个定位角 */
    for (int k = 0; k < 3; k++) {
        int ox = (k == 1) ? n - 7 : 0;
        int oy = (k == 2) ? n - 7 : 0;
        lv_draw_rect_dsc_t f; lv_draw_rect_dsc_init(&f);
        f.radius = 0; f.border_width = 0; f.bg_opa = LV_OPA_COVER;
        f.bg_color = lv_color_make(16, 18, 22);
        lv_canvas_draw_rect(cv, (int)(x0 + ox*cell), (int)(y0 + oy*cell),
                            (int)(7*cell), (int)(7*cell), &f);
        f.bg_color = lv_color_white();
        lv_canvas_draw_rect(cv, (int)(x0 + (ox+1)*cell), (int)(y0 + (oy+1)*cell),
                            (int)(5*cell), (int)(5*cell), &f);
        f.bg_color = lv_color_make(16, 18, 22);
        lv_canvas_draw_rect(cv, (int)(x0 + (ox+2)*cell), (int)(y0 + (oy+2)*cell),
                            (int)(3*cell), (int)(3*cell), &f);
    }
}

/* ═══════════════════════════════════════════════════
 * 创建 / 公共 API
 * ═══════════════════════════════════════════════════ */
lv_obj_t *emopet_canvas_create(lv_obj_t *parent)
{
    s_col.main = MK(47, 216, 255);      /* 冰蓝（EMOPET 默认）*/
    s_col.core = MK(214, 248, 255);

    size_t bytes = (size_t)SCR_W * SCR_H * sizeof(lv_color_t);
    s_buf = heap_caps_malloc(bytes, MALLOC_CAP_SPIRAM);
    if (!s_buf) s_buf = heap_caps_malloc(bytes, MALLOC_CAP_8BIT);
    if (!s_buf) { ESP_LOGE(TAG, "canvas buffer 分配失败"); return NULL; }

    s_cv = lv_canvas_create(parent);
    lv_obj_set_size(s_cv, SCR_W, SCR_H);
    lv_obj_center(s_cv);
#if LVGL_VERSION_MAJOR >= 9
    lv_canvas_set_buffer(s_cv, s_buf, SCR_W, SCR_H, LV_COLOR_FORMAT_RGB565);
#else
    lv_canvas_set_buffer(s_cv, s_buf, SCR_W, SCR_H, LV_IMG_CF_TRUE_COLOR);
#endif
    lv_canvas_fill_bg(s_cv, MK(8, 9, 12), LV_OPA_COVER);

    memcpy(&s_cur, &EMO[EMO_IDLE], sizeof(emo_t));
    memcpy(&s_tgt, &EMO[EMO_IDLE], sizeof(emo_t));
    return s_cv;
}

void emopet_set_color(uint8_t r, uint8_t g, uint8_t b)
{
    s_col.main = MK(r, g, b);
    /* 芯色 = 主色向白色混合 80% */
    s_col.core = lv_color_mix(s_col.main, lv_color_white(), 205);
}

void emopet_set_emotion(emo_id_t id)
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

void emopet_blink(void) { s_blink = true; s_blink_t = 0.0f; }
void emopet_set_status_bar(bool on) { s_status = on; }
void emopet_set_wave(bool on) { s_wave = on; }
void emopet_set_auto_blink(bool on) { s_auto_blink = on; }
void emopet_set_breathe(bool on) { s_breathe = on; }
void emopet_set_energy(float e) { s_energy = e; }

/* ═══════════════════════════════════════════════════
 * 每帧推进（建议 33ms / 30fps）
 * ═══════════════════════════════════════════════════ */
void emopet_tick(void)
{
    if (!s_cv) return;
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
        /* 闭到最低点时才换形状 —— 肉眼看不到"变形"，只看到"眨眼后换了表情" */
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
        /* 对称三角波：0.07s 闭合 + 0.07s 睁开，比硬切自然 */
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

    /* ── 渲染 ───────────────────────────────────── */
    lv_canvas_fill_bg(s_cv, MK(8, 9, 12), LV_OPA_COVER);

    if (s_cur.shape == EM_QR) {
        draw_qr(s_cv);
        if (s_status) draw_status(s_cv);
        lv_obj_invalidate(s_cv);
        return;
    }

    /* 眼睛在面板上的反射光晕：一层淡淡的同色叠加，增强 LED 质感 */
    if (s_cur.glow > 0.05f) {
        lv_draw_rect_dsc_t gd; lv_draw_rect_dsc_init(&gd);
        gd.radius = LV_RADIUS_CIRCLE; gd.border_width = 0;
        gd.bg_color = s_col.main;
        gd.bg_opa = (lv_opa_t)(34 * (s_cur.glow > 1.3f ? 1.3f : s_cur.glow));
        int r = 150;
        lv_canvas_draw_rect(s_cv, 120 - r, 120 - r, r*2, r*2, &gd);
    }

    emo_t L = s_cur;
    L.w *= bf * sf * (1.0f + 0.12f * (1.0f - hs));   /* 眨眼时横向挤压（squash & stretch）*/
    L.h *= bf * sf * hs;
    L.offY = s_cur.offY;

    const int cy = EYE_CY + L.offY;

    if (L.blush) { draw_blush(s_cv, EYE_LX - 6, cy + 34); draw_blush(s_cv, EYE_RX + 6, cy + 34); }

    draw_eye(s_cv, EYE_LX, cy, &L, 1.0f);

    /* 右眼：wink 等支持独立形状 */
    emo_t R = L;
    if (R_OVER[s_cur_id].use) {
        R.shape = R_OVER[s_cur_id].e.shape;
        R.h     = R_OVER[s_cur_id].e.h * bf * sf * hs;
        R.bend  = R_OVER[s_cur_id].e.bend;
    }
    draw_eye(s_cv, EYE_RX, cy, &R, 1.0f);

    if (s_status) draw_status(s_cv);
    if (s_wave) draw_wave(s_cv);

    lv_obj_invalidate(s_cv);
}

/* ============================================================
 * boot_anim.c — 3.8s 开机动画进度推进
 * 设计原则：不是播一段过场动画，是"它醒过来"
 *   慢（前 1.5s 悬念）→ 快（1.5-2.9s 开灯 + 五官四连击）→ 收（0.9s）
 * ============================================================ */
#include <string.h>
#include <math.h>
#include "esp_log.h"
#include "esp_random.h"
#include "lvgl.h"
#include "app_config.h"
#include "pet_ui.h"

static const char *TAG = "boot_anim";

static boot_prog_t   s_p;
static uint32_t      s_t0;
static boot_branch_t s_branch;
static boot_done_cb_t s_done;
static lv_timer_t   *s_timer = NULL;
static bool          s_done_flag = false;
static bool          s_skip_allowed = true;

/* 段定义：[start, end]；a<0 表示"已完成"，值恒 1 */
typedef struct { float a, b; } seg_t;

typedef struct {
    float     dur;
    seg_t     seed, ripple, outline, fill, bg, ear, blush, eye, bubble, settle, confetti;
} timeline_t;

#define DONE_SEG { -1, 0 }

static const timeline_t TL_FULL = {
    3.80f,
    {0.20f,0.60f}, {0.60f,1.00f}, {1.00f,1.50f}, {1.50f,1.90f}, {1.55f,1.90f},
    {1.90f,2.20f}, {2.20f,2.45f}, {2.45f,2.85f}, {2.85f,3.40f}, {3.40f,3.80f}, DONE_SEG
};
static const timeline_t TL_WAKE = {
    0.60f,
    DONE_SEG, DONE_SEG, DONE_SEG, DONE_SEG, DONE_SEG,
    {0.00f,0.18f}, {0.06f,0.18f}, {0.10f,0.40f}, DONE_SEG, {0.40f,0.60f}, DONE_SEG
};
static const timeline_t TL_BIRTH = {
    4.40f,
    {0.20f,0.60f}, {0.60f,1.00f}, {1.00f,1.50f}, {1.50f,1.90f}, {1.55f,1.90f},
    {1.90f,2.20f}, {2.20f,2.45f}, {2.45f,2.85f}, {2.85f,3.40f}, {3.40f,3.90f}, {3.50f,4.40f}
};

static float clampf(float x, float a, float b) { return x < a ? a : (x > b ? b : x); }
static float segv(float s, seg_t g)
{
    if (g.a < 0) return 1.0f;
    return clampf((s - g.a) / (g.b - g.a), 0.0f, 1.0f);
}
static float ease_out  (float p) { return 1.0f - (1.0f - p) * (1.0f - p) * (1.0f - p); }
static float ease_inout(float p) { return p < 0.5f ? 4*p*p*p : 1.0f - powf(-2.0f*p + 2.0f, 3.0f) / 2.0f; }
static float back_out  (float p) { const float c = 1.70158f; return 1.0f + (c+1.0f)*powf(p-1.0f,3.0f) + c*powf(p-1.0f,2.0f); }

static const timeline_t *tl(void)
{
    switch (s_branch) {
    case BOOT_WAKE:  return &TL_WAKE;
    case BOOT_BIRTH: return &TL_BIRTH;
    default:         return &TL_FULL;   /* FULL / WIFI 同时间轴，区别在结尾处理 */
    }
}

static void finish(void)
{
    if (s_timer) { lv_timer_del(s_timer); s_timer = NULL; }
    /* 保持全 1，让宠物继续以"完成态"渲染 */
    memset(&s_p, 0, sizeof(s_p));
    s_p.seed = s_p.ripple = s_p.outline = s_p.fill = s_p.bg =
    s_p.ear = s_p.blush = s_p.eye = s_p.bubble = s_p.settle = 1.0f;
    s_p.confetti = 0.0f;
    s_done_flag = true;
    ESP_LOGI(TAG, "开机动画结束 (%s)", s_branch == BOOT_WAKE ? "唤醒短版" : "完整版");
    if (s_done) s_done();
}

static void tick(lv_timer_t *t)
{
    (void)t;
    const timeline_t *T = tl();
    float s = (float)(lv_tick_get() - s_t0) / 1000.0f;

    s_p.seed    = ease_out(segv(s, T->seed));
    s_p.ripple  = ease_out(segv(s, T->ripple));
    s_p.outline = ease_inout(segv(s, T->outline));
    s_p.fill    = ease_out(segv(s, T->fill));
    s_p.bg      = ease_inout(segv(s, T->bg));       /* 与 fill 严格同步 = "开灯" */
    s_p.ear     = back_out(segv(s, T->ear));
    s_p.blush   = segv(s, T->blush);
    s_p.eye     = back_out(segv(s, T->eye));
    s_p.bubble  = back_out(segv(s, T->bubble));
    s_p.settle  = ease_out(segv(s, T->settle));
    s_p.confetti= T->confetti.a >= 0 ? ease_out(segv(s, T->confetti)) : 0.0f;

    /* 开灯那一刻的配音落点（若你有喇叭，在这里播一声） */
    static bool beeped = false;
    if (!beeped && s >= 1.50f) { beeped = true; /* play_boot_chime(); */ }

    if (s >= T->dur) finish();
}

void boot_anim_start(boot_branch_t branch, boot_done_cb_t done)
{
    s_branch = branch;
    s_done = done;
    s_done_flag = false;
    s_skip_allowed = (branch != BOOT_WIFI);   /* 首开机未配网：不允许跳过，她得看到二维码 */
    memset(&s_p, 0, sizeof(s_p));

    /* 唤醒短版：已完成项直接置 1 */
    if (branch == BOOT_WAKE) {
        s_p.seed = s_p.ripple = s_p.outline = s_p.fill = s_p.bg = 1.0f;
    }

    s_t0 = lv_tick_get();
    s_timer = lv_timer_create(tick, 20, NULL);   /* 50Hz 推进 */
    ESP_LOGI(TAG, "开机动画开始 branch=%d dur=%.2fs", (int)branch, (double)tl()->dur);
}

void boot_anim_skip(void)
{
    if (!s_skip_allowed || s_done_flag) return;
    finish();
}

bool boot_anim_is_done(void) { return s_done_flag; }

const boot_prog_t *boot_anim_prog(void)
{
    if (s_done_flag) return NULL;    /* NULL = 已完成，渲染侧置全 1 */
    return &s_p;
}

/* 按当前时间选问候语（让每天开机都不重样） */
const char *boot_greeting(void)
{
    if (s_branch == BOOT_BIRTH) return "生日快乐！";
    /* 未接 RTC 时用 esp_random 演示；接入 RTC 后换成读小时 */
    int bucket = (int)(esp_random() % 5);
    switch (bucket) {
    case 0: return "你回来啦";
    case 1: return "早呀";
    case 2: return "午安";
    case 3: return "下午好";
    default: return "想你了";
    }
}

/* ============================================================
 * pet_boot_anim.c — 3.8s 开机动画进度推进
 *
 * 移植自 hardware/sets/theme/像素宠物/main/src/boot_anim.c。
 * 与原版差异：不再自建 lv_timer 驱动（主固件里 LVGL 任务上下文管理更严格），
 * 改为纯时间推进器 —— PetSkinDisplay 用自己的 timer 周期调
 * pet_boot_anim_poll()，把最新进度画到 canvas。设计原则不变：
 * 慢（前 1.5s 悬念）→ 快（1.5-2.9s 开灯 + 五官四连击）→ 收（0.9s）。
 * ============================================================ */
#include "pet_boot_anim.h"

#include <math.h>
#include <string.h>

#include "esp_log.h"
#include "esp_random.h"
#include "lvgl.h"

static const char *TAG = "pet_boot_anim";

static pet_boot_prog_t   s_p;
static uint32_t          s_t0;
static pet_boot_branch_t s_branch;
static pet_boot_done_cb_t s_done;
static bool              s_done_flag = false;
static bool              s_skip_allowed = true;
static bool              s_started = false;

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
    case PET_BOOT_WAKE:  return &TL_WAKE;
    case PET_BOOT_BIRTH: return &TL_BIRTH;
    default:             return &TL_FULL;   /* FULL / WIFI 同时间轴 */
    }
}

static void finish(void)
{
    /* 保持全 1，让宠物继续以"完成态"渲染 */
    memset(&s_p, 0, sizeof(s_p));
    s_p.seed = s_p.ripple = s_p.outline = s_p.fill = s_p.bg =
    s_p.ear = s_p.blush = s_p.eye = s_p.bubble = s_p.settle = 1.0f;
    s_p.confetti = 0.0f;
    s_done_flag = true;
    ESP_LOGI(TAG, "开机动画结束 (%s)", s_branch == PET_BOOT_WAKE ? "唤醒短版" : "完整版");
    if (s_done) s_done();
}

/* 推进一帧（由调用方 timer 周期调，间隔建议 20ms）*/
void pet_boot_anim_poll(void)
{
    if (!s_started || s_done_flag) return;
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

    if (s >= T->dur) finish();
}

void pet_boot_anim_start(pet_boot_branch_t branch, pet_boot_done_cb_t done)
{
    s_branch = branch;
    s_done = done;
    s_done_flag = false;
    s_skip_allowed = (branch != PET_BOOT_WIFI);
    memset(&s_p, 0, sizeof(s_p));

    /* 唤醒短版：已完成项直接置 1 */
    if (branch == PET_BOOT_WAKE) {
        s_p.seed = s_p.ripple = s_p.outline = s_p.fill = s_p.bg = 1.0f;
    }

    s_t0 = lv_tick_get();
    s_started = true;
    ESP_LOGI(TAG, "开机动画开始 branch=%d dur=%.2fs", (int)branch, (double)tl()->dur);
}

void pet_boot_anim_skip(void)
{
    if (!s_started || !s_skip_allowed || s_done_flag) return;
    finish();
}

bool pet_boot_anim_is_done(void) { return s_done_flag; }

const pet_boot_prog_t *pet_boot_anim_prog(void)
{
    if (s_done_flag) return NULL;    /* NULL = 已完成，渲染侧置全 1 */
    return &s_p;
}

const char *pet_boot_greeting(void)
{
    if (s_branch == PET_BOOT_BIRTH) return "生日快乐！";
    /* 主固件有 RTC 校时（SystemInfo），但 boot 阶段可能未同步；
       沿用原版随机桶演示，接 RTC 后换成读小时 */
    int bucket = (int)(esp_random() % 5);
    switch (bucket) {
    case 0: return "你回来啦";
    case 1: return "早呀";
    case 2: return "午安";
    case 3: return "下午好";
    default: return "想你了";
    }
}

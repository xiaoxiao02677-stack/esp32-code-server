#pragma once
/* ============================================================
 * app_config.h — 布局常量 / 状态枚举 / 进度结构
 * 硬件：ESP32-S3 + 240x240 方形 IPS (ST7789)
 * ============================================================ */
#include <stdint.h>
#include <stdbool.h>

#ifdef __cplusplus
extern "C" {
#endif

/* ── 屏幕 ───────────────────────────────────────── */
#define SCR_W   240
#define SCR_H   240

/* ── 方屏布局（与 esp32_boot_preview_square.html 一致）───── */
#define CY_BASE     126     /* 待机 / 聆听时宠物中心 y            */
#define CY_SPEAK    156     /* 回应时下移 30px，给气泡让位        */
#define FACE_RX     70      /* 脸宽半径（方屏可放大）             */
#define FACE_RY     62
#define TOPBAR_Y    22      /* 顶栏：左时间 / 右 Wi-Fi + 电量     */
#define VOL_Y       218     /* 底部音量条                         */
#define BUBBLE_W    200     /* 气泡宽度                           */
#define BUBBLE_H    50

/* ── 开机动画总时长（秒）────────────────────────── */
#define BOOT_DUR_FULL   3.80f
#define BOOT_DUR_WAKE   0.60f
#define BOOT_DUR_BIRTH  4.40f

/* ── UI 状态 ────────────────────────────────────── */
typedef enum {
    UI_ST_IDLE = 0,     /* 待机   */
    UI_ST_LISTEN,       /* 聆听中 */
    UI_ST_THINK,        /* 思考中（等待回复）*/
    UI_ST_SPEAK,        /* 回应中 */
    UI_ST_MENU,         /* 菜单   */
} ui_state_t;

/* ── 开机动画进度（0..1，绘制侧只读）────────────── */
typedef struct {
    float seed;      /* ① 种子微光   */
    float ripple;    /* ② 涟漪扩散   */
    float outline;   /* ③ 轮廓生长   */
    float fill;      /* ④ 填充注入   */
    float bg;        /* ④ 背景提亮（与 fill 严格同步）*/
    float ear;       /* ⑤ 耳朵弹出   */
    float blush;     /* ⑥ 腮红点亮   */
    float eye;       /* ⑦ 睁眼       */
    float bubble;    /* ⑧ 问候气泡   */
    float settle;    /* ⑨ 落位待机   */
    float confetti;  /*    纪念日彩蛋 */
} boot_prog_t;

/* ── 宠物表情皮肤 ───────────────────────────────── */
typedef enum {
    PET_SKIN_CAT = 0,   /* 猫 · 尖耳   */
    PET_SKIN_BEAR,      /* 小熊 · 圆耳 */
    PET_SKIN_CLOUD,     /* 云兽 · 云耳 */
    PET_SKIN_MAX
} pet_skin_t;

/* ── 开机分支 ───────────────────────────────────── */
typedef enum {
    BOOT_FULL = 0,      /* 完整 3.8s         */
    BOOT_WAKE,          /* 深度唤醒 0.6s 短版 */
    BOOT_WIFI,          /* 未配网 · 结尾二维码 */
    BOOT_BIRTH,         /* 纪念日 · 撒花彩蛋  */
} boot_branch_t;

#ifdef __cplusplus
}
#endif

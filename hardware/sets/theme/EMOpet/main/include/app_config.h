#pragma once
/* ============================================================
 * app_config.h — EMOPET 风格机器人脸
 * 屏幕：240x240 方形 IPS (ST7789) · 黑底 + 发光眼
 * ============================================================ */
#include <stdint.h>
#include <stdbool.h>
#include "lvgl.h"

#ifdef __cplusplus
extern "C" {
#endif

#define SCR_W 240
#define SCR_H 240

/* 眼睛布局 —— 幼态化：更大、更靠下、间距更开 */
#define EYE_LX       80
#define EYE_RX      160
#define EYE_CY      126      /* 眼睛中心 y（offY 在此基础上偏移）*/

/* 眼睛形状 */
typedef enum {
    EM_DOT = 0,     /* 圆角矩形 / 胶囊（基础眼）*/
    EM_ARC,         /* 弯月：bend>0 笑 ∩，bend<0 哭 ∪ */
    EM_HEART,       /* 爱心 */
    EM_STAR,        /* 五角星 */
    EM_SPIRAL,      /* 螺旋（晕）*/
    EM_X,           /* 叉（断线 / 死机）*/
    EM_QR,          /* 配网二维码（整屏，忽略 w/h）*/
    EM_NONE,        /* 不画（纯黑，用于转场瞬间）*/
} em_shape_t;

/* 表情 ID */
typedef enum {
    EMO_IDLE = 0,
    EMO_LISTEN,
    EMO_SPEAK,
    EMO_HAPPY,
    EMO_LOVE,
    EMO_SLEEPY,
    EMO_SAD,
    EMO_SURPRISE,
    EMO_ANGRY,
    EMO_WINK,
    EMO_STAR,
    EMO_DIZZY,
    EMO_THINK,
    EMO_SHY,
    EMO_OFFLINE,
    EMO_LOWBATT,
    EMO_BOOT,
    EMO_WIFI,
    EMO_MAX
} emo_id_t;

/* 单只眼睛的参数（可左右独立）*/
typedef struct {
    em_shape_t shape;
    float w, h;         /* 宽高（像素）*/
    float bend;         /* 弧线弯曲：>0 笑，<0 哭 */
    float glow;         /* 辉光强度 0..1.6 */
    int   offY;         /* 整体上下偏移 */
    float tilt;         /* 倾角（左右反向）*/
    bool  pulse;        /* 呼吸闪烁（低电量）*/
    bool  blush;        /* 腮红 */
} emo_t;

/* 眼睛配色 */
typedef struct {
    lv_color_t main;    /* 主色（辉光）*/
    lv_color_t core;    /* 芯色（近白）*/
} eye_color_t;

#ifdef __cplusplus
}
#endif

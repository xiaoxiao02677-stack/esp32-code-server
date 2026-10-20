#pragma once

// ════════════════════════════════════════════════════════════════════════
// emo_skin_types.h — EMOpet 主题 · 公共类型与布局常量
// ════════════════════════════════════════════════════════════════════════
//
// 来源：hardware/sets/theme/EMOpet/main/include/app_config.h（240x240 方屏
// 常量）移植进主固件。所有坐标不写死 240：以 240 基准值经 emo_layout_t
// 换算，适配 240 圆屏 / 320x240 横屏 / 240x320 竖屏（对齐 YhSkinProfile）。
//
// C/C++ 混编注意：本头同时被 .c（emo_face.c 等）与 .cc（emo_display.cc）
// 引用，全部内容保持 C 兼容（无类、无引用参数）。

#include <stdbool.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

// ── 240 基准布局（经 emo_layout_t 缩放后使用）────────
#define EMO_BASE_W          240
#define EMO_BASE_H          240
#define EMO_EYE_LX          80      /* 左眼中心 x（240 基准）*/
#define EMO_EYE_RX          160     /* 右眼中心 x */
#define EMO_EYE_CY          126     /* 眼睛中心 y */
#define EMO_BLUSH_DY        34      /* 腮红中心相对眼睛 y */
#define EMO_WAVE_BASE       216     /* 底部声波条基线 y */

// ── 眼睛形状（em_shape_t，与源工程一致）──────────────
typedef enum {
    EM_DOT = 0,     /* 圆角矩形 / 胶囊（基础眼）*/
    EM_ARC,         /* 弯月：bend>0 笑 ∩，bend<0 哭 ∪ */
    EM_HEART,       /* 爱心 */
    EM_STAR,        /* 五角星 */
    EM_SPIRAL,      /* 螺旋（晕）*/
    EM_X,           /* 叉（断线 / 死机）*/
    EM_NONE,        /* 不画（纯黑，用于转场瞬间）*/
} em_shape_t;

// 注：源工程的 EM_QR（整屏二维码）不移植——主固件配网走 Wi-Fi 配网页 +
// 屏幕提示，二维码渲染由基类系统卡片负责。

// ── 表情 ID（emo_id_t，与源工程一致，去掉 BOOT/WIFI 系统态）──
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
    EMO_LOWBATT,
    EMO_MAX
} emo_id_t;

// ── 单只眼睛参数（可左右独立）────────────────────────
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

// ── 布局换算：240 基准 → 实际屏参 ───────────────────
typedef struct {
    int width;       /* 实际屏宽 */
    int height;      /* 实际屏高 */
    int short_side;  /* min(w,h) */
    int eye_lx;      /* 左眼中心 x */
    int eye_rx;      /* 右眼中心 x */
    int eye_cy;      /* 眼睛中心 y */
    int blush_dy;    /* 腮红相对眼睛 y 偏移 */
    int wave_base;   /* 声波条基线 y */
    float scale;     /* 短边 / 240（眼睛尺寸基准缩放）*/
} emo_layout_t;

// 由宽高推导布局（240 基准等比缩放；竖屏时眼部整体上移避开底部提示条）
emo_layout_t emo_layout_make(int width, int height);

#ifdef __cplusplus
}
#endif

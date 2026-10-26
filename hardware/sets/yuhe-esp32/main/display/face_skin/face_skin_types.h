#pragma once

// ════════════════════════════════════════════════════════════════════════
// 极简脸 face 主题 · 类型与表情参数表（face_skin_types.h）
// ════════════════════════════════════════════════════════════════════════
//
// 设计来源：hardware/sets/theme/face/docs/face_ui_preview.html
//（HTML 高保真原稿「Square Face · Minimal」，240×240 黑底 + 双发光眼 + 嘴）。
//
// 设计原则（与原稿逐项对齐）：
//   · 眼睛 = 圆角胶囊，柔光用 box-shadow 双层 —— LVGL 无阴影叠加，等效
//     方案：每只眼 3 层同心圆（辉光外圈 @大半透明 / 主体 / 无内芯，
//     主体纯色 #E8F4F6），硬边分层即风格（RGB565 纪律，同 dengyu 光萤）。
//   · 嘴 = 圆角矩形，宽/高/圆角/纵移 四参数随表情连续过渡（lerp 0.08）。
//   · 眨眼 = scaleY 压扁 160ms（余弦缓动）。
//   · 呼吸 = 全局 scale ±2.5%（idle 1.1s / sleepy 1.6s 周期）。
//   · 游荡 = idle 时每帧小概率重选目标点 ±3.5px，lerp 0.045 跟随。
//   · talking 点头 = 眼睛 y 加 ±1.8px 正弦（180ms 周期）。
//   · interact 回弹 = 520ms 正弦 0→+16%→0（傲娇小反应）。
//
// 坐标基准 240×240（HTML 原稿），其他屏型按 profile 几何换算（见
// face_geom_t）：320 宽屏眼距拉开居中；240×320 竖屏脸上移留底部留白。

#include <lvgl.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

// ---- 表情（HTML expressions 表 8 态 + 关机态）----
typedef enum {
    FACE_EXPR_IDLE = 0,     // 待机：呼吸+游荡+眨眼，嘴 36×7
    FACE_EXPR_TALKING,      // 说话：点头+嘴开合 90ms 拟态
    FACE_EXPR_HAPPY,        // 开心：眼 +8% 放大，嘴 48×14 圆角 30 上移 4
    FACE_EXPR_SHY,          // 害羞：眼 -8% 缩小，嘴 22×6 上移 -2
    FACE_EXPR_THINK,        // 思考：眼 -4%，嘴 18×5 圆角 10（一字嘴）
    FACE_EXPR_SLEEPY,       // 困倦：眼 -12%，嘴 40×5，呼吸更缓
    FACE_EXPR_SURPRISE,     // 惊讶：眼 +18%，嘴 16×22 圆角 50（O 嘴）
    FACE_EXPR_ANGRY,        // 生气：眼 -5%，嘴 32×6 圆角 4（方嘴）下移 3
    FACE_EXPR_MAX
} face_expr_t;

// 一套表情参数（HTML expressions 配置表 1:1 搬运，px 为 240 基准）
typedef struct {
    int16_t eye_scale_pct;   // 眼睛缩放百分比（100 = 原大）
    int16_t look_amp_x;      // 游荡幅度 x（0 = 不游荡，表情锁定直视）
    int16_t look_amp_y;      // 游荡幅度 y
    int16_t mouth_w;         // 嘴宽
    int16_t mouth_h;         // 嘴高
    int16_t mouth_r;         // 嘴圆角
    int16_t mouth_y;         // 嘴纵移（正 = 下移）
} face_expr_params_t;

const face_expr_params_t* face_expr_params(face_expr_t expr);

// ---- 几何（240 基准，构造时按 profile 换算存好）----
typedef struct {
    int16_t eye_d;          // 眼睛直径（72 基准）
    int16_t eye_l_x;        // 左眼左上 x（28 基准）
    int16_t eye_r_x;        // 右眼左上 x（140 基准）
    int16_t eye_y;          // 眼睛左上 y（58 基准）
    int16_t mouth_cx;       // 嘴中心 x
    int16_t mouth_y;        // 嘴基线 y（158 基准，中心点）
    int16_t glow_d;         // 辉光外圈直径（eye_d 的 1.22 倍向上取整）
    int16_t screen_w;       // 屏宽（布局换算用）
    int16_t screen_h;       // 屏高
} face_geom_t;

// 按屏型推导几何（240 基准 × 等比 + 横屏拉距/竖屏上移）
face_geom_t face_geom_make(int width, int height, bool round_screen);

// ---- 动效参数（ms / 概率；概率已按 30fps 帧率换算）----
typedef struct {
    uint16_t blink_ms;          // 眨眼时长 160
    uint16_t blink_prob_permyriad;  // 每帧眨眼概率（万分之）70 —— HTML 60fps 下
                                    // 0.35%/帧 ×2 = 30fps 等效（平均 ~4.8s 眨一次）
    uint16_t wander_prob_permyriad; // 每帧重选游荡点概率 120 —— HTML 0.6%/帧 ×2
                                    //（平均 ~2.8s 重选一次，与原稿每秒重选率一致）
    uint16_t interact_ms;       // 回弹时长 520
    uint16_t interact_amp_pct;  // 回弹幅度 16%
    uint16_t talk_nod_period;   // 点头周期 180
    uint16_t talk_mouth_period; // 嘴开合周期 90
    uint16_t talk_mouth_amp;    // 嘴开合幅度 10px
    uint8_t  lerp_follow;       // 游荡跟随系数（百分比/帧 4.5% → 5）
    uint8_t  lerp_mouth;        // 嘴过渡系数（8%/帧）
} face_motion_t;

const face_motion_t* face_default_motion(void);

// ---- 配色 ----
// 眼/嘴主体 #E8F4F6（RGB565 0xEFF6），辉光 #B4DCFF @ 半透明分层
#define FACE_COLOR_BODY  0xE8F4F6
#define FACE_COLOR_GLOW  0xB4DCFF

#ifdef __cplusplus
}
#endif

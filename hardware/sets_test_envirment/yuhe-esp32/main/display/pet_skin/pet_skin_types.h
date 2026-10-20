#pragma once

// ════════════════════════════════════════════════════════════════════════
// pet_skin_types.h — 像素宠物主题 · 公共类型与布局常量
// ════════════════════════════════════════════════════════════════════════
//
// 来源：hardware/sets/theme/像素宠物/main/include/app_config.h（240x240 方屏
// 常量）移植进主固件。所有坐标不写死 240：以 240 基准值经 PetLayout 换算，
// 适配 240 圆屏 / 320x240 横屏 / 240x320 竖屏（对齐 YhSkinProfile 机制）。
//
// C/C++ 混编注意：本头同时被 .c（pet_canvas.c 等）与 .cc（pet_skin_display.cc）
// 引用，全部内容保持 C 兼容（无类、无引用参数）。

#include <stdbool.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

// ── 开机动画总时长（秒）──────────────────────────────
#define PET_BOOT_DUR_FULL   3.80f
#define PET_BOOT_DUR_WAKE   0.60f
#define PET_BOOT_DUR_BIRTH  4.40f

// ── 240 基准布局（经 PetLayout 缩放后使用）──────────
#define PET_BASE_W          240
#define PET_BASE_H          240
#define PET_CY_BASE         126   /* 待机/聆听时宠物中心 y（240 基准）*/
#define PET_CY_SPEAK        156   /* 回应时下移 30px 给气泡让位 */
#define PET_FACE_RX         70    /* 脸宽半径 */
#define PET_FACE_RY         62
#define PET_EAR_DX          34    /* 耳朵横偏移（120±34）*/
#define PET_EAR_BASE_DY     -46   /* 耳根相对 cy */
#define PET_EAR_TIP_DY      -74
#define PET_EYE_DX          22    /* 眼睛横偏移（120±22）*/
#define PET_BLUSH_DX        44    /* 腮红横偏移（120±44）*/
#define PET_GRID            8     /* 像素风网格尺寸 */

// ── UI 状态（由 PetSkinDisplay 的协议钩子驱动）───────
typedef enum {
    PET_UI_IDLE = 0,     /* 待机   */
    PET_UI_LISTEN,       /* 聆听中 */
    PET_UI_THINK,        /* 思考中（等待回复）*/
    PET_UI_SPEAK,        /* 回应中 */
} pet_ui_state_t;

// ── 宠物表情（协议 emotion 字符串映射后的内部态）────
typedef enum {
    PET_EXPR_NEUTRAL = 0,  /* 待机 */
    PET_EXPR_HAPPY,        /* 开心（笑眼）*/
    PET_EXPR_SAD,          /* 难过（下垂眼）*/
    PET_EXPR_SURPRISE,     /* 惊讶（圆睁）*/
    PET_EXPR_SLEEPY,       /* 困倦（眯眼）*/
    PET_EXPR_MAX
} pet_expr_t;

// ── 宠物皮肤（双击轮换）─────────────────────────────
typedef enum {
    PET_SKIN_CAT = 0,   /* 猫 · 尖耳   */
    PET_SKIN_BEAR,      /* 小熊 · 圆耳 */
    PET_SKIN_CLOUD,     /* 云兽 · 云耳 */
    PET_SKIN_MAX
} pet_skin_id_t;

// ── 开机分支 ────────────────────────────────────────
typedef enum {
    PET_BOOT_FULL = 0,   /* 完整 3.8s          */
    PET_BOOT_WAKE,       /* 深度唤醒 0.6s 短版 */
    PET_BOOT_WIFI,       /* 未配网 · 结尾二维码（本固件暂不用，占位）*/
    PET_BOOT_BIRTH,      /* 纪念日 · 撒花彩蛋  */
} pet_boot_branch_t;

// ── 开机动画进度（0..1，绘制侧只读）─────────────────
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
} pet_boot_prog_t;

// ── 布局换算：240 基准 → 实际屏参 ───────────────────
// 独立于 YhSkinProfile（C 文件不能引 C++ 头），机制一致：短边等比缩放。
typedef struct {
    int width;       /* 实际屏宽 */
    int height;      /* 实际屏高 */
    int short_side;  /* min(w,h) */
    int cx;          /* 屏幕中心 x */
    int cy_base;     /* 待机宠物中心 y（240 基准 126 等比换算）*/
    int cy_speak;    /* 回应宠物中心 y */
    int face_rx;
    int face_ry;
    int ear_dx;
    int ear_base_dy;
    int ear_tip_dy;
    int eye_dx;
    int blush_dx;
    int grid;        /* 像素网格（≥4，随屏适当放大）*/
} pet_layout_t;

// 由宽高推导布局（240 基准等比缩放；竖屏时 cy 略上移避开底部提示条）
pet_layout_t pet_layout_make(int width, int height);

#ifdef __cplusplus
}
#endif

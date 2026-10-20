#pragma once

// ════════════════════════════════════════════════════════════════════════
// 像素宠物主题 · 显示层（pet_skin_display.h）
// ════════════════════════════════════════════════════════════════════════
//
// 移植自 hardware/sets/theme/像素宠物 独立工程。设计：PetSkinDisplay 继承
// YhSkinDisplay，白嫖其全部久经考验的骨架——
//   · 壁纸双槽（idle/boot）与 NVS 生命周期
//   · 字体退休池（SetTextFont 悬垂崩溃的根治方案）
//   · 锁纪律（DisplayLockGuard 递归锁）
//   · 基类占位对象族（SetTheme/ShowNotification null 崩溃防御）
//   · profile 几何适配（240 圆屏 / 320x240 / 240x320）+ chrome 控件
//     （时间/电量/气泡/提示）与系统卡片（配网/激活码/升级）
// 只替换视觉层：像素宠物 canvas 取代背景图+表情图，3.8s 出生动画取代品牌 splash。
//
// 主题切换：Kconfig choice YH_UI_THEME（main/Kconfig.projbuild）
//   · YH_UI_THEME_XIAOYOU（默认）—— 原主题（小智/小柚/琳琳），直接构造 YhSkinDisplay
//   · YH_UI_THEME_PIXELPET —— 像素宠物，本类
// build.py --theme xiaoyou|pixel-pet 注入对应 sdkconfig 行。
//
// 板级用法（四个版型同构，见各板 yh_set_*.cc）：
//   #if CONFIG_YH_UI_THEME_PIXELPET
//       display_ = new PetSkinDisplay(panel_io, panel, W, H, OX, OY,
//                                     MX, MY, SWAP, YhSkinProfile::Round240(true));
//   #else
//       display_ = new YhSkinDisplay(...);   // 原样
//   #endif

#include "display/yh_skin/yh_skin_display.h"
#include "display/pet_skin/pet_skin_types.h"

#include <lvgl.h>

class PetSkinDisplay : public YhSkinDisplay {
public:
    // 构造签名与 YhSkinDisplay 完全一致（板级只换类名，参数原样传入）
    PetSkinDisplay(esp_lcd_panel_io_handle_t panel_io, esp_lcd_panel_handle_t panel, int width,
                   int height, int offset_x, int offset_y, bool mirror_x, bool mirror_y,
                   bool swap_xy, const YhSkinProfile& profile);
    ~PetSkinDisplay() override;

    // ---- Display 渲染层覆写（协议语义与基类一致）----
    void SetupUI() override;
    void SetEmotion(const char* emotion) override;
    void SetChatMessage(const char* role, const char* content) override;
    void ShowBootSplash() override;
    void DismissBootSplash() override;
    void HandleKeyEvent(int ev) override;
    void NextEasterEgg() override;
    void Tick1s() override;

private:
    void StartFrameTimer();
    void OnFrameTimer();  // lv_timer 回调：出生动画推进 + 眨眼/说话拟态

    pet_layout_t layout_{};         // 240 基准 → 实际屏换算（构造时算好）
    lv_obj_t* pet_canvas_obj_ = nullptr;  // 宠物 canvas（pet_canvas.c 单例句柄）
    lv_timer_t* frame_timer_ = nullptr;   // 常驻帧 timer（33ms）

    pet_skin_id_t skin_id_ = PET_SKIN_CAT;
    pet_expr_t expr_ = PET_EXPR_NEUTRAL;

    bool boot_animating_ = false;    // 出生/唤醒动画播放中
    bool speaking_ = false;          // 上一帧是否说话态（脏标记）
    bool blink_last_ = false;        // 上一帧是否眨眼（脏标记）
    bool frame_div_ = false;         // 隔帧分频（说话态 15fps）
    uint32_t blink_cycle_ms_ = 0;    // 当前眨眼周期
    uint32_t last_blink_reseed_ = 0; // 上次重掷眨眼周期时刻

    int tick_count_ = 0;             // 1s 节拍计数（彩蛋窗口计时）
    int easter_until_tick_ = -1;     // 彩蛋窗口截止 tick（-1 = 无窗口）
};

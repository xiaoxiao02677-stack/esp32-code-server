#pragma once

// ════════════════════════════════════════════════════════════════════════
// EMOpet 主题 · 显示层（emo_skin_display.h）
// ════════════════════════════════════════════════════════════════════════
//
// 移植自 hardware/sets/theme/EMOpet 独立工程（240x240 机器人发光眼）。
// 与 PetSkinDisplay（像素宠物）同一集成模式：EmoSkinDisplay 继承
// YhSkinDisplay，白嫖其全部久经考验的骨架——
//   · 壁纸双槽（idle/boot）与 NVS 生命周期
//   · 字体退休池（SetTextFont 悬垂崩溃的根治方案）
//   · 锁纪律（DisplayLockGuard 递归锁）
//   · 基类占位对象族（SetTheme/ShowNotification null 崩溃防御）
//   · profile 几何适配（240 圆屏 / 320x240 / 240x320）+ chrome 控件
//     （时间/电量/气泡/提示）与系统卡片（配网/激活码/升级）
// 只替换视觉层：EMOpet 发光眼 canvas 取代表情图，
// "压扁→渐亮睁开"的 0.5s 睁眼接管开机首帧（无需独立出生动画模块）。
//
// 主题切换：Kconfig choice YH_UI_THEME（main/Kconfig.projbuild）
//   · YH_UI_THEME_XIAOYOU（默认）—— 原主题（小智/小柚/琳琳）
//   · YH_UI_THEME_PIXELPET —— 像素宠物
//   · YH_UI_THEME_EMOPET —— EMOpet 机器人眼（本类）
// build.py --theme xiaoyou|pixel-pet|emopet 注入对应 sdkconfig 行。
//
// 板级用法（四个版型同构，见各板 yh_set_*.cc）：
//   #if CONFIG_YH_UI_THEME_EMOPET
//       display_ = new EmoSkinDisplay(panel_io, panel, W, H, OX, OY,
//                                     MX, MY, SWAP, YhSkinProfile::Round240(true));
//   #else
//       display_ = new YhSkinDisplay(...);   // 原样
//   #endif

#include "display/yh_skin/yh_skin_display.h"
#include "display/emo_skin/emo_skin_types.h"

#include <lvgl.h>

class EmoSkinDisplay : public YhSkinDisplay {
public:
    // 构造签名与 YhSkinDisplay 完全一致（板级只换类名，参数原样传入）
    EmoSkinDisplay(esp_lcd_panel_io_handle_t panel_io, esp_lcd_panel_handle_t panel, int width,
                   int height, int offset_x, int offset_y, bool mirror_x, bool mirror_y,
                   bool swap_xy, const YhSkinProfile& profile);
    ~EmoSkinDisplay() override;

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
    void OnFrameTimer();  // lv_timer 回调：说话能量拟态 + 声波开关

    emo_layout_t layout_{};                // 240 基准 → 实际屏换算（构造时算好）
    lv_obj_t* emo_canvas_obj_ = nullptr;   // EMOpet canvas（emo_face.c 单例句柄）
    lv_timer_t* frame_timer_ = nullptr;    // 常驻帧 timer（33ms）

    emo_id_t emo_id_ = EMO_IDLE;           // 当前表情

    bool speaking_ = false;                // 上一帧是否说话态（声波开关沿）
    int tick_count_ = 0;                   // 1s 节拍计数（彩蛋窗口计时）
    int easter_until_tick_ = -1;           // 彩蛋窗口截止 tick（-1 = 无窗口）
    uint8_t color_index_ = 0;              // 当前眼睛配色（双击轮换）
    uint32_t last_bat_check_ = 0;          // 低电量脉搏喂入节流
};

#pragma once

// ════════════════════════════════════════════════════════════════════════
// 极简脸 face 主题 · 显示层（face_skin_display.h）
// ════════════════════════════════════════════════════════════════════════
//
// 设计原稿：hardware/sets/theme/face/docs/face_ui_preview.html
//（Square Face · Minimal，240×240 黑底 + 双发光眼 + 嘴，纯脸零文字）。
//
// FaceSkinDisplay 继承 YhSkinDisplay，白嫖骨架（壁纸双槽 / 字体退休池 /
// 锁纪律 / 占位族 / 系统卡片 / profile 几何），只换视觉层：
//   · face_core 渲染核心取代背景图 + emoji 表情 + 气泡
//   · 纯脸零文字：不建任何 label，无字体依赖（协议文本事件全部只做
//     状态驱动，脸上不落一字；系统卡片〔配网/激活/升级〕例外——那是
//     功能界面，不是脸的一部分，用户明确选择保留）
//   · 无用户壁纸时隐藏 bg_image_ 露出纯黑底（忠实原稿）；用户下发
//     壁纸后恢复显示（用户意志优先）——覆写 SetWallpaper/ClearWallpaper
//
// 主题切换：Kconfig choice YH_UI_THEME（main/Kconfig.projbuild）
//   · YH_UI_THEME_FACE —— 极简脸，本类
// build.py --theme face 注入 CONFIG_YH_UI_THEME_FACE=y。
//
// 板级用法（四个版型同构，见各板 yh_set_*.cc）：
//   #if CONFIG_YH_UI_THEME_FACE
//       display_ = new FaceSkinDisplay(panel_io, panel, W, H, OX, OY,
//                                      MX, MY, SWAP, YhSkinProfile::Round240(false));
//   #endif
//
// 表情双层调和（8 态既是模式又是情绪，显示层负责分诊）：
//   模式级（250ms 设备态轮询，真源）：Speaking→talking（点头+嘴拟态）、
//     Connecting/Upgrading→think、FatalError→angry、其余→情绪记忆
//   情绪级（协议 SetEmotion / 按键预置）：映射 8 态存 expr_ 记忆，
//     非说话态直接上脸；说话中只记不切，TTS 结束轮询自动回落
//   interact 彩蛋窗口（双击，520ms 回弹 + 1.8s 表情）：轮询与 SetEmotion
//     全部让路（face_core_in_interact 判断），窗口过后设备态接管
//
// 帧驱动：单个 lv_timer（33ms ≈ 30fps）常驻 taskLVGL，内部 250ms 间隔
// 做设备态对账（省一个 timer，pet 单 timer 先例）；说话态隔帧降 15fps。

#include "display/yh_skin/yh_skin_display.h"
#include "face_core.h"
#include "face_skin_types.h"

#include <lvgl.h>

class FaceSkinDisplay : public YhSkinDisplay {
public:
    // 构造签名与 YhSkinDisplay 完全一致（板级只换类名）
    FaceSkinDisplay(esp_lcd_panel_io_handle_t panel_io, esp_lcd_panel_handle_t panel, int width,
                    int height, int offset_x, int offset_y, bool mirror_x, bool mirror_y,
                    bool swap_xy, const YhSkinProfile& profile);
    ~FaceSkinDisplay() override;

    // ---- Display 渲染层覆写（协议语义与基类一致）----
    void SetupUI() override;
    void SetEmotion(const char* emotion) override;
    void SetChatMessage(const char* role, const char* content) override;
    bool SetWallpaper(const lv_img_dsc_t* image) override;
    bool ClearWallpaper() override;
    void HandleKeyEvent(int ev) override;
    void NextEasterEgg() override;

    // Tick1s 不覆写：基类节拍（时间刷新/彩蛋超时）照常运行。早晚问候走
    // LcdDisplay::SetEmotion 限定调用（非虚）且文案在气泡里——脸主题里
    // 两者均不可见，属纯文字特性按选型放弃；协议 SetEmotion 完整驱动。

private:
    void OnFrameTimer();      // 30fps：face_core_tick + 250ms 设备态对账
    void PollDeviceState();   // 设备态 → 模式级表情（interact 窗口冻结）
    void ShowFaceOrWallpaper();  // 无用户壁纸 → 隐藏 bg_image_ 露纯黑底

    face_core_t* core_ = nullptr;      // 渲染核心（对象树 + 动画状态机）
    lv_timer_t* frame_timer_ = nullptr;  // 唯一常驻 timer（33ms）
    uint32_t last_poll_ms_ = 0;        // 上次设备态对账时刻
    bool frame_div_ = false;           // 说话态隔帧分频
    face_expr_t expr_ = FACE_EXPR_IDLE;  // 情绪记忆（协议/按键驱动）
};

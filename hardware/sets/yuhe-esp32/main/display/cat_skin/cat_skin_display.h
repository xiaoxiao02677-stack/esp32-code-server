#pragma once

// ════════════════════════════════════════════════════════════════════════
// 猫咪 cat 主题 · 显示层（cat_skin_display.h）
// ════════════════════════════════════════════════════════════════════════
//
// 移植自 G:\demo\22 cat\esp32_cat_ui（8 段表情动画 + 嘴形拟态的猫脸），
// 融入 yuhe 六主题体系（build.py --theme cat）。
//
// CatSkinDisplay 继承 YhSkinDisplay，白嫖骨架（壁纸双槽 / 字体退休池 /
// 锁纪律 / 占位族 / 系统卡片 / profile 几何），只换视觉层：
//   · cat_anim 渲染核心取代背景图 + emoji 表情 + 气泡（帧动画猫脸）
//   · 待机随机循环：60% idle / 30% happy+shy / 10% 情绪（原项目分布）
//   · 状态角标（cat_badge_t）：右上角彩色圆点，设备态一眼可辨——
//     零文字 UI 的第二信号通道（face 主题状态辉光同款哲学）
//   · 系统卡片（配网/激活码/升级）例外保留——功能界面不是脸
//
// 状态区分设计（用户硬需求：按 BOOT 后必须知道自己处于哪个状态）：
//   待机 idle   = 随机猫动画循环 + 淡蓝角标
//   聆听 listen = idle1 定格注视帧 + 青绿角标（动画骤停 = 醒目差异）
//   说话 speak  = 猫脸动画 + 嘴形拟态轮换 + 暖橙角标
//   连接        = 猫脸动画 + 琥珀角标慢闪
//   致命错误    = angry 动画 + 珊瑚红角标
//   静音长按    = 灰角标短显 2s（板级已做音量切换，这里只做视觉）
//
// BOOT 键（板级已做行为，皮肤层只做视觉反馈——HandleKeyEvent）：
//   短按 0：进聆听——idle1 定格 + 青绿角标即时亮（不等 250ms 轮询）
//   双击 1：彩蛋动画（cry/angry/sad 随机，播完回待机循环）
//   长按 2：静音切换视觉（灰角标 2s；非待机态眨眼/不动）
//
// 开机流程（WiFi/配网）：基类 SetupUI 建品牌 splash + 系统卡片，
// Connecting/Activating 态轮询自动亮琥珀角标；配网卡片由基类
// ShowNotification 白嫖（用户要求"不要忘记配网"——复用不重造）。
//
// 帧驱动：单个 lv_timer（66ms ≈ 15fps，与素材帧率一致）常驻 taskLVGL，
// 内部 250ms 间隔做设备态对账（face 主题同款单 timer 先例）。

#include "cat_anim.h"
#include "display/yh_skin/yh_skin_display.h"

#include <lvgl.h>

class CatSkinDisplay : public YhSkinDisplay {
public:
    // 构造签名与 YhSkinDisplay 完全一致（板级只换类名）
    CatSkinDisplay(esp_lcd_panel_io_handle_t panel_io, esp_lcd_panel_handle_t panel, int width,
                   int height, int offset_x, int offset_y, bool mirror_x, bool mirror_y,
                   bool swap_xy, const YhSkinProfile& profile);
    ~CatSkinDisplay() override;

    // ---- Display 渲染层覆写（协议语义与基类一致）----
    void SetupUI() override;
    void SetEmotion(const char* emotion) override;
    void SetChatMessage(const char* role, const char* content) override;
    bool SetWallpaper(const lv_img_dsc_t* image) override;
    bool ClearWallpaper() override;
    void HandleKeyEvent(int ev) override;
    void NextEasterEgg() override;

    // Tick1s 不覆写：基类节拍（彩蛋超时）照常运行。早晚问候走
    // LcdDisplay::SetEmotion 限定调用（非虚）且文案在气泡里——猫主题里
    // 均不可见，属纯文字特性按选型放弃；协议 SetEmotion 完整驱动。

private:
    void OnFrameTimer();      // 15fps：cat_anim_tick + 250ms 设备态对账
    void PollDeviceState();   // 设备态 → 动画 + 角标（彩蛋窗口冻结）
    void ShowCatOrWallpaper();  // 无用户壁纸 → 隐藏 bg_image_ 露黑底

    cat_anim_t* anim_ = nullptr;        // 渲染核心（canvas + 播放状态机）
    lv_timer_t* frame_timer_ = nullptr;  // 唯一常驻 timer（66ms）
    uint32_t last_poll_ms_ = 0;          // 上次设备态对账时刻
    cat_anim_id_t expr_ = CAT_ANIM_IDLE1;  // 情绪记忆（协议 SetEmotion 驱动）
    bool was_speaking_ = false;          // 说话→待机转换检测（情绪余韵播一次）
};

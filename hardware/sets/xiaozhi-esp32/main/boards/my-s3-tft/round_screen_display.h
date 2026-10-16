#pragma once

#include "../../display/lcd_display.h"

// 圆屏（240x240，安全区半径100）小柚风格 Display（my-s3-tft 专用皮肤）
//
// 布局（需求规格）：
//   顶部 y=10 时间（14号字）/ y=28 电量百分比（14号字）
//   中心 y=-15 表情头像（emoji 大字号，映射 LLM emotion 协议名）
//   底部 y=-55 气泡 200x50 圆角16 粉边框（AI/系统回复，180宽自动换行）
//   底部 y=-12 操作提示「短按说话 长按菜单」
//   背景：0x2A1633 -> 0x120B18 垂直渐变
//
// 设计原则（"不要影响原 api 功能"）：
// - 只覆写渲染层（SetupUI/SetEmotion/SetChatMessage/SetStatus/UpdateStatusBar）
// - Application/协议/MCP/音频链路零改动
// - SetEmotion 兼容服务器协议名（happy/sad/sleepy/angry/neutral/thinking/
//   laughing/loving/embarrassed/surprised/crying/winking/cool/relaxed/...）
//   全量走 noto_emoji_get_utf8，未映射名自动回退
class RoundScreenDisplay : public SpiLcdDisplay {
public:
    RoundScreenDisplay(esp_lcd_panel_io_handle_t panel_io, esp_lcd_panel_handle_t panel,
                       int width, int height, int offset_x, int offset_y,
                       bool mirror_x, bool mirror_y, bool swap_xy);

    void SetupUI() override;
    void SetEmotion(const char* emotion) override;
    void SetChatMessage(const char* role, const char* content) override;
    void SetStatus(const char* status) override;
    void UpdateStatusBar(bool update_all = false) override;
    void ClearChatMessages() override;
    void ShowNotification(const char* notification, int duration_ms) override;
    void SetTheme(Theme* theme) override;

    // ---- 单 BOOT 键三事件 UI 侧行为（0=短按 1=双击 2=长按）----
    // Application 状态机优先处理（原逻辑），此方法只做皮肤层的增强反馈
    void HandleKeyEvent(int ev);

    // 表情彩蛋轮播（待机时双击触发）
    void NextEasterEgg();

    // 1 秒节拍（板级 esp_timer 调用）：夜间睡觉/早晨问好/低电量提醒
    void Tick1s();

private:
    void BuildMainScreen();
    void SetBubbleText(const char* text);

    lv_obj_t* avatar_label_ = nullptr;        // 中心表情（emoji 字体）
    lv_obj_t* bubble_ = nullptr;              // 气泡容器 200x50
    lv_obj_t* bubble_label_ = nullptr;        // 气泡文字
    lv_obj_t* round_time_label_ = nullptr;    // 顶部时间 y=10
    lv_obj_t* round_bat_label_ = nullptr;     // 顶部电量 y=28
    lv_obj_t* round_hint_label_ = nullptr;    // 底部提示 y=-12

    // 皮肤配色（需求规格）
    static constexpr uint32_t kColorBgTop = 0x2A1633;      // 背景渐变顶
    static constexpr uint32_t kColorBgBottom = 0x120B18;   // 背景渐变底
    static constexpr uint32_t kColorPrimary = 0xFF7AA2;    // 主粉（边框/强调）
    static constexpr uint32_t kColorBubbleBg = 0x3A2440;   // 气泡底
    static constexpr uint32_t kColorTextMain = 0xFFF7FB;   // 主文字
    static constexpr uint32_t kColorTextSub = 0xC9B8D9;    // 次文字
    static constexpr uint32_t kColorTextHint = 0x8B7A99;   // 底部提示

    int egg_index_ = 0;
    int easter_egg_until_tick_ = -1;  // 彩蛋表情展示截止 tick（10 秒后回 neutral）
    int tick_count_ = 0;
    int last_bat_percent_ = -1;
};

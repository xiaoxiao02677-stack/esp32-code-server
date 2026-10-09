#pragma once

#include "../../display/lcd_display.h"

// bigscreen-s3（ESP32-S3 + ILI9341 320x240 横屏 + ES8311，无触屏无电池）专用皮肤。
//
// 布局（320x240 横屏，适配 big_screen.mp4 动画背景：黑白手绘少女+双猫+爱心）：
//   底层  GIF 动画背景（bigscreen_bg.c，171 帧循环，全屏 320x240）
//   顶层  左上 时间文本 + 右上 表情徽章（圆形底 noto emoji 大字号）
//         中下 气泡（280x64 圆角 16，AI/系统消息，260 宽自动换行 2-3 行）
//         底部居中 操作提示「短按说话 双击彩蛋 长按静音」
//
// 设计原则（同 my-s3-tft 圆屏皮肤，2026-10-08 事故教训）：
// - 只覆写渲染层（SetupUI/SetEmotion/SetChatMessage/SetStatus/UpdateStatusBar）
//   Application/协议/MCP/音频链路零改动
// - 基类协议对象（status_label_/container_/network_label_ 等）全部创建成
//   隐藏占位，防 SetTheme/ShowNotification/Assets::Apply 的 null 解引用崩溃
// - SetEmotion 完全复用基类资产渲染管线（emoji_collection 图片 / noto emoji 字符）
//   但渲染目标改为右上角徽章，不遮挡背景动画主体
//
// 表情徽章位置说明：动画主体（少女面部）在画面中央，徽章放右上角 + 半透明
// 深色底，视觉上是"状态角标"，不与背景争抢视觉焦点。
class BigscreenDisplay : public SpiLcdDisplay {
public:
    BigscreenDisplay(esp_lcd_panel_io_handle_t panel_io, esp_lcd_panel_handle_t panel,
                     int width, int height, int offset_x, int offset_y,
                     bool mirror_x, bool mirror_y, bool swap_xy);

    void SetupUI() override;
    void SetEmotion(const char* emotion) override;
    void SetChatMessage(const char* role, const char* content) override;
    void SetStatus(const char* status) override;
    void UpdateStatusBar(bool update_all = false) override;
    void ClearChatMessages() override;
    void ShowNotification(const char* notification, int duration_ms = 3000) override;
    void SetTheme(Theme* theme) override;
    void SetPowerSaveMode(bool on) override;

    // ---- 单 BOOT 键三事件 UI 侧反馈（0=短按 1=双击 2=长按）----
    // Application 状态机优先（板级回调处理实际动作），这里只做皮肤反馈
    void HandleKeyEvent(int ev);

    // 表情彩蛋轮播（待机时双击触发）
    void NextEasterEgg();

    // 1 秒节拍（板级 esp_timer 调用）：彩蛋超时恢复 + 自动行为
    void Tick1s();

    // SD 卡挂载成功回调（板级后台任务调用）：若 /sdcard/bg.gif 存在且
    // 合法（<=4MB），停掉 Flash 背景，改为播放 SD 大背景。
    // 任何失败都静默保持现状（Flash 背景继续播）。
    void OnSdCardMounted();

private:
    void BuildMainScreen();
    void SetBubbleText(const char* text);
    void RestartBackgroundGif();

    lv_obj_t* time_label_ = nullptr;        // 左上时间
    lv_obj_t* status_chip_ = nullptr;       // 左上状态胶囊（联网/配网等非时间状态）
    lv_obj_t* status_chip_label_ = nullptr;
    lv_obj_t* emotion_badge_ = nullptr;     // 右上表情徽章容器
    lv_obj_t* bubble_ = nullptr;            // 中下气泡容器
    lv_obj_t* bubble_label_ = nullptr;      // 气泡文字
    lv_obj_t* hint_label_ = nullptr;        // 底部操作提示
    lv_obj_t* bg_gif_obj_ = nullptr;        // GIF 背景图层（lv_image）
    std::unique_ptr<LvglGif> bg_gif_;       // GIF 播放控制器
    uint8_t* sd_gif_data_ = nullptr;        // SD 背景文件缓冲（PSRAM，OnSdCardMounted 分配）

    // 皮肤配色（深色系，叠加在黑白动画上保证文字可读）
    static constexpr uint32_t kColorBubbleBg = 0x1A1020;    // 气泡底（近黑）
    static constexpr uint32_t kColorPrimary = 0xFF7AA2;     // 主粉（边框/强调）
    static constexpr uint32_t kColorTextMain = 0xFFF7FB;    // 主文字
    static constexpr uint32_t kColorTextSub = 0xC9B8D9;     // 次文字
    static constexpr uint32_t kColorTextHint = 0x8B7A99;    // 底部提示
    static constexpr uint32_t kColorBadgeBg = 0x2A1633;     // 徽章底（半透明深紫）

    int egg_index_ = 0;
    int easter_egg_until_tick_ = -1;
    int tick_count_ = 0;
};

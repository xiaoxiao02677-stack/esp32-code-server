#pragma once

// 屿禾「小柚」LVGL 皮肤 —— 共享显示层
//
// 来源：hardware/small_secreen/yuhe-esp32/main/boards/my-s3-tft/round_screen_display.*
//      （用户指定的 1:1 视觉基准：时间/电量/表情/气泡/提示 + good.jpg 背景 + 彩蛋 + 1s 节拍）
//
// 与基准的三处差异（其余逐像素对齐）：
//   1) 几何参数化 —— 同一套代码适配 240x240 圆屏 / 320x240 横屏 / 240x320 竖屏；
//   2) 开机即接管 —— SetupUI 第一件事就是品牌开机画面，原生 yuhe UI 从不出现；
//   3) 系统态卡片 —— 配网/激活码/升级/错误走 yh_skin_cards 的全屏卡片，
//      不再塞进 200x50 的小气泡里。
//
// 设计原则（沿用基准）：只覆写渲染层，Application/协议/MCP/音频链路零改动。
// 基类隐藏占位对象族（container_/content_/network_label_/...）必须全部创建，
// 否则 LcdDisplay::SetTheme / ShowNotification 会 null 解引用（2026-10-08 事故）。

#include "display/lcd_display.h"
#include "lvgl_theme.h"
#include "yh_skin_types.h"

#include <esp_lcd_panel_io.h>
#include <esp_lcd_panel_ops.h>
#include <lvgl.h>

#include <cstdint>
#include <memory>

// ── 图像资源 ────────────────────────────────────────────────────────────────
// yh_skin_bg（240x240 RGB565）在 yh_skin_types.h 声明、yh_skin_assets.c 定义，
// 由 tools/gen_yh_skin_assets.py 从 good.jpg 生成；四个版型共用同一份，勿在
// 板目录再放副本（每份 578KB 源码 / 225KB flash）。

class YhSkinDisplay : public SpiLcdDisplay {
public:
    YhSkinDisplay(esp_lcd_panel_io_handle_t panel_io, esp_lcd_panel_handle_t panel, int width,
                  int height, int offset_x, int offset_y, bool mirror_x, bool mirror_y,
                  bool swap_xy, const YhSkinProfile& profile);

    // ---- Display 渲染层覆写（协议语义不变）----
    void SetupUI() override;

    // ★ 必须覆写：`LvglDisplay::SetTextFont` 会把主题里的 text_font 换成新的
    //   shared_ptr，于是旧的 LvglBuiltInFont 对象被析构 —— 但它的 lv_font_t
    //   是**对象内部的成员拷贝**（lvgl_font.h: `font_(*font)`），而 LVGL 的
    //   样式持有的是裸 `const lv_font_t*`。任何没被 SetTheme/ApplyFonts 重绑
    //   过的控件，指针当场变成悬垂。
    //   实测后果：assets 加载完 common 字体、切主题那一刻（日志
    //   "Assets: Refreshing display theme..." 之后）立刻 panic：
    //   InstrFetchProhibited / EXCVADDR=0x0，栈为
    //   lv_display_refr_timer → lv_obj_update_layout → lv_font_get_glyph_width
    //   → lv_font_get_glyph_dsc —— 读到的 get_glyph_dsc 是 0。
    //   这里的做法：把旧字体对象留进"退休池"永不释放（一个 lv_font_t 才几十字节），
    //   从根上消除这一类悬垂，而不是去追每一处裸指针。
    bool SetTextFont(std::shared_ptr<LvglFont> text_font) override;
    void SetStatus(const char* status) override;
    void SetEmotion(const char* emotion) override;
    void SetChatMessage(const char* role, const char* content) override;
    void ClearChatMessages() override;
    void ShowNotification(const char* notification, int duration_ms = 3000) override;
    void ShowNotification(const std::string& notification, int duration_ms = 3000) override;
    void SetTheme(Theme* theme) override;
    void UpdateStatusBar(bool update_all = false) override;
    void SetHideSubtitle(bool hide) override;

    // ---- 用户壁纸（FR-2.19/2.20/2.21）：裸指针，生命周期归 WallpaperManager ----
    // 返回值 = 这张图是否真的绑到了 bg_image_ 上。false 表示没接（拿不到锁 /
    // bg_image_ 还没建），调用方必须回滚并"不记账"，否则一次假成功会让之后
    // 同版本下发全被 already applied 挡死。
    bool SetWallpaper(const lv_img_dsc_t* image) override;
    // 返回 false = 没能解除引用，调用方不得释放旧 buffer
    bool ClearWallpaper() override;
    // 开机画面取图用：当前用户壁纸（无则 nullptr → splash 回落品牌底纹）
    const lv_img_dsc_t* GetWallpaper() const override { return user_wallpaper_; }

    // ---- 开机壁纸（boot 槽）：只影响 splash 底图，不动主界面背景 ----
    // 回落链：boot 壁纸 > 待机壁纸 > 品牌底纹。未下发过 boot 壁纸的设备
    // 开机行为与旧版完全一致（idle 壁纸打底），平滑兼容。
    bool SetBootWallpaper(const lv_img_dsc_t* image) override;
    bool ClearBootWallpaper() override;
    const lv_img_dsc_t* GetBootWallpaper() const override { return boot_wallpaper_; }

    // ---- 开机画面：SetupUI 内部第一件事就是它，首帧即品牌画面 ----
    // 可见性唯一真源是 yh_skin::SplashVisible()（看 g_root 是否存在）。
    // 早期版本另存过一份 splash_visible_ 成员，淡出 300ms 内两者会不一致，
    // 让「正在连接」这类状态文案漏进气泡 —— 该成员与其转发函数均已删除。
    // virtual：PetSkinDisplay（像素宠物主题）覆写为 3.8s 宠物出生动画。
    virtual void ShowBootSplash();
    virtual void DismissBootSplash();

    // ---- 单 BOOT 键三事件皮肤反馈（0=短按 1=双击 2=长按）----
    virtual void HandleKeyEvent(int ev);

    // ---- 表情彩蛋轮播（待机双击）----
    virtual void NextEasterEgg();

    // ---- 1 秒节拍（板级 esp_timer 调用）----
    virtual void Tick1s();

    const YhSkinProfile& profile() const { return profile_; }

protected:
    // ---- 子类皮肤定制点（PetSkinDisplay 等主题复用基类骨架）----
    // 基类 SetupUI 已建好：占位对象族（SetTheme/ShowNotification 防崩）、
    // 壁纸链（SetWallpaper/ApplyBackground）、气泡/时间/电量/提示、开机 splash。
    // 子类只替换视觉层，以下成员与工具开放给子类直接操作。
    lv_obj_t* bg_image_ = nullptr;      // 背景图对象（缩放铺满，不用 bg_image_src）
    lv_obj_t* avatar_box_ = nullptr;    // 表情容器
    lv_obj_t* bubble_ = nullptr;        // 气泡容器
    lv_obj_t* bubble_label_ = nullptr;  // 气泡文字
    lv_obj_t* time_label_ = nullptr;    // 顶部时间
    lv_obj_t* battery_text_ = nullptr;  // 顶部电量（has_battery=false 时隐藏）
    lv_obj_t* hint_label_ = nullptr;    // 底部操作提示

    YhSkinFonts CurrentFonts() const;                // 主题四字体（assets 加载后会变）
    void SetBubbleText(const char* text);            // 自带锁的气泡原语

private:
    void BuildMainScreen();
    void AttachHiddenPlaceholders();
    bool ApplyBackground();                        // 已持锁调用：壁纸 > 主题背景 > good.jpg
                                                   // 返回 false = 没作用到显示层（UI 未建/拿不到锁）
    // 已持锁调用：把指定图绑到主界面 bg_image_（set_src 回读确认 + 等比缩放 +
    // 显式标脏）。ApplyBackground 回落链与 SetBootWallpaper 兜底共用。
    bool BindBackgroundImage(const lv_img_dsc_t* image);
    // 已持锁调用：splash 底图（boot 壁纸 > idle 壁纸 > 品牌底纹）。
    // splash 不存在时 lv_image_set_src 不会执行，如实返回 false。
    bool ApplySplashBackground();
    void ApplyFonts();                             // 已持锁调用：把 skin 自建对象重绑到当前主题字体
    void DismissSplashIfNeeded();                  // 待机/连接成功时收起开机画面

    YhSkinProfile profile_;

    const lv_img_dsc_t* user_wallpaper_ = nullptr;   // idle 槽：主界面背景
    const lv_img_dsc_t* boot_wallpaper_ = nullptr;   // boot 槽：splash 底图
    bool subtitle_hidden_ = false;

    int egg_index_ = 0;
    int easter_egg_until_tick_ = -1;
    int tick_count_ = 0;
    int last_bat_percent_ = -1;

    // 皮肤配色（与基准一致）
    static constexpr uint32_t kColorBgTop = 0x2A1633;
    static constexpr uint32_t kColorBgBottom = 0x120B18;
    static constexpr uint32_t kColorPrimary = 0xFF7AA2;
    static constexpr uint32_t kColorBubbleBg = 0x3A2440;
    static constexpr uint32_t kColorTextMain = 0xFFF7FB;
    static constexpr uint32_t kColorTextSub = 0xC9B8D9;
    static constexpr uint32_t kColorTextHint = 0x8B7A99;
};

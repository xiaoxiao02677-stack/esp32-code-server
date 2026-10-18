#ifndef DISPLAY_H
#define DISPLAY_H

#include "emoji_collection.h"
#include "text_glyph.h"

#ifndef CONFIG_USE_EMOTE_MESSAGE_STYLE
#define HAVE_LVGL 1
#include <lvgl.h>
#endif

#include <esp_log.h>
#include <esp_pm.h>
#include <esp_timer.h>

#include <chrono>
#include <cstddef>
#include <cstdint>
#include <memory>
#include <string>
#include <vector>

class LvglFont;
class LvglImage;

class Theme {
public:
    Theme(const std::string& name) : name_(name) {}
    virtual ~Theme() = default;

    inline std::string name() const { return name_; }
    virtual std::shared_ptr<LvglFont> GetTextFont() const { return nullptr; }

private:
    std::string name_;
};

class Display {
public:
    Display();
    virtual ~Display();

    virtual void SetStatus(const char* status);
    virtual void ShowNotification(const char* notification, int duration_ms = 3000);
    virtual void ShowNotification(const std::string& notification, int duration_ms = 3000);
    virtual void SetEmotion(const char* emotion);
    virtual void SetChatMessage(const char* role, const char* content);
    virtual void ClearChatMessages();
    virtual void SetTheme(Theme* theme);
    virtual Theme* GetTheme() { return current_theme_; }
    virtual void UpdateStatusBar(bool update_all = false);
    virtual void SetPowerSaveMode(bool on);
    virtual bool AddTextGlyphs(const std::vector<TextGlyph>& glyphs, uint8_t bpp) { return false; }
    virtual void ClearTextGlyphs() {}
    virtual void SetEmojiCollection(std::shared_ptr<EmojiCollection>) {}
    virtual void SetupUI() { setup_ui_called_ = true; }
    virtual bool IsMonochrome() const { return false; }
    virtual bool SupportsGuiOperations() const { return false; }
    virtual void SetHideSubtitle(bool hide) { (void)hide; }
    virtual bool InsertAnimDialog(const char* name, uint32_t duration_ms) {
        (void)name;
        (void)duration_ms;
        return false;
    }
    virtual bool MountAssets(const char* partition_label) {
        (void)partition_label;
        return false;
    }
    virtual void UnmountAssets() {}
    virtual bool GetAssetData(const std::string& name, const uint8_t*& data, size_t& size) {
        (void)name;
        (void)data;
        (void)size;
        return false;
    }
    virtual void LoadAssets() {}
    virtual void SetPreviewImage(std::unique_ptr<LvglImage> image);
    virtual bool SetTextFont(std::shared_ptr<LvglFont> text_font) {
        (void)text_font;
        return false;
    }
    virtual bool SnapshotToJpeg(std::string& jpeg_data, int quality = 80) {
        (void)jpeg_data;
        (void)quality;
        return false;
    }

#ifndef CONFIG_USE_EMOTE_MESSAGE_STYLE
    // 用户壁纸（FR-2.19 / FR-2.22）：
    // 图缓冲与 lv_img_dsc_t 由 WallpaperManager 持有，这里只接收裸指针并立即消费；
    // 默认空实现 → 不支持的显示驱动自动忽略（NFR-9 兼容）。
    // emote 风格构建无 lvgl.h、也无壁纸渲染能力，故不声明这两个接口；
    // 调用侧（wallpaper_manager.cc）用 WALLPAPER_HAS_LVGL_DISPLAY 条件闸对齐。
    // 返回值 = 显示层是否真的接管了这张图，调用方（wallpaper_manager）据此决定
    // 「记账为已应用」还是「回滚 + 回 fail:render」。默认实现返回 true：
    // 没有壁纸能力的历史驱动保持"接受但不做事"的原语义，不会让服务端刷失败。
    virtual bool SetWallpaper(const lv_img_dsc_t* image) { (void)image; return true; }
    // 返回 false = 没能解除对旧图的引用（拿不到锁/UI 未就绪）。
    // 调用方必须放弃释放旧 buffer，否则 LVGL 会去渲染一块已释放的 PSRAM。
    virtual bool ClearWallpaper() { return true; }
    // 当前已绑定的用户壁纸（nullptr = 无，用默认背景）。
    // 供开机画面取图：splash 想直接以用户壁纸打底时，从这里拿指针——
    // 缓冲归 WallpaperManager 所有，调用方只读、不 free（FR-2.22 同一所有权约定）。
    virtual const lv_img_dsc_t* GetWallpaper() const { return nullptr; }

    // ---- 开机壁纸（boot 槽）：只影响 splash 画面底图，不动主界面背景 ----
    // 所有权约定与上面完全相同（缓冲归 WallpaperManager，这里只持只读指针）。
    // 默认实现返回 true / 空转：不支持的历史驱动保持原语义。
    virtual bool SetBootWallpaper(const lv_img_dsc_t* image) { (void)image; return true; }
    virtual bool ClearBootWallpaper() { return true; }
    virtual const lv_img_dsc_t* GetBootWallpaper() const { return nullptr; }
#endif

    inline int width() const { return width_; }
    inline int height() const { return height_; }
    inline bool IsSetupUICalled() const { return setup_ui_called_; }

protected:
    int width_ = 0;
    int height_ = 0;
    bool setup_ui_called_ = false;  // Track if SetupUI() has been called

    Theme* current_theme_ = nullptr;

    friend class DisplayLockGuard;
    virtual bool Lock(int timeout_ms = 0) = 0;
    virtual void Unlock() = 0;
};

class DisplayLockGuard {
public:
    explicit DisplayLockGuard(Display* display) : display_(display), locked_(Acquire(display)) {
        if (!locked_) {
            // 打出来的是"放弃了"，不是"等了 30 秒"。持有者多半已经病态（见下方注释）。
            ESP_LOGE("Display",
                     "Failed to lock display after %d ms; caller must skip LVGL work (owner task stuck?)",
                     kTotalWaitMs);
        }
    }
    ~DisplayLockGuard() {
        if (locked_) {
            display_->Unlock();
        }
    }

    DisplayLockGuard(const DisplayLockGuard&) = delete;
    DisplayLockGuard& operator=(const DisplayLockGuard&) = delete;

    // 供调用方 fail-closed：拿不到锁就**别碰 LVGL**。
    // 原来的写法是等满 30 秒后打印一行然后无锁继续，这是本案的放大器：
    // LVGL 在本工程是 LV_OS_NONE（sdkconfig 无 CONFIG_LV_USE_OS），内部零加锁，
    // event_head 是单个全局链表、节点是各任务栈上的局部变量。两个任务同时
    // push/pop 会把 head 还原成"另一个任务早已返回的栈槽"，该槽被复用后
    // lv_event_push 会写出 e->prev = &e 的自环 → lv_event_mark_deleted 的
    // while(e) 永不终止（实测卡死 30s+，WDT 每 10s 打同一栈）；若该槽内容
    // 是小整数则表现为 LoadProhibited / EXCVADDR=0x14。
    // 所以"等不到锁还继续写"比"这次不更新界面"危险得多。
    bool locked() const { return locked_; }
    explicit operator bool() const { return locked_; }

private:
    // 分片重试而不是一次性长等：
    //   · 正常竞争（毫秒级）仍然能拿到，行为不变；
    //   · 真病态持锁时尽早返回 false，让调用方跳过，而不是把调用者
    //     连同主任务一起钉死 30 秒（那期间按键、协议、看门狗全被拖住）。
    static bool Acquire(Display* display) {
        for (int waited = 0; waited < kTotalWaitMs; waited += kSliceMs) {
            if (display->Lock(kSliceMs)) {
                return true;
            }
        }
        return false;
    }

    static constexpr int kSliceMs = 500;
    static constexpr int kTotalWaitMs = 2000;

    Display* display_;
    bool locked_;
};

class NoDisplay : public Display {
private:
    virtual bool Lock(int timeout_ms = 0) override { return true; }
    virtual void Unlock() override {}
};

#endif

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
    virtual void SetWallpaper(const lv_img_dsc_t* image) { (void)image; }
    virtual void ClearWallpaper() {}
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
    explicit DisplayLockGuard(Display* display)
        : display_(display), locked_(display_->Lock(30000)) {
        if (!locked_) {
            ESP_LOGE("Display", "Failed to lock display");
        }
    }
    ~DisplayLockGuard() {
        if (locked_) {
            display_->Unlock();
        }
    }

    DisplayLockGuard(const DisplayLockGuard&) = delete;
    DisplayLockGuard& operator=(const DisplayLockGuard&) = delete;

    explicit operator bool() const { return locked_; }

private:
    Display* display_;
    bool locked_;
};

class NoDisplay : public Display {
private:
    virtual bool Lock(int timeout_ms = 0) override { return true; }
    virtual void Unlock() override {}
};

#endif

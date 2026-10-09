#include "bigscreen_display.h"

#include "../../display/display.h"
#include "application.h"
#include "assets/lang_config.h"
#include "boards/common/board.h"
#include "lvgl_theme.h"

#include <esp_log.h>
#include <noto_emoji.h>

#include <cstring>

// 动画背景 GIF（由 tools/mp4_to_gif_bg.py 从 big_screen.mp4 生成，320x240 循环）
extern const uint8_t bigscreen_bg_gif[];
extern const size_t bigscreen_bg_gif_len;

#define TAG "Bigscreen"

// LVGL v9（本固件）API：lv_obj_remove_flag / lv_obj_set_scrollbar_mode
// 取代 v8 的 lv_obj_clear_flag；lv_screen_active() 获取活动屏幕。
BigscreenDisplay::BigscreenDisplay(esp_lcd_panel_io_handle_t panel_io,
                                   esp_lcd_panel_handle_t panel, int width, int height,
                                   int offset_x, int offset_y, bool mirror_x, bool mirror_y,
                                   bool swap_xy)
    : SpiLcdDisplay(panel_io, panel, width, height, offset_x, offset_y, mirror_x, mirror_y,
                    swap_xy) {}

void BigscreenDisplay::SetupUI() {
    if (setup_ui_called_) {
        return;
    }
    Display::SetupUI();
    DisplayLockGuard lock(this);

    auto lvgl_theme = static_cast<LvglTheme*>(current_theme_);
    auto text_font = lvgl_theme->text_font()->font();

    auto screen = lv_screen_active();
    lv_obj_set_style_text_font(screen, text_font, 0);
    lv_obj_set_style_bg_color(screen, lv_color_black(), 0);
    lv_obj_set_style_bg_opa(screen, LV_OPA_COVER, 0);

    BuildMainScreen();
}

void BigscreenDisplay::BuildMainScreen() {
    auto screen = lv_screen_active();
    auto lvgl_theme = static_cast<LvglTheme*>(current_theme_);
    auto text_font = lvgl_theme->text_font()->font();
    auto icon_font = lvgl_theme->icon_font()->font();
    auto emoji_font = lvgl_theme->emoji_font()->font();

    // ---- 底层：GIF 动画背景（big_screen.mp4 的循环动画，全屏 320x240）----
    // 用手动 lv_image 承载：LvglGif 的 frame_callback 更新画布后触发重绘。
    // 不用 style bg_image_src —— 那会由 LVGL 解码静态图，无法逐帧刷新。
    bg_gif_obj_ = lv_image_create(screen);
    lv_obj_align(bg_gif_obj_, LV_ALIGN_CENTER, 0, 0);
    lv_obj_set_size(bg_gif_obj_, 320, 240);

    // 构造 GIF 解码控制器：数据在 Flash（.rodata），gifdec 复制进 LVGL 池（PSRAM）
    lv_img_dsc_t dsc = {};
    dsc.header.magic = LV_IMAGE_HEADER_MAGIC;
    dsc.header.flags = LV_IMAGE_FLAGS_MODIFIABLE;
    dsc.header.cf = LV_COLOR_FORMAT_RAW;
    dsc.data = (const uint8_t*)bigscreen_bg_gif;
    dsc.data_size = bigscreen_bg_gif_len;
    bg_gif_ = std::make_unique<LvglGif>(&dsc);

    if (bg_gif_->IsLoaded()) {
        bg_gif_->SetFrameCallback([this]() {
            if (bg_gif_obj_ != nullptr) {
                lv_image_set_src(bg_gif_obj_, bg_gif_->image_dsc());
            }
        });
        lv_image_set_src(bg_gif_obj_, bg_gif_->image_dsc());
        bg_gif_->Start();
        ESP_LOGI(TAG, "BG GIF started (%dx%d, %u bytes)", bg_gif_->width(), bg_gif_->height(),
                 (unsigned)bigscreen_bg_gif_len);
    } else {
        ESP_LOGE(TAG, "BG GIF failed to load; solid fallback");
        bg_gif_.reset();
        lv_obj_set_style_bg_color(screen, lv_color_hex(0x121212), 0);
    }

    // ---- 左上：时间 ----
    time_label_ = lv_label_create(screen);
    lv_label_set_text(time_label_, "--:--");
    lv_obj_set_style_text_font(time_label_, text_font, 0);
    lv_obj_set_style_text_color(time_label_, lv_color_hex(kColorTextMain), 0);
    lv_obj_set_style_text_opa(time_label_, LV_OPA_COVER, 0);
    // 半透明深色衬底，保证叠加在动画上可读
    lv_obj_set_style_bg_color(time_label_, lv_color_hex(kColorBubbleBg), 0);
    lv_obj_set_style_bg_opa(time_label_, LV_OPA_70, 0);
    lv_obj_set_style_radius(time_label_, 8, 0);
    lv_obj_set_style_pad_hor(time_label_, 8, 0);
    lv_obj_set_style_pad_ver(time_label_, 2, 0);
    lv_obj_align(time_label_, LV_ALIGN_TOP_LEFT, 8, 6);

    // ---- 左上：状态胶囊（配网/连接等非时间状态）----
    status_chip_ = lv_obj_create(screen);
    lv_obj_set_size(status_chip_, LV_SIZE_CONTENT, LV_SIZE_CONTENT);
    lv_obj_set_style_bg_color(status_chip_, lv_color_hex(kColorBadgeBg), 0);
    lv_obj_set_style_bg_opa(status_chip_, LV_OPA_70, 0);
    lv_obj_set_style_border_width(status_chip_, 0, 0);
    lv_obj_set_style_radius(status_chip_, 8, 0);
    lv_obj_set_style_pad_all(status_chip_, 4, 0);
    lv_obj_set_style_pad_hor(status_chip_, 8, 0);
    lv_obj_set_scrollbar_mode(status_chip_, LV_SCROLLBAR_MODE_OFF);
    lv_obj_align(status_chip_, LV_ALIGN_TOP_LEFT, 8, 30);
    lv_obj_add_flag(status_chip_, LV_OBJ_FLAG_HIDDEN);

    status_chip_label_ = lv_label_create(status_chip_);
    lv_label_set_text(status_chip_label_, "");
    lv_obj_set_style_text_font(status_chip_label_, text_font, 0);
    lv_obj_set_style_text_color(status_chip_label_, lv_color_hex(kColorTextSub), 0);
    lv_obj_center(status_chip_label_);

    // ---- 右上：表情徽章（60x60 圆形容器，noto emoji）----
    // 动画主体在画面中央，徽章放右上角避免遮挡面部
    emotion_badge_ = lv_obj_create(screen);
    lv_obj_set_size(emotion_badge_, 60, 60);
    lv_obj_align(emotion_badge_, LV_ALIGN_TOP_RIGHT, -8, 6);
    lv_obj_set_style_bg_color(emotion_badge_, lv_color_hex(kColorBadgeBg), 0);
    lv_obj_set_style_bg_opa(emotion_badge_, LV_OPA_70, 0);
    lv_obj_set_style_border_width(emotion_badge_, 1, 0);
    lv_obj_set_style_border_color(emotion_badge_, lv_color_hex(kColorPrimary), 0);
    lv_obj_set_style_radius(emotion_badge_, 30, 0);
    lv_obj_set_style_pad_all(emotion_badge_, 0, 0);
    lv_obj_set_scrollbar_mode(emotion_badge_, LV_SCROLLBAR_MODE_OFF);

    emoji_label_ = lv_label_create(emotion_badge_);
    lv_obj_set_style_text_font(emoji_label_, emoji_font, 0);
    lv_obj_set_style_text_color(emoji_label_, lv_color_hex(kColorTextMain), 0);
    lv_label_set_text(emoji_label_, noto_emoji_get_utf8("neutral"));
    lv_obj_center(emoji_label_);

    // emoji_image_（资产图片/GIF 表情）初始隐藏；SetEmotion 命中资产时基类切换显示
    emoji_image_ = lv_img_create(emotion_badge_);
    lv_obj_center(emoji_image_);
    lv_obj_add_flag(emoji_image_, LV_OBJ_FLAG_HIDDEN);

    // preview_image_（基类成员：截图/预览链路使用）——隐藏占位，避免空指针
    preview_image_ = lv_image_create(screen);
    lv_obj_set_size(preview_image_, width_ / 2, height_ / 2);
    lv_obj_align(preview_image_, LV_ALIGN_CENTER, 0, 0);
    lv_obj_add_flag(preview_image_, LV_OBJ_FLAG_HIDDEN);

    // ---- 中下：气泡 280x64 圆角 16 粉色边框 ----
    bubble_ = lv_obj_create(screen);
    lv_obj_set_size(bubble_, 280, 64);
    lv_obj_align(bubble_, LV_ALIGN_BOTTOM_MID, 0, -36);
    lv_obj_set_style_bg_color(bubble_, lv_color_hex(kColorBubbleBg), 0);
    lv_obj_set_style_bg_opa(bubble_, LV_OPA_80, 0);
    lv_obj_set_style_radius(bubble_, 16, 0);
    lv_obj_set_style_border_width(bubble_, 1, 0);
    lv_obj_set_style_border_color(bubble_, lv_color_hex(kColorPrimary), 0);
    lv_obj_set_style_pad_all(bubble_, 6, 0);
    lv_obj_set_scrollbar_mode(bubble_, LV_SCROLLBAR_MODE_OFF);

    bubble_label_ = lv_label_create(bubble_);
    lv_label_set_text(bubble_label_, "我在呢");
    lv_obj_set_width(bubble_label_, 260);
    lv_label_set_long_mode(bubble_label_, LV_LABEL_LONG_WRAP);
    lv_obj_set_style_text_align(bubble_label_, LV_TEXT_ALIGN_CENTER, 0);
    lv_obj_set_style_text_font(bubble_label_, text_font, 0);
    lv_obj_set_style_text_color(bubble_label_, lv_color_hex(kColorTextMain), 0);
    lv_obj_center(bubble_label_);

    // ---- 底部：操作提示 ----
    hint_label_ = lv_label_create(screen);
    lv_label_set_text(hint_label_, "短按说话  双击彩蛋  长按静音");
    lv_obj_set_style_text_font(hint_label_, text_font, 0);
    lv_obj_set_style_text_color(hint_label_, lv_color_hex(kColorTextHint), 0);
    lv_obj_set_style_bg_color(hint_label_, lv_color_hex(kColorBubbleBg), 0);
    lv_obj_set_style_bg_opa(hint_label_, LV_OPA_60, 0);
    lv_obj_set_style_radius(hint_label_, 6, 0);
    lv_obj_set_style_pad_hor(hint_label_, 6, 0);
    lv_obj_align(hint_label_, LV_ALIGN_BOTTOM_MID, 0, -8);

    // ---- 基类协议对象补齐（防 SetTheme/ShowNotification 崩溃，见头文件说明）----
    container_ = lv_obj_create(screen);
    lv_obj_set_size(container_, 1, 1);
    lv_obj_add_flag(container_, LV_OBJ_FLAG_HIDDEN);
    lv_obj_set_style_bg_opa(container_, LV_OPA_TRANSP, 0);
    lv_obj_set_style_border_width(container_, 0, 0);

    network_label_ = lv_label_create(container_);
    lv_obj_set_style_text_font(network_label_, icon_font, 0);
    lv_label_set_text(network_label_, "");
    lv_obj_add_flag(network_label_, LV_OBJ_FLAG_HIDDEN);

    mute_label_ = lv_label_create(container_);
    lv_obj_set_style_text_font(mute_label_, icon_font, 0);
    lv_label_set_text(mute_label_, "");
    lv_obj_add_flag(mute_label_, LV_OBJ_FLAG_HIDDEN);

    battery_label_ = lv_label_create(container_);
    lv_obj_set_style_text_font(battery_label_, icon_font, 0);
    lv_label_set_text(battery_label_, "");
    lv_obj_add_flag(battery_label_, LV_OBJ_FLAG_HIDDEN);

    status_label_ = lv_label_create(container_);
    lv_obj_set_style_text_font(status_label_, text_font, 0);
    lv_label_set_text(status_label_, "");
    lv_obj_add_flag(status_label_, LV_OBJ_FLAG_HIDDEN);

    notification_label_ = lv_label_create(container_);
    lv_obj_set_style_text_font(notification_label_, text_font, 0);
    lv_label_set_text(notification_label_, "");
    lv_obj_add_flag(notification_label_, LV_OBJ_FLAG_HIDDEN);

    low_battery_popup_ = lv_obj_create(container_);
    lv_obj_set_size(low_battery_popup_, 1, 1);
    lv_obj_add_flag(low_battery_popup_, LV_OBJ_FLAG_HIDDEN);
    lv_obj_set_style_bg_opa(low_battery_popup_, LV_OPA_TRANSP, 0);
    lv_obj_set_style_border_width(low_battery_popup_, 0, 0);
    low_battery_label_ = lv_label_create(low_battery_popup_);
    lv_label_set_text(low_battery_label_, "");
    lv_obj_set_style_text_font(low_battery_label_, text_font, 0);

    content_ = lv_obj_create(container_);
    lv_obj_set_size(content_, 1, 1);
    lv_obj_add_flag(content_, LV_OBJ_FLAG_HIDDEN);
    lv_obj_set_style_bg_opa(content_, LV_OPA_TRANSP, 0);
    lv_obj_set_style_border_width(content_, 0, 0);

    chat_message_label_ = lv_label_create(content_);
    lv_obj_set_style_text_font(chat_message_label_, text_font, 0);
    lv_label_set_text(chat_message_label_, "");
    lv_obj_add_flag(chat_message_label_, LV_OBJ_FLAG_HIDDEN);
}

void BigscreenDisplay::RestartBackgroundGif() {
    // 从 SetPowerSaveMode 返回时恢复背景动画（Stop 后画布保留最后一帧，
    // 重新 Start 从头循环）
    if (bg_gif_ && bg_gif_obj_ != nullptr) {
        lv_image_set_src(bg_gif_obj_, bg_gif_->image_dsc());
        bg_gif_->Start();
    }
}

void BigscreenDisplay::SetBubbleText(const char* text) {
    DisplayLockGuard lock(this);
    if (bubble_label_ != nullptr && text != nullptr) {
        lv_label_set_text(bubble_label_, text);
    }
}

// ---------------- 协议层钩子（原 API 语义不变，仅换皮肤渲染） ----------------

void BigscreenDisplay::SetEmotion(const char* emotion) {
    // 彩蛋展示期间不覆盖（10 秒后自动恢复）
    if (easter_egg_until_tick_ > tick_count_) {
        return;
    }
    // 复用基类资产/emoji 渲染管线（协议名 -> emoji_collection 图片 / noto emoji）
    // 渲染目标是右上角 emotion_badge_（基类 SetEmotion 只操作 emoji_image_/emoji_label_）
    LcdDisplay::SetEmotion(emotion);
}

void BigscreenDisplay::SetChatMessage(const char* role, const char* content) {
    if (!setup_ui_called_) {
        ESP_LOGW(TAG, "SetChatMessage('%s','%s') before SetupUI", role, content);
        return;
    }
    // 气泡只显示最新一条（role 语义保留：system 空串=清空恢复默认）
    if (content == nullptr || content[0] == '\0') {
        SetBubbleText("我在呢");
        return;
    }
    // 截断到 96 字符（260 宽 2-3 行容量）
    if (strlen(content) > 96) {
        char buf[100];
        memcpy(buf, content, 96);
        buf[96] = '\0';
        SetBubbleText(buf);
    } else {
        SetBubbleText(content);
    }
}

void BigscreenDisplay::ClearChatMessages() {
    // 单气泡布局：清屏 = 气泡恢复默认文案
    // 不调基类实现——它会 lv_obj_clean(content_) 使 bubble_label_ 悬空
    DisplayLockGuard lock(this);
    if (bubble_label_ != nullptr) {
        lv_label_set_text(bubble_label_, "我在呢");
    }
}

void BigscreenDisplay::ShowNotification(const char* notification, int duration_ms) {
    // 通知落到气泡（基类实现只写隐藏占位 label）
    if (!setup_ui_called_) {
        ESP_LOGW(TAG, "ShowNotification('%s') called before SetupUI() - message will be lost!",
                 notification);
    }
    DisplayLockGuard lock(this);
    if (bubble_label_ != nullptr) {
        lv_label_set_text(bubble_label_, notification);
    }
}

void BigscreenDisplay::SetTheme(Theme* theme) {
    // 基类实现：重绑基类标签（container_/network_label_/...）到新主题字体。
    // 本皮肤标签不会被基类触碰，必须在这里一并重绑，
    // 否则布局测量走到悬空字体指针（2026-10-08 圆屏同款事故）。
    LcdDisplay::SetTheme(theme);

    auto lvgl_theme = static_cast<LvglTheme*>(theme);
    auto text_font = lvgl_theme->text_font()->font();
    auto icon_font = lvgl_theme->icon_font()->font();
    auto emoji_font = lvgl_theme->emoji_font()->font();

    lv_obj_set_style_text_font(time_label_, text_font, 0);
    lv_obj_set_style_text_font(status_chip_label_, text_font, 0);
    lv_obj_set_style_text_font(hint_label_, text_font, 0);
    lv_obj_set_style_text_font(bubble_label_, text_font, 0);
    lv_obj_set_style_text_font(emoji_label_, emoji_font, 0);
    lv_obj_set_style_text_font(chat_message_label_, text_font, 0);
    lv_obj_set_style_text_font(low_battery_label_, text_font, 0);
    // network/mute/battery/status/notification 占位已由基类 SetTheme 重绑
    (void)icon_font;
}

void BigscreenDisplay::SetStatus(const char* status) {
    if (!setup_ui_called_) {
        return;
    }
    DisplayLockGuard lock(this);
    if (status == nullptr) {
        return;
    }
    // 纯时间格式（5 字符 "HH:MM"）写到左上时间位
    if (strlen(status) == 5 && status[2] == ':') {
        if (time_label_ != nullptr) {
            lv_label_set_text(time_label_, status);
        }
        return;
    }
    // 其余状态（连接中/激活/升级等）写入气泡
    if (bubble_label_ != nullptr) {
        lv_label_set_text(bubble_label_, status);
    }
}

void BigscreenDisplay::UpdateStatusBar(bool update_all) {
    // 复用基类节拍逻辑：时间刷新（经我们覆写的 SetStatus 落到左上时间位）
    LvglDisplay::UpdateStatusBar(update_all);
}

void BigscreenDisplay::SetPowerSaveMode(bool on) {
    // 息屏/省电：停掉背景 GIF 动画（SPI 屏主刷新的最大消耗源）
    if (on) {
        if (bg_gif_) {
            bg_gif_->Stop();
        }
    } else {
        RestartBackgroundGif();
        LcdDisplay::SetEmotion("neutral");
    }
    // 基类语义：sleepy/neutral 表情 + 清消息
    LcdDisplay::SetPowerSaveMode(on);
}

// ---------------- 单 BOOT 键三事件（皮肤层反馈） ----------------

void BigscreenDisplay::HandleKeyEvent(int ev) {
    auto& app = Application::GetInstance();
    auto state = app.GetDeviceState();

    switch (ev) {
        case 0:  // 短按
            if (state == kDeviceStateIdle || state == kDeviceStateSpeaking) {
                // Application::ToggleChatState() 已由板级回调处理；
                // 这里给聆听态预置反馈
                LcdDisplay::SetEmotion("laughing");
                SetBubbleText("我在听...");
            }
            break;
        case 1:  // 双击
            if (state == kDeviceStateIdle) {
                NextEasterEgg();
            } else if (state == kDeviceStateSpeaking) {
                LcdDisplay::SetEmotion("winking");
            }
            break;
        case 2:  // 长按
            // 板级已处理实际动作（静音切换/打断）；这里给可见反馈
            if (state == kDeviceStateIdle) {
                auto codec = Board::GetInstance().GetAudioCodec();
                bool muted = (codec->output_volume() == 0);
                LcdDisplay::SetEmotion(muted ? "sad" : "cool");
                SetBubbleText(muted ? "已静音" : "声音开启啦");
            } else if (state == kDeviceStateListening) {
                LcdDisplay::SetEmotion("neutral");
                SetBubbleText("我在呢");
            }
            break;
        default:
            break;
    }
}

void BigscreenDisplay::NextEasterEgg() {
    static const struct {
        const char* emotion;
        const char* text;
    } eggs[] = {
        {"loving", "么么"},
        {"embarrassed", "摸头会变矮的"},
        {"cool", "今天也很酷"},
        {"silly", "嘿嘿"},
        {"surprised", "哇！"},
    };
    constexpr int kEggCount = sizeof(eggs) / sizeof(eggs[0]);
    egg_index_ = (egg_index_ + 1) % kEggCount;
    LcdDisplay::SetEmotion(eggs[egg_index_].emotion);
    SetBubbleText(eggs[egg_index_].text);
    easter_egg_until_tick_ = tick_count_ + 10;  // 10 秒后恢复协议驱动表情
}

void BigscreenDisplay::Tick1s() {
    tick_count_++;

    // 彩蛋超时恢复
    if (easter_egg_until_tick_ > 0 && tick_count_ >= easter_egg_until_tick_) {
        easter_egg_until_tick_ = -1;
        if (Application::GetInstance().GetDeviceState() == kDeviceStateIdle) {
            LcdDisplay::SetEmotion("neutral");
            SetBubbleText("我在呢");
        }
    }

    // 自动行为：只在整分钟触发（tick_count_ 每 1s +1）
    auto& app = Application::GetInstance();
    if (app.GetDeviceState() != kDeviceStateIdle) {
        return;
    }
    if (tick_count_ % 60 != 0) {
        return;
    }

    time_t now = time(NULL);
    struct tm* tm_now = localtime(&now);
    if (tm_now == nullptr || tm_now->tm_year < 2025 - 1900) {
        return;  // 时间未同步
    }

    static int last_behavior_min = -1;
    int cur_min = tm_now->tm_hour * 60 + tm_now->tm_min;
    if (cur_min == last_behavior_min) {
        return;
    }

    if (cur_min == 23 * 60 + 30) {
        last_behavior_min = cur_min;
        LcdDisplay::SetEmotion("sleepy");
        SetBubbleText("该睡啦，别熬夜");
    } else if (cur_min == 7 * 60) {
        last_behavior_min = cur_min;
        LcdDisplay::SetEmotion("happy");
        SetBubbleText("早呀宝宝，今天也要加油");
    }
}

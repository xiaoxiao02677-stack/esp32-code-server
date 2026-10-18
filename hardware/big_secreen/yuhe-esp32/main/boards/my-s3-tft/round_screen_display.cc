#include "round_screen_display.h"

#include "../../display/display.h"
#include "application.h"
#include "assets/lang_config.h"
#include "boards/common/board.h"
#include "lvgl_theme.h"

#include <esp_log.h>
#include <noto_emoji.h>

#include <ctime>
#include <cstring>

// 用户指定背景图（good.jpg，240x240 RGB565，由 tools/jpg_to_lvgl565.py 生成）
extern const lv_image_dsc_t bg_good;

#define TAG "RoundScreen"

// LVGL v9（本固件）与 v8 API 差异兼容：
// lv_obj_clear_flag(o, LV_OBJ_FLAG_SCROLLABLE) -> lv_obj_remove_flag / set_scrollbar_mode
// LV_LABEL_LONG_WRAP 不变；lv_screen_active() 已由基类使用
RoundScreenDisplay::RoundScreenDisplay(esp_lcd_panel_io_handle_t panel_io,
                                       esp_lcd_panel_handle_t panel, int width, int height,
                                       int offset_x, int offset_y, bool mirror_x,
                                       bool mirror_y, bool swap_xy)
    : SpiLcdDisplay(panel_io, panel, width, height, offset_x, offset_y, mirror_x, mirror_y,
                    swap_xy) {}

void RoundScreenDisplay::SetupUI() {
    if (setup_ui_called_) {
        return;
    }
    Display::SetupUI();
    DisplayLockGuard lock(this);

    auto lvgl_theme = static_cast<LvglTheme*>(current_theme_);
    auto text_font = lvgl_theme->text_font()->font();
    auto icon_font = lvgl_theme->icon_font()->font();
    auto large_icon_font = lvgl_theme->large_icon_font()->font();
    auto emoji_font = lvgl_theme->emoji_font()->font();

    auto screen = lv_screen_active();
    lv_obj_set_style_text_font(screen, text_font, 0);

    BuildMainScreen();
    (void)icon_font;
    (void)large_icon_font;
    (void)emoji_font;
    (void)text_font;
}

void RoundScreenDisplay::BuildMainScreen() {
    auto screen = lv_screen_active();
    auto lvgl_theme = static_cast<LvglTheme*>(current_theme_);
    auto text_font = lvgl_theme->text_font()->font();
    auto icon_font = lvgl_theme->icon_font()->font();
    auto emoji_font = lvgl_theme->emoji_font()->font();

    // ---- 背景：good.jpg 全屏图（用户指定），回退色保留以防图片加载异常 ----
    lv_obj_set_style_bg_image_src(screen, &bg_good, 0);
    lv_obj_set_style_bg_color(screen, lv_color_hex(kColorBgTop), 0);
    lv_obj_set_style_bg_grad_color(screen, lv_color_hex(kColorBgBottom), 0);
    lv_obj_set_style_bg_grad_dir(screen, LV_GRAD_DIR_VER, 0);

    // ---- 顶部：时间 y=10 / 电量 y=28（14 号字，居中）----
    round_time_label_ = lv_label_create(screen);
    lv_label_set_text(round_time_label_, "--:--");
    lv_obj_set_style_text_font(round_time_label_, text_font, 0);
    lv_obj_set_style_text_color(round_time_label_, lv_color_hex(kColorTextSub), 0);
    lv_obj_align(round_time_label_, LV_ALIGN_TOP_MID, 0, 10);

    round_bat_label_ = lv_label_create(screen);
    lv_label_set_text(round_bat_label_, "");
    lv_obj_set_style_text_font(round_bat_label_, text_font, 0);
    lv_obj_set_style_text_color(round_bat_label_, lv_color_hex(kColorTextSub), 0);
    lv_obj_align(round_bat_label_, LV_ALIGN_TOP_MID, 0, 28);

    // ---- 中心：表情头像 y=-15 ----
    // 复用基类 emoji_image_/emoji_label_（SetEmotion 资产渲染管线不动），
    // 仅重新定位到圆屏中心偏上。
    // 基类 SetupUI 未运行（我们完全接管布局），因此在此创建这两个对象。
    // 注意：保留成员名与基类一致，使 LcdDisplay::SetEmotion 的 emoji 渲染逻辑直接生效。
    lv_obj_t* avatar_container = lv_obj_create(screen);
    lv_obj_set_size(avatar_container, 120, 120);
    lv_obj_align(avatar_container, LV_ALIGN_CENTER, 0, -15);
    lv_obj_set_style_bg_opa(avatar_container, LV_OPA_TRANSP, 0);
    lv_obj_set_style_border_width(avatar_container, 0, 0);
    lv_obj_set_style_radius(avatar_container, 0, 0);
    lv_obj_set_style_pad_all(avatar_container, 0, 0);
    lv_obj_set_scrollbar_mode(avatar_container, LV_SCROLLBAR_MODE_OFF);

    emoji_label_ = lv_label_create(avatar_container);
    lv_obj_set_style_text_font(emoji_label_, emoji_font, 0);
    lv_obj_set_style_text_color(emoji_label_, lv_color_hex(kColorTextMain), 0);
    lv_label_set_text(emoji_label_, noto_emoji_get_utf8("neutral"));
    lv_obj_center(emoji_label_);

    // emoji_image_（图片/GIF 表情）初始隐藏；SetEmotion 命中资产时基类会自动切换显示
    emoji_image_ = lv_img_create(avatar_container);
    lv_obj_center(emoji_image_);
    lv_obj_add_flag(emoji_image_, LV_OBJ_FLAG_HIDDEN);

    // preview_image_（基类成员：截图/预览链路使用）——中心隐藏占位，避免空指针
    preview_image_ = lv_image_create(screen);
    lv_obj_set_size(preview_image_, width_ / 2, height_ / 2);
    lv_obj_align(preview_image_, LV_ALIGN_CENTER, 0, 0);
    lv_obj_add_flag(preview_image_, LV_OBJ_FLAG_HIDDEN);

    // ---- 气泡：底部居中 y=-55，200x50，圆角16，粉色边框 ----
    bubble_ = lv_obj_create(screen);
    lv_obj_set_size(bubble_, 200, 50);
    lv_obj_align(bubble_, LV_ALIGN_BOTTOM_MID, 0, -55);
    lv_obj_set_style_bg_color(bubble_, lv_color_hex(kColorBubbleBg), 0);
    lv_obj_set_style_bg_opa(bubble_, LV_OPA_80, 0);
    lv_obj_set_style_radius(bubble_, 16, 0);
    lv_obj_set_style_border_width(bubble_, 1, 0);
    lv_obj_set_style_border_color(bubble_, lv_color_hex(kColorPrimary), 0);
    lv_obj_set_style_pad_all(bubble_, 4, 0);
    lv_obj_set_scrollbar_mode(bubble_, LV_SCROLLBAR_MODE_OFF);

    bubble_label_ = lv_label_create(bubble_);
    lv_label_set_text(bubble_label_, "我在呢");
    lv_obj_set_width(bubble_label_, 180);
    lv_label_set_long_mode(bubble_label_, LV_LABEL_LONG_WRAP);
    lv_obj_set_style_text_align(bubble_label_, LV_TEXT_ALIGN_CENTER, 0);
    lv_obj_set_style_text_font(bubble_label_, text_font, 0);
    lv_obj_set_style_text_color(bubble_label_, lv_color_hex(kColorTextMain), 0);
    lv_obj_center(bubble_label_);

    // ---- 底部提示 y=-12 ----
    round_hint_label_ = lv_label_create(screen);
    lv_label_set_text(round_hint_label_, "短按说话  长按菜单");
    lv_obj_set_style_text_font(round_hint_label_, text_font, 0);
    lv_obj_set_style_text_color(round_hint_label_, lv_color_hex(kColorTextHint), 0);
    lv_obj_align(round_hint_label_, LV_ALIGN_BOTTOM_MID, 0, -12);

    // ---- 基类协议对象补齐（关键，防 SetTheme/ShowNotification 崩溃）----
    // LcdDisplay::SetTheme（激活时 Assets::Apply 必经）无条件设置这些标签的
    // 字体/颜色；LvglDisplay::ShowNotification/SetStatus 也会写它们。
    // 圆屏布局不用原状态栏，但必须全部创建成隐藏对象，否则 null 解引用
    // 导致 Guru Meditation 崩溃循环（2026-10-08 事故）。
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

    // status_label_：基类语义是"当前状态"；圆屏把它映射到气泡文字上会与
    // SetStatus 覆写冲突，改为隐藏占位（真实状态经覆写的 SetStatus 进气泡）
    status_label_ = lv_label_create(container_);
    lv_obj_set_style_text_font(status_label_, text_font, 0);
    lv_label_set_text(status_label_, "");
    lv_obj_add_flag(status_label_, LV_OBJ_FLAG_HIDDEN);

    // notification_label_：隐藏占位（基类 ShowNotification 的超时回调会对它
    // 做 HIDDEN 切换，不能指向气泡文字，否则气泡会被藏掉）；
    // 通知的实际显示由覆写的 ShowNotification 落到气泡
    notification_label_ = lv_label_create(container_);
    lv_obj_set_style_text_font(notification_label_, text_font, 0);
    lv_label_set_text(notification_label_, "");
    lv_obj_add_flag(notification_label_, LV_OBJ_FLAG_HIDDEN);

    // low_battery_popup_：SetTheme 末尾无条件设置其背景色（不判空），
    // 必须创建。圆屏低电量提示走气泡，这里做隐藏占位。
    low_battery_popup_ = lv_obj_create(container_);
    lv_obj_set_size(low_battery_popup_, 1, 1);
    lv_obj_add_flag(low_battery_popup_, LV_OBJ_FLAG_HIDDEN);
    lv_obj_set_style_bg_opa(low_battery_popup_, LV_OPA_TRANSP, 0);
    lv_obj_set_style_border_width(low_battery_popup_, 0, 0);
    low_battery_label_ = lv_label_create(low_battery_popup_);
    lv_label_set_text(low_battery_label_, "");
    lv_obj_set_style_text_font(low_battery_label_, text_font, 0);

    // chat_message_label_ / content_：独立隐藏占位。
    // 之前把 content_ 指向 bubble_、chat_message_label_ 指向 bubble_label_，
    // 但基类任何未覆写路径（如未来新增的清理/重建逻辑）会对 content_ 做
    // lv_obj_clean、对 chat_message_label_ 做 lv_obj_del，把气泡拆掉。
    // 占位对象与气泡零耦合，基类怎么折腾都不影响圆屏 UI。
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

void RoundScreenDisplay::SetBubbleText(const char* text) {
    DisplayLockGuard lock(this);
    if (bubble_label_ != nullptr && text != nullptr) {
        lv_label_set_text(bubble_label_, text);
    }
}

// ---------------- 协议层钩子（原 API 语义不变，仅换皮肤渲染） ----------------

void RoundScreenDisplay::SetEmotion(const char* emotion) {
    // 彩蛋展示期间不覆盖（10 秒后自动恢复）
    if (easter_egg_until_tick_ > tick_count_) {
        return;
    }
    // 完全复用基类的资产/emoji 渲染（协议名 -> emoji_collection 图片 / noto emoji 字符）
    LcdDisplay::SetEmotion(emotion);
}

void RoundScreenDisplay::SetChatMessage(const char* role, const char* content) {
    if (!setup_ui_called_) {
        ESP_LOGW(TAG, "SetChatMessage('%s','%s') before SetupUI", role, content);
        return;
    }
    // 圆屏气泡只显示最新一条（role 语义保留：system 空串=清空）
    if (content == nullptr || content[0] == '\0') {
        SetBubbleText("我在呢");
        return;
    }
    // 截断到 96 字符（180 宽 2-3 行的容量），保证气泡内完整显示
    if (strlen(content) > 96) {
        char buf[100];
        memcpy(buf, content, 96);
        buf[96] = '\0';
        SetBubbleText(buf);
    } else {
        SetBubbleText(content);
    }
}

void RoundScreenDisplay::ClearChatMessages() {
    // 圆屏是单气泡布局：清屏 = 气泡恢复默认文案。
    // 不调基类实现——它会 lv_obj_clean(content_) 删掉气泡文字（content_
    // 基类语义是滚动消息列表容器），使 bubble_label_ 悬空。
    DisplayLockGuard lock(this);
    if (bubble_label_ != nullptr) {
        lv_label_set_text(bubble_label_, "我在呢");
    }
    chat_message_label_ = nullptr;
}

void RoundScreenDisplay::ShowNotification(const char* notification, int duration_ms) {
    // 圆屏：通知直接落到气泡（基类实现只写隐藏占位 label）。
    // duration_ms 不用于隐藏气泡——气泡是常驻 UI，由下一次 SetStatus/
    // SetChatMessage 自然覆盖通知内容。
    if (!setup_ui_called_) {
        ESP_LOGW(TAG, "ShowNotification('%s') called before SetupUI() - message will be lost!",
                 notification);
    }
    DisplayLockGuard lock(this);
    if (bubble_label_ != nullptr) {
        lv_label_set_text(bubble_label_, notification);
    }
}

void RoundScreenDisplay::SetTheme(Theme* theme) {
    // 基类实现：重绑基类标签（container_/network_label_/...）到新主题字体。
    // 注意：旧字体在 LvglDisplay::SetTextFont 里于 SetTheme 返回后被释放
    // （previous_light_font.reset() -> cbin_font_delete）。基类标签会被
    // 重绑，但下面 BuildMainScreen 创建的圆屏标签不会被基类触碰——
    // 必须在这里一并重绑，否则布局测量走到悬空字体指针（PC=0x0 崩溃，
    // 2026-10-08 "Refreshing display theme" 后 InstrFetchProhibited 事故）。
    LcdDisplay::SetTheme(theme);

    auto lvgl_theme = static_cast<LvglTheme*>(theme);
    auto text_font = lvgl_theme->text_font()->font();
    auto icon_font = lvgl_theme->icon_font()->font();
    auto emoji_font = lvgl_theme->emoji_font()->font();

    // 圆屏布局标签（重绑后旧字体方可安全释放）
    lv_obj_set_style_text_font(round_time_label_, text_font, 0);
    lv_obj_set_style_text_font(round_bat_label_, text_font, 0);
    lv_obj_set_style_text_font(round_hint_label_, text_font, 0);
    lv_obj_set_style_text_font(bubble_label_, text_font, 0);
    lv_obj_set_style_text_font(emoji_label_, emoji_font, 0);
    // 隐藏占位族（同批创建，防止后续路径解引用悬空字体）
    lv_obj_set_style_text_font(chat_message_label_, text_font, 0);
    lv_obj_set_style_text_font(low_battery_label_, text_font, 0);
    // network/mute/battery/status/notification 占位已由基类 SetTheme 重绑，
    // 不重复设置
}

void RoundScreenDisplay::SetStatus(const char* status) {
    if (!setup_ui_called_) {
        return;
    }
    DisplayLockGuard lock(this);
    // 圆屏布局：待机时顶部为时间（基类 UpdateStatusBar 走 SetStatus("%H:%M")）；
    // 其他状态文本显示在气泡（避免遮蔽表情）
    if (status == nullptr) {
        return;
    }
    // 纯时间格式（5 字符 "HH:MM"）写到时间位
    if (strlen(status) == 5 && status[2] == ':') {
        if (round_time_label_ != nullptr) {
            lv_label_set_text(round_time_label_, status);
        }
        return;
    }
    // 其余状态（连接中/激活/升级等）写入气泡
    if (bubble_label_ != nullptr) {
        lv_label_set_text(bubble_label_, status);
    }
}

void RoundScreenDisplay::UpdateStatusBar(bool update_all) {
    // 1) 复用基类节拍逻辑：时间刷新（经我们覆写的 SetStatus 落到时间位）
    LvglDisplay::UpdateStatusBar(update_all);

    // 2) 电量：百分比文本（圆屏无图标字体位，直接 "NN%"）
    auto& board = Board::GetInstance();
    int battery_level;
    bool charging, discharging;
    if (board.GetBatteryLevel(battery_level, charging, discharging)) {
        DisplayLockGuard lock(this);
        if (round_bat_label_ != nullptr) {
            char buf[12];
            if (charging) {
                snprintf(buf, sizeof(buf), "⚡%d%%", battery_level);
            } else {
                snprintf(buf, sizeof(buf), "%d%%", battery_level);
            }
            lv_label_set_text(round_bat_label_, buf);
        }
        // 低电量自动行为（每分钟最多提醒一次，防刷屏）
        if (!charging && battery_level <= 15 &&
            (last_bat_percent_ < 0 || battery_level != last_bat_percent_)) {
            LcdDisplay::SetEmotion("sad");
            SetBubbleText("我有点饿了，快充电");
        }
        last_bat_percent_ = battery_level;
    }
}

// ---------------- 单 BOOT 键三事件（皮肤层反馈） ----------------

void RoundScreenDisplay::HandleKeyEvent(int ev) {
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
            // 板级已处理实际动作（静音/取消/忽略）；这里给可见反馈
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

void RoundScreenDisplay::NextEasterEgg() {
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

void RoundScreenDisplay::Tick1s() {
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

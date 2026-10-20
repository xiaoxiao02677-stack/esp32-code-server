// ════════════════════════════════════════════════════════════════════════
// EMOpet 主题 · EmoSkinDisplay 实现（emo_skin_display.cc）
// ════════════════════════════════════════════════════════════════════════
//
// 移植自 hardware/sets/theme/EMOpet 独立工程（240x240 机器人发光眼）。
// 集成策略：完全复用 YhSkinDisplay 骨架（占位族 / 壁纸双槽 / 字体退休池 /
// 锁纪律 / 气泡 / 时间 / 电量 / 系统卡片），只替换视觉层——
//   · EMOpet 发光眼 canvas（PSRAM 直写自绘）取代背景图 + emoji 表情
//   · "压扁 → 渐亮睁开"的 0.5s 睁眼接管开机首帧（ShowBootSplash 挂载点）
//   · 15 态发光眼表情（idle/listen/speak/happy/love/... ）取代协议 emoji
//
// z-order（屏幕自底向上）：bg_image_（壁纸，index 0）→ emo canvas（index 1）
// → chrome 控件（时间/电量/气泡/提示）→ 系统卡片（yh_skin_cards，基类管理）。
//
// 帧驱动：单个 lv_timer（33ms ≈ 30fps）常驻 taskLVGL；emo_face.c 内部隔帧
// 分频——静止态 15fps，眨眼/转场/说话自动全速。说话态经 Application 设备
// 状态直接判定（不依赖协议消息回灌），驱动能量拟态 + 底部声波条。
//
// 上下文纪律：所有覆写方法遵循基类锁纪律（DisplayLockGuard 递归锁，
// fail-closed）。timer 回调运行在 taskLVGL（LVGL port 已持锁），递归加锁安全。

#include "display/emo_skin/emo_skin_display.h"

#include "application.h"
#include "board.h"
#include "display/emo_skin/emo_face.h"

#include <esp_log.h>

#include <cmath>
#include <cstring>

#define TAG "EmoSkin"

namespace {

// 协议 emotion 字符串 → EMOpet 表情。与 LcdDisplay::SetEmotion 的协议名
// 对齐；未匹配回落 EMO_IDLE。说话/聆听由设备状态单独驱动（见 OnFrameTimer）。
struct EmotionMapEntry {
    const char* name;
    emo_id_t id;
};
const EmotionMapEntry kEmotionMap[] = {
    {"neutral", EMO_IDLE},        {"idle", EMO_IDLE},
    {"happy", EMO_HAPPY},         {"laughing", EMO_HAPPY},    {"loving", EMO_LOVE},
    {"sad", EMO_SAD},             {"crying", EMO_SAD},        {"angry", EMO_ANGRY},
    {"surprised", EMO_SURPRISE},  {"winking", EMO_WINK},      {"dizzy", EMO_DIZZY},
    {"sleepy", EMO_SLEEPY},       {"cool", EMO_STAR},         {"proud", EMO_STAR},
    {"excited", EMO_STAR},        {"thinking", EMO_THINK},    {"embarrassed", EMO_SHY},
    {"shy", EMO_SHY},             {"confused", EMO_THINK},    {"serious", EMO_IDLE},
    {"silly", EMO_WINK},          {"listening", EMO_LISTEN},  {"speaking", EMO_SPEAK},
};

emo_id_t MapEmotion(const char* emotion) {
    if (emotion == nullptr) {
        return EMO_IDLE;
    }
    for (const auto& entry : kEmotionMap) {
        if (strcmp(emotion, entry.name) == 0) {
            return entry.id;
        }
    }
    return EMO_IDLE;
}

// 眼睛配色轮换（双击彩蛋）：{r, g, b}，默认冰蓝（源工程配色）
struct EmoColor {
    uint8_t r, g, b;
    const char* name;
};
const EmoColor kEmoColors[] = {
    { 47, 216, 255, "冰蓝" },   // 源工程默认
    {255,  96, 200, "玫粉"},
    { 72, 255, 148, "薄荷绿"},
    {255, 190,  60, "暖橙"},
};
const int kEmoColorCount = sizeof(kEmoColors) / sizeof(kEmoColors[0]);

// 说话能量拟态：~3Hz 正弦（原版独立工程走真实音频 RMS 频段，主题层
// 不接音频链路，用拟态驱动眼睛跳动 + 声波条，视觉语义一致）。
float SpeakingEnergy(uint32_t now_ms) {
    float phase = static_cast<float>(now_ms % 340u) / 340.0f;
    return 0.35f + 0.55f * (0.5f + 0.5f * sinf(phase * 6.28318f));
}

}  // namespace

EmoSkinDisplay::EmoSkinDisplay(esp_lcd_panel_io_handle_t panel_io, esp_lcd_panel_handle_t panel,
                               int width, int height, int offset_x, int offset_y, bool mirror_x,
                               bool mirror_y, bool swap_xy, const YhSkinProfile& profile)
    : YhSkinDisplay(panel_io, panel, width, height, offset_x, offset_y, mirror_x, mirror_y,
                    swap_xy, profile) {
    layout_ = emo_layout_make(width, height);
}

EmoSkinDisplay::~EmoSkinDisplay() {
    // 防御性：显示对象实际与板子同生命周期（板级裸指针持有、永不 delete），
    // 但若将来走受控析构，必须先停 timer 再拆 canvas，不留野回调。
    if (frame_timer_ != nullptr) {
        lv_timer_delete(frame_timer_);
        frame_timer_ = nullptr;
    }
    emo_canvas_destroy();
}

// ---------------- SetupUI：基类骨架 + EMOpet 视觉层 ----------------

void EmoSkinDisplay::SetupUI() {
    if (IsSetupUICalled()) {
        return;
    }
    // 基类 SetupUI 一次建齐：占位族 / 壁纸链 / chrome 控件，末尾虚调
    // ShowBootSplash() → 本类覆写版本此刻 canvas 未建、直接返回 →
    // 品牌 splash 不会出现，开机首帧由 canvas 的渐亮睁眼接管。
    YhSkinDisplay::SetupUI();

    DisplayLockGuard lock(this);
    if (!lock) { return; }  // fail-closed

    // 表情占位容器整个隐藏：里面的 emoji_label 是可见的（noto "neutral"
    // 字符），不藏会画在 EMOpet 眼睛上。指针保留——基类 SetEmotion 判空安全。
    if (avatar_box_ != nullptr) {
        lv_obj_add_flag(avatar_box_, LV_OBJ_FLAG_HIDDEN);
    }

    // EMOpet canvas：壁纸之上、chrome 之下（bg_image_ 在 index 0）。
    // canvas 内部自带头部深黑底，壁纸在主题模式下退居 splash 底图。
    emo_canvas_obj_ = emo_canvas_create(lv_screen_active(), &layout_);
    if (emo_canvas_obj_ != nullptr) {
        lv_obj_move_to_index(emo_canvas_obj_, 1);
        lv_obj_remove_flag(emo_canvas_obj_, LV_OBJ_FLAG_CLICKABLE);
    } else {
        // PSRAM + 内部 RAM 都分配失败（极端内存压力）：不建 EMOpet 层，
        // 界面回落基类视觉（背景图 + chrome），功能完整只是没有发光眼。
        ESP_LOGE(TAG, "emo canvas unavailable, falling back to base skin");
    }

    // 提示文案换成 EMOpet 主题语境
    if (hint_label_ != nullptr) {
        lv_label_set_text(hint_label_, "短按说话  双击换色");
    }

    // 常驻帧 timer：睁眼渐亮 + 眨眼 + 说话拟态 + 声波条全在这里推进
    StartFrameTimer();

    ESP_LOGI(TAG, "emopet skin ready (%dx%d, scale=%.2f)", layout_.width, layout_.height,
             (double)layout_.scale);
}

// ---------------- 开机画面（覆写）----------------

void EmoSkinDisplay::ShowBootSplash() {
    // 开机首帧由 SetupUI 建 canvas 时的渐亮睁眼接管（canvas 重建即重演），
    // 这里只处理运行期重建场景（如主题切换后基类再次调用）。
    if (!IsSetupUICalled()) {
        return;
    }
    DisplayLockGuard lock(this);
    if (!lock) { return; }
    // 无额外动画模块：EMOpet 的"睁眼"就是它的开机画面。
}

void EmoSkinDisplay::DismissBootSplash() {
    DisplayLockGuard lock(this);
    if (!lock) { return; }
    // EMOpet 睁眼渐亮由 canvas 插值自行收敛（~0.5s），外部要求收开机画面
    // （如配网/升级卡片要上屏）时直接置目标态，控件层立刻可用。
    emo_set_emotion(EMO_IDLE);
}

// ---------------- 帧 timer ----------------

void EmoSkinDisplay::StartFrameTimer() {
    if (frame_timer_ != nullptr) {
        return;
    }
    frame_timer_ = lv_timer_create(
        [](lv_timer_t* timer) {
            static_cast<EmoSkinDisplay*>(lv_timer_get_user_data(timer))->OnFrameTimer();
        },
        33, this);  // ~30fps，emo_face.c 内部静止态自动降 15fps
    if (frame_timer_ != nullptr) {
        lv_timer_set_user_data(frame_timer_, this);
    } else {
        ESP_LOGE(TAG, "lv_timer_create failed; eyes will be static");
    }
}

void EmoSkinDisplay::OnFrameTimer() {
    DisplayLockGuard lock(this);
    if (!lock) { return; }

    // 说话/聆听态直接取设备状态：不依赖协议消息回灌，TTS 结束自然回待机
    auto state = Application::GetInstance().GetDeviceState();
    const bool speaking = (state == kDeviceStateSpeaking);
    const bool listening = (state == kDeviceStateListening);

    if (speaking) {
        if (!speaking_) {
            // 说话态沿：切表情 + 开声波
            emo_set_emotion(EMO_SPEAK);
            emo_set_wave(true);
            speaking_ = true;
        }
        emo_set_energy(SpeakingEnergy(lv_tick_get()));
    } else {
        if (speaking_) {
            // 离开说话态：关声波，回待机表情（聆听态除外）
            emo_set_wave(false);
            speaking_ = false;
            if (!listening && emo_id_ == EMO_SPEAK) {
                emo_set_emotion(EMO_IDLE);
                emo_id_ = EMO_IDLE;
            }
        } else if (listening) {
            // 聆听态（协议 emotion 已切 EMO_LISTEN 时无需重复）
            if (emo_id_ != EMO_LISTEN) {
                emo_set_emotion(EMO_LISTEN);
                emo_id_ = EMO_LISTEN;
            }
        }
        emo_set_energy(0.0f);
    }

    // 低电量脉搏：基类 UpdateStatusBar 有电池才刷新，这里轻量喂入
    if (profile().has_battery && lv_tick_get() - last_bat_check_ > 5000) {
        last_bat_check_ = lv_tick_get();
        auto& board = Board::GetInstance();
        int level = 0;
        bool charging = false, discharging = false;
        if (board.GetBatteryLevel(level, charging, discharging) && !charging && level <= 15) {
            emo_set_battery_low(true);
        } else {
            emo_set_battery_low(false);
        }
    }

    emo_tick();
}

// ---------------- 协议钩子 ----------------

void EmoSkinDisplay::SetEmotion(const char* emotion) {
    if (!IsSetupUICalled() || emotion == nullptr) {
        return;
    }
    // 彩蛋展示期间不覆盖（10 秒窗口，语义与基类一致）
    if (easter_until_tick_ > tick_count_) {
        return;
    }
    DisplayLockGuard lock(this);
    if (!lock) { return; }
    // 说话/聆听态由 OnFrameTimer 的设备状态驱动，协议 emotion 不覆盖
    auto state = Application::GetInstance().GetDeviceState();
    if (state == kDeviceStateSpeaking || state == kDeviceStateListening) {
        return;
    }
    emo_id_ = MapEmotion(emotion);
    emo_set_emotion(emo_id_);
}

void EmoSkinDisplay::SetChatMessage(const char* role, const char* content) {
    // 气泡、UA 过滤、激活码卡片、splash 收起判定全部复用基类；
    // 这里只把"助手开口"落到 EMOpet 脸上（说话态本身由帧循环接管）。
    YhSkinDisplay::SetChatMessage(role, content);
    if (!IsSetupUICalled()) {
        return;
    }
    DisplayLockGuard lock(this);
    if (!lock) { return; }
    if (content != nullptr && content[0] != '\0' &&
        (role == nullptr || strcmp(role, "assistant") == 0)) {
        auto state = Application::GetInstance().GetDeviceState();
        if (state != kDeviceStateSpeaking && state != kDeviceStateListening) {
            emo_id_ = EMO_HAPPY;
            emo_set_emotion(EMO_HAPPY);
        }
    }
}

// ---------------- 按键与彩蛋 ----------------

void EmoSkinDisplay::HandleKeyEvent(int ev) {
    if (!IsSetupUICalled()) {
        return;
    }
    auto state = Application::GetInstance().GetDeviceState();

    switch (ev) {
        case 0:  // 短按：进入聆听。Application::ToggleChatState 已由板级处理
            if (state == kDeviceStateIdle || state == kDeviceStateSpeaking) {
                DisplayLockGuard lock(this);
                if (!lock) { return; }
                emo_id_ = EMO_LISTEN;
                emo_set_emotion(EMO_LISTEN);
                SetBubbleText("在听你说…");
            }
            break;
        case 1:  // 双击：待机轮换眼睛配色，说话中给个惊喜表情
            if (state == kDeviceStateIdle) {
                NextEasterEgg();
            } else if (state == kDeviceStateSpeaking) {
                DisplayLockGuard lock(this);
                if (!lock) { return; }
                emo_id_ = EMO_SURPRISE;
                emo_set_emotion(EMO_SURPRISE);
            }
            break;
        case 2:  // 长按：静音提示落到眼睛表情（气泡文案沿用基类语义）
            if (state == kDeviceStateIdle) {
                auto codec = Board::GetInstance().GetAudioCodec();
                bool muted = (codec != nullptr && codec->output_volume() == 0);
                DisplayLockGuard lock(this);
                if (!lock) { return; }
                emo_id_ = muted ? EMO_SAD : EMO_HAPPY;
                emo_set_emotion(emo_id_);
                SetBubbleText(muted ? "已静音" : "声音开启啦");
            } else if (state == kDeviceStateListening) {
                DisplayLockGuard lock(this);
                if (!lock) { return; }
                emo_id_ = EMO_IDLE;
                emo_set_emotion(EMO_IDLE);
                SetBubbleText("我在呢");
            }
            break;
        default:
            break;
    }
}

void EmoSkinDisplay::NextEasterEgg() {
    // 待机双击：眼睛配色轮换（冰蓝 → 玫粉 → 薄荷绿 → 暖橙），气泡报色名。
    DisplayLockGuard lock(this);
    if (!lock) { return; }
    color_index_ = (color_index_ + 1) % kEmoColorCount;
    const EmoColor& c = kEmoColors[color_index_];
    emo_set_color(c.r, c.g, c.b);
    emo_id_ = EMO_HAPPY;
    emo_set_emotion(EMO_HAPPY);
    char text[32];
    snprintf(text, sizeof(text), "眼睛变成%s啦", c.name);
    SetBubbleText(text);
    easter_until_tick_ = tick_count_ + 10;  // 10 秒后恢复协议驱动表情
}

// ---------------- 1s 节拍 ----------------

void EmoSkinDisplay::Tick1s() {
    if (!IsSetupUICalled()) {
        return;
    }
    tick_count_++;

    // 彩蛋窗口到期：恢复协议驱动表情
    if (easter_until_tick_ > 0 && tick_count_ >= easter_until_tick_) {
        easter_until_tick_ = -1;
        if (Application::GetInstance().GetDeviceState() == kDeviceStateIdle) {
            DisplayLockGuard lock(this);
            if (!lock) { return; }
            emo_id_ = EMO_IDLE;
            emo_set_emotion(EMO_IDLE);
            SetBubbleText("我在呢");
        }
    }

    // 基类节拍：时间刷新（SetStatus → 顶部时间位）、早晚问候（问候表情
    // 走 LcdDisplay::SetEmotion 的 emoji 路径，EMOpet 脸上不可见，属可接受损耗）。
    YhSkinDisplay::Tick1s();
}

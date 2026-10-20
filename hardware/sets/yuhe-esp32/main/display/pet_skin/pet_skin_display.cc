// ════════════════════════════════════════════════════════════════════════
// 像素宠物主题 · PetSkinDisplay 实现（pet_skin_display.cc）
// ════════════════════════════════════════════════════════════════════════
//
// 移植自 hardware/sets/theme/像素宠物 独立工程（240x240），见同目录 PORTING.md。
// 集成策略：完全复用 YhSkinDisplay 骨架（占位族 / 壁纸双槽 / 字体退休池 /
// 锁纪律 / 气泡 / 时间 / 电量 / 系统卡片），只替换视觉层——
//   · 像素宠物 canvas（PSRAM 自绘）取代背景图 + emoji 表情
//   · 3.8s 出生动画取代品牌 splash（ShowBootSplash 虚方法挂载点）
//   · 五态宠物表情（开心/难过/惊讶/困倦/中性）取代协议 emoji
//
// z-order（屏幕自底向上）：bg_image_（壁纸，index 0）→ pet canvas（index 1）
// → chrome 控件（时间/电量/气泡/提示）→ 系统卡片（yh_skin_cards，基类管理）。
//
// 帧驱动：单个 lv_timer（33ms ≈ 30fps）常驻 taskLVGL。待机且无表情变化时
// 跳过渲染（脏标记），避免空转烧 CPU；说话态经 Application 设备状态直接判定，
// 不依赖协议消息回灌，天然不会卡在说话态。
//
// 上下文纪律：所有覆写方法遵循基类锁纪律（DisplayLockGuard 递归锁，
// fail-closed）。timer 回调运行在 taskLVGL（LVGL port 已持锁），递归加锁安全。

#include "display/pet_skin/pet_skin_display.h"

#include "application.h"
#include "board.h"
#include "display/pet_skin/pet_boot_anim.h"
#include "display/pet_skin/pet_canvas.h"
#include "display/yh_skin/yh_skin_boot.h"

#include <esp_log.h>

#include <cmath>
#include <cstdio>
#include <cstring>

#define TAG "PetSkin"

namespace {

// 协议 emotion 字符串 → 宠物五态。与 LcdDisplay::SetEmotion 的协议名对齐；
// 未匹配回落中性（闭眼/嘴型仍由状态驱动）。
struct EmotionMapEntry {
    const char* name;
    pet_expr_t expr;
};
const EmotionMapEntry kEmotionMap[] = {
    {"happy", PET_EXPR_HAPPY},        {"laughing", PET_EXPR_HAPPY},
    {"loving", PET_EXPR_HAPPY},       {"excited", PET_EXPR_HAPPY},
    {"sad", PET_EXPR_SAD},            {"crying", PET_EXPR_SAD},
    {"angry", PET_EXPR_SAD},
    {"surprised", PET_EXPR_SURPRISE}, {"winking", PET_EXPR_SURPRISE},
    {"cool", PET_EXPR_SURPRISE},      {"proud", PET_EXPR_SURPRISE},
    {"sleepy", PET_EXPR_SLEEPY},      {"dizzy", PET_EXPR_SLEEPY},
    {"neutral", PET_EXPR_NEUTRAL},    {"thinking", PET_EXPR_NEUTRAL},
    {"embarrassed", PET_EXPR_NEUTRAL}, {"silly", PET_EXPR_NEUTRAL},
    {"confused", PET_EXPR_NEUTRAL},   {"serious", PET_EXPR_NEUTRAL},
};

pet_expr_t MapEmotion(const char* emotion) {
    if (emotion == nullptr) {
        return PET_EXPR_NEUTRAL;
    }
    for (const auto& entry : kEmotionMap) {
        if (strcmp(emotion, entry.name) == 0) {
            return entry.expr;
        }
    }
    return PET_EXPR_NEUTRAL;
}

// 皮肤名（切换时气泡提示）
const char* kSkinNames[PET_SKIN_MAX] = {"小猫咪", "小棕熊", "云朵兽"};

// 说话嘴部拟态：~3Hz 正弦开合（原版独立工程同样用拟态而非真实音频能量）。
float SpeakingEnergy(uint32_t now_ms) {
    float phase = static_cast<float>(now_ms % 340u) / 340.0f;
    return 0.35f + 0.55f * (0.5f + 0.5f * sinf(phase * 6.28318f));
}

}  // namespace

PetSkinDisplay::PetSkinDisplay(esp_lcd_panel_io_handle_t panel_io, esp_lcd_panel_handle_t panel,
                               int width, int height, int offset_x, int offset_y, bool mirror_x,
                               bool mirror_y, bool swap_xy, const YhSkinProfile& profile)
    : YhSkinDisplay(panel_io, panel, width, height, offset_x, offset_y, mirror_x, mirror_y,
                    swap_xy, profile) {
    layout_ = pet_layout_make(width, height);
}

PetSkinDisplay::~PetSkinDisplay() {
    // 防御性：显示对象实际与板子同生命周期（板级裸指针持有、永不 delete），
    // 但若将来走受控析构，必须先停 timer 再拆 canvas，不留野回调。
    if (frame_timer_ != nullptr) {
        lv_timer_delete(frame_timer_);
        frame_timer_ = nullptr;
    }
    pet_canvas_destroy();
}

// ---------------- SetupUI：基类骨架 + 宠物视觉层 ----------------

void PetSkinDisplay::SetupUI() {
    if (IsSetupUICalled()) {
        return;
    }
    // 基类 SetupUI 一次建齐：占位族 / 壁纸链 / chrome 控件，末尾虚调
    // ShowBootSplash() → 本类覆写版本此刻 canvas 未建、直接返回 →
    // 品牌 splash 不会出现，开机首帧由下面的出生动画接管。
    YhSkinDisplay::SetupUI();

    DisplayLockGuard lock(this);
    if (!lock) { return; }  // fail-closed

    // 表情占位容器整个隐藏：里面的 emoji_label 是可见的（noto "neutral"
    // 字符），不藏会画在宠物脸上。指针保留——基类 SetEmotion 判空安全。
    if (avatar_box_ != nullptr) {
        lv_obj_add_flag(avatar_box_, LV_OBJ_FLAG_HIDDEN);
    }

    // 宠物 canvas：壁纸之上、chrome 之下（bg_image_ 在 index 0）
    pet_canvas_obj_ = pet_canvas_create(lv_screen_active(), &layout_);
    if (pet_canvas_obj_ != nullptr) {
        lv_obj_move_to_index(pet_canvas_obj_, 1);
        lv_obj_remove_flag(pet_canvas_obj_, LV_OBJ_FLAG_CLICKABLE);
    } else {
        // PSRAM + 内部 RAM 都分配失败（极端内存压力）：不建宠物层，
        // 界面回落基类视觉（背景图 + chrome），功能完整只是没有宠物。
        ESP_LOGE(TAG, "pet canvas unavailable, falling back to base skin");
    }

    // 提示文案换成宠物主题语境
    if (hint_label_ != nullptr) {
        lv_label_set_text(hint_label_, "短按说话  双击换宠");
    }

    // 出生动画 + 常驻帧 timer
    StartFrameTimer();
    if (pet_canvas_obj_ != nullptr) {
        pet_boot_anim_start(PET_BOOT_FULL, nullptr);
        boot_animating_ = true;
        pet_canvas_render(pet_boot_anim_prog(), 0.0f, skin_id_, PET_EXPR_NEUTRAL, false);
    }

    ESP_LOGI(TAG, "pixel-pet skin ready (%dx%d, grid=%d)", layout_.width, layout_.height,
             layout_.grid);
}

// ---------------- 开机画面（覆写）----------------

void PetSkinDisplay::ShowBootSplash() {
    // 开机首帧由 SetupUI 尾部的出生动画接管，这里只处理运行期重建场景
    // （如主题切换后基类再次调用）：canvas 在则重启一遍唤醒短版动画。
    if (pet_canvas_obj_ == nullptr) {
        return;
    }
    DisplayLockGuard lock(this);
    if (!lock) { return; }
    if (boot_animating_) {
        return;  // 动画已在播
    }
    pet_boot_anim_start(PET_BOOT_WAKE, nullptr);  // 0.6s 唤醒短版
    boot_animating_ = true;
}

void PetSkinDisplay::DismissBootSplash() {
    DisplayLockGuard lock(this);
    if (!lock) { return; }
    // 外部要求收开机画面（如配网/升级卡片要上屏）：动画跳到完成态，
    // 宠物以完成形态驻留，控件层立刻可用。
    if (boot_animating_) {
        pet_boot_anim_skip();
        boot_animating_ = false;
    }
}

// ---------------- 帧 timer ----------------

void PetSkinDisplay::StartFrameTimer() {
    if (frame_timer_ != nullptr) {
        return;
    }
    frame_timer_ = lv_timer_create(
        [](lv_timer_t* timer) {
            static_cast<PetSkinDisplay*>(lv_timer_get_user_data(timer))->OnFrameTimer();
        },
        33, this);  // ~30fps，与原版 20ms 同量级，留出 LVGL 渲染余量
    if (frame_timer_ != nullptr) {
        lv_timer_set_user_data(frame_timer_, this);
    } else {
        ESP_LOGE(TAG, "lv_timer_create failed; pet will be static");
    }
}

void PetSkinDisplay::OnFrameTimer() {
    DisplayLockGuard lock(this);
    if (!lock) { return; }

    if (boot_animating_) {
        pet_boot_anim_poll();
        const pet_boot_prog_t* prog = pet_boot_anim_prog();
        if (prog == nullptr) {
            // 动画完成：宠物落位待机，报一声问候
            boot_animating_ = false;
            SetBubbleText(pet_boot_greeting());
            pet_canvas_render_idle(0.0f, skin_id_, expr_, false);
        } else {
            pet_canvas_render(prog, 0.0f, skin_id_, PET_EXPR_NEUTRAL, false);
        }
        return;
    }

    const uint32_t now = lv_tick_get();
    // 每 10s 重掷眨眼周期（2.6~4.4s），避免机械感
    if (now - last_blink_reseed_ > 10000 || blink_cycle_ms_ == 0) {
        blink_cycle_ms_ = 2600 + (now % 7) * 260;
        last_blink_reseed_ = now;
    }
    const bool blink = (now % blink_cycle_ms_) < 160;

    // 说话态直接取设备状态：不依赖协议消息回灌，TTS 结束自然回待机
    const bool speaking =
        (Application::GetInstance().GetDeviceState() == kDeviceStateSpeaking);
    frame_div_ ^= 1;  // 隔帧分频：说话态 15fps（3Hz 嘴部动画足够平滑）
    if (speaking) {
        // 说话中隔帧渲染：嘴部按能量拟态开合（~3Hz）。
        // 半数帧跳过 = 给音频/网络任务让出一半渲染预算，
        // 20MHz SPI 的板子全屏 flush 一帧就要 60ms，30fps 必然抢占过度。
        speaking_ = true;
        blink_last_ = blink;
        if (frame_div_) {
            return;
        }
        pet_canvas_render_idle(SpeakingEnergy(now), skin_id_, expr_, blink);
    } else if (speaking_ || blink != blink_last_) {
        // 待机：只在状态离开说话态 / 眨眼沿跳变时重绘，其余帧跳过
        speaking_ = false;
        blink_last_ = blink;
        pet_canvas_render_idle(0.0f, skin_id_, expr_, blink);
    }
}

// ---------------- 协议钩子 ----------------

void PetSkinDisplay::SetEmotion(const char* emotion) {
    if (!IsSetupUICalled() || emotion == nullptr) {
        return;
    }
    // 彩蛋展示期间不覆盖（10 秒窗口，语义与基类一致）
    if (easter_until_tick_ > tick_count_) {
        return;
    }
    DisplayLockGuard lock(this);
    if (!lock) { return; }
    expr_ = MapEmotion(emotion);
    // 不调 LcdDisplay::SetEmotion：那是给 emoji_image_ 换图的，宠物主题里
    // avatar 已隐藏，画上去也看不见，还白白查一次 emoji 集合。
    const bool speaking = (Application::GetInstance().GetDeviceState() == kDeviceStateSpeaking);
    pet_canvas_render_idle(speaking ? SpeakingEnergy(lv_tick_get()) : 0.0f, skin_id_, expr_,
                           false);
}

void PetSkinDisplay::SetChatMessage(const char* role, const char* content) {
    // 气泡、UA 过滤、激活码卡片、splash 收起判定全部复用基类；
    // 这里只把"说话默认带笑意"落到宠物脸上。
    YhSkinDisplay::SetChatMessage(role, content);
    if (!IsSetupUICalled()) {
        return;
    }
    DisplayLockGuard lock(this);
    if (!lock) { return; }
    if (content != nullptr && content[0] != '\0' &&
        (role == nullptr || strcmp(role, "assistant") == 0) && expr_ == PET_EXPR_NEUTRAL) {
        expr_ = PET_EXPR_HAPPY;
        const bool speaking =
            (Application::GetInstance().GetDeviceState() == kDeviceStateSpeaking);
        pet_canvas_render_idle(speaking ? SpeakingEnergy(lv_tick_get()) : 0.0f, skin_id_, expr_,
                               false);
    }
}

// ---------------- 按键与彩蛋 ----------------

void PetSkinDisplay::HandleKeyEvent(int ev) {
    if (!IsSetupUICalled()) {
        return;
    }
    auto state = Application::GetInstance().GetDeviceState();

    switch (ev) {
        case 0:  // 短按：进入聆听。Application::ToggleChatState 已由板级处理
            if (state == kDeviceStateIdle || state == kDeviceStateSpeaking) {
                DisplayLockGuard lock(this);
                if (!lock) { return; }
                expr_ = PET_EXPR_SURPRISE;
                SetBubbleText("在听你说…");
                pet_canvas_render_idle(0.0f, skin_id_, expr_, false);
            }
            break;
        case 1:  // 双击：待机轮换皮肤，说话中给个惊喜表情
            if (state == kDeviceStateIdle) {
                NextEasterEgg();
            } else if (state == kDeviceStateSpeaking) {
                DisplayLockGuard lock(this);
                if (!lock) { return; }
                expr_ = PET_EXPR_SURPRISE;
                pet_canvas_render_idle(SpeakingEnergy(lv_tick_get()), skin_id_, expr_, false);
            }
            break;
        case 2:  // 长按：静音提示落到宠物表情（气泡文案沿用基类语义）
            if (state == kDeviceStateIdle) {
                auto codec = Board::GetInstance().GetAudioCodec();
                bool muted = (codec != nullptr && codec->output_volume() == 0);
                DisplayLockGuard lock(this);
                if (!lock) { return; }
                expr_ = muted ? PET_EXPR_SAD : PET_EXPR_HAPPY;
                SetBubbleText(muted ? "已静音" : "声音开启啦");
                pet_canvas_render_idle(0.0f, skin_id_, expr_, false);
            } else if (state == kDeviceStateListening) {
                DisplayLockGuard lock(this);
                if (!lock) { return; }
                expr_ = PET_EXPR_NEUTRAL;
                SetBubbleText("我在呢");
                pet_canvas_render_idle(0.0f, skin_id_, expr_, false);
            }
            break;
        default:
            break;
    }
}

void PetSkinDisplay::NextEasterEgg() {
    // 待机双击：宠物皮肤轮换（猫 → 熊 → 云兽），气泡报名字。
    DisplayLockGuard lock(this);
    if (!lock) { return; }
    skin_id_ = static_cast<pet_skin_id_t>((skin_id_ + 1) % PET_SKIN_MAX);
    expr_ = PET_EXPR_HAPPY;
    char text[32];
    snprintf(text, sizeof(text), "变成%s啦", kSkinNames[skin_id_]);
    SetBubbleText(text);
    easter_until_tick_ = tick_count_ + 10;  // 10 秒后恢复协议驱动表情
    pet_canvas_render_idle(0.0f, skin_id_, expr_, false);
}

// ---------------- 1s 节拍 ----------------

void PetSkinDisplay::Tick1s() {
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
            expr_ = PET_EXPR_NEUTRAL;
            SetBubbleText("我在呢");
            pet_canvas_render_idle(0.0f, skin_id_, expr_, false);
        }
    }

    // 基类节拍：时间刷新（SetStatus → 顶部时间位）、早晚问候（问候表情
    // 走 LcdDisplay::SetEmotion 的 emoji 路径，宠物脸上不可见，属可接受损耗）。
    YhSkinDisplay::Tick1s();
}

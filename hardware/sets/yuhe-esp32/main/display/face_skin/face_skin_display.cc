// ════════════════════════════════════════════════════════════════════════
// 极简脸 face 主题 · 显示层实现（face_skin_display.cc）
// ════════════════════════════════════════════════════════════════════════
// LVGL v9。只覆写渲染层：Application / 协议 / MCP / 音频链路零改动。
// 骨架继承 YhSkinDisplay（壁纸双槽 / 字体退休池 / 锁纪律 / 占位族 /
// 系统卡片 / profile 几何）。设计原稿：theme/face/docs/。
//
// 纯脸零文字的边界（用户选型）：
//   · 脸上不落一字：气泡/时间/电量/提示全部隐藏，无字体依赖；
//     对话内容靠语音传达，脸只负责表情。
//   · 系统卡片（配网/激活码/升级）例外保留——那是功能界面不是脸，
//     基类 ShowNotification 原样白嫖。
//   · 无用户壁纸时隐藏 bg_image_ 露纯黑底（忠实原稿）；用户下发壁纸后
//     恢复显示（用户意志优先）。
//
// 帧驱动：单个 lv_timer（33ms ≈ 30fps）常驻 taskLVGL，内部按 250ms
// 间隔做设备态对账（pet 单 timer 先例）；说话态隔帧降 15fps 给音频/
// 网络任务让预算（20MHz SPI 全屏 flush 一帧 60ms）。
//
// 已知取舍：基类 Tick1s 的早晚问候走 LcdDisplay::SetEmotion（非虚直调）
// 且文案在气泡里——脸主题里两者都不可见，属纯文字特性，按选型放弃；
// 协议 SetEmotion（AI 情绪）仍然完整驱动表情。

#include "face_skin_display.h"

#include "application.h"
#include "board.h"

#include <esp_log.h>

#include <cstring>

#define TAG "FaceSkin"

namespace {

// 协议 emotion 字符串 → 脸 8 态（未匹配回落 idle：呼吸+游荡照常）
struct EmotionMapEntry {
    const char* name;
    face_expr_t expr;
};
const EmotionMapEntry kEmotionMap[] = {
    {"happy", FACE_EXPR_HAPPY},       {"laughing", FACE_EXPR_HAPPY},
    {"loving", FACE_EXPR_HAPPY},      {"excited", FACE_EXPR_HAPPY},
    {"sad", FACE_EXPR_SLEEPY},        {"crying", FACE_EXPR_SLEEPY},
    {"sleepy", FACE_EXPR_SLEEPY},     {"dizzy", FACE_EXPR_SLEEPY},
    {"angry", FACE_EXPR_ANGRY},
    {"surprised", FACE_EXPR_SURPRISE}, {"winking", FACE_EXPR_SURPRISE},
    {"cool", FACE_EXPR_SURPRISE},     {"proud", FACE_EXPR_SURPRISE},
    {"thinking", FACE_EXPR_THINK},    {"confused", FACE_EXPR_THINK},
    {"serious", FACE_EXPR_THINK},
    {"embarrassed", FACE_EXPR_SHY},   {"silly", FACE_EXPR_SHY},
    {"neutral", FACE_EXPR_IDLE},
};

face_expr_t MapEmotion(const char* emotion) {
    if (emotion == nullptr) {
        return FACE_EXPR_IDLE;
    }
    for (const auto& entry : kEmotionMap) {
        if (strcmp(emotion, entry.name) == 0) {
            return entry.expr;
        }
    }
    return FACE_EXPR_IDLE;
}

}  // namespace

// ---------------- 构造 / 析构 ----------------

FaceSkinDisplay::FaceSkinDisplay(esp_lcd_panel_io_handle_t panel_io,
                                 esp_lcd_panel_handle_t panel, int width, int height,
                                 int offset_x, int offset_y, bool mirror_x, bool mirror_y,
                                 bool swap_xy, const YhSkinProfile& profile)
    : YhSkinDisplay(panel_io, panel, width, height, offset_x, offset_y, mirror_x, mirror_y,
                    swap_xy, profile) {
    // 几何在 SetupUI 里按 profile 现算（face_geom_make）
}

FaceSkinDisplay::~FaceSkinDisplay() {
    // 防御性：显示对象实际与板子同生命周期（板级裸指针持有），
    // 但受控析构时先停 timer 再拆对象树，不留野回调。
    if (frame_timer_ != nullptr) {
        lv_timer_delete(frame_timer_);
        frame_timer_ = nullptr;
    }
    if (core_ != nullptr) {
        face_core_destroy(core_);
        core_ = nullptr;
    }
}

// ---------------- SetupUI ----------------

void FaceSkinDisplay::SetupUI() {
    if (IsSetupUICalled()) {
        return;
    }
    // 基类：占位族 / 壁纸链 / chrome 控件 / 品牌 splash（屿禾工坊，用户选定保留）
    YhSkinDisplay::SetupUI();

    DisplayLockGuard lock(this);
    if (!lock) { return; }  // fail-closed

    // 屏幕底色纯黑（HTML 原稿 240×240 黑底）
    lv_obj_t* screen = lv_screen_active();
    lv_obj_set_style_bg_color(screen, lv_color_black(), 0);
    lv_obj_set_style_bg_grad_color(screen, lv_color_black(), 0);
    lv_obj_set_style_bg_opa(screen, LV_OPA_COVER, 0);

    // 基类 chrome 全部隐退（纯脸零文字；指针保留——基类判空安全）
    if (avatar_box_ != nullptr) {
        lv_obj_add_flag(avatar_box_, LV_OBJ_FLAG_HIDDEN);
    }
    if (bubble_ != nullptr) {
        lv_obj_add_flag(bubble_, LV_OBJ_FLAG_HIDDEN);
    }
    if (time_label_ != nullptr) {
        lv_obj_add_flag(time_label_, LV_OBJ_FLAG_HIDDEN);
    }
    if (battery_text_ != nullptr) {
        lv_obj_add_flag(battery_text_, LV_OBJ_FLAG_HIDDEN);
    }
    if (hint_label_ != nullptr) {
        lv_obj_add_flag(hint_label_, LV_OBJ_FLAG_HIDDEN);
    }

    // 脸渲染核心（几何按 profile 换算）。z 序天然正确：face_root 建在
    // chrome 之后 → 在 bg_image_(index 0)/chrome 之上；开机 splash 与
    // 系统卡片都是 move_foreground 的全屏容器，恒在脸之上，互不遮挡。
    face_geom_t geom = face_geom_make(profile().width, profile().height, profile().round);
    core_ = face_core_create(screen, &geom);
    if (core_ == nullptr) {
        ESP_LOGE(TAG, "face core create failed; falling back to base skin");
    }

    // 无用户壁纸 → 隐藏 bg_image_ 露纯黑底
    ShowFaceOrWallpaper();

    // 唯一常驻 timer：33ms 帧驱动 + 内部 250ms 设备态对账
    frame_timer_ = lv_timer_create(
        [](lv_timer_t* timer) {
            static_cast<FaceSkinDisplay*>(lv_timer_get_user_data(timer))->OnFrameTimer();
        },
        33, this);
    if (frame_timer_ == nullptr) {
        ESP_LOGE(TAG, "lv_timer_create failed; face will be static");
    }

    ESP_LOGI(TAG, "face skin ready (%dx%d round=%d)", profile().width, profile().height,
             profile().round);
}

// ---------------- 壁纸联动 ----------------

void FaceSkinDisplay::ShowFaceOrWallpaper() {
    if (bg_image_ == nullptr) {
        return;
    }
    // 用户壁纸存在 → 显示（用户意志优先）；否则隐藏露纯黑底。
    // boot 壁纸镜像路径（SetBootWallpaper 兜底）只改 src 不改显隐，
    // 脸主题里 bg 隐藏时镜像无视觉效果，行为正确无需干预。
    if (GetWallpaper() != nullptr) {
        lv_obj_remove_flag(bg_image_, LV_OBJ_FLAG_HIDDEN);
    } else {
        lv_obj_add_flag(bg_image_, LV_OBJ_FLAG_HIDDEN);
    }
}

bool FaceSkinDisplay::SetWallpaper(const lv_img_dsc_t* image) {
    const bool ok = YhSkinDisplay::SetWallpaper(image);
    if (ok) {
        DisplayLockGuard lock(this);
        if (lock) { ShowFaceOrWallpaper(); }
    }
    return ok;
}

bool FaceSkinDisplay::ClearWallpaper() {
    const bool ok = YhSkinDisplay::ClearWallpaper();
    if (ok) {
        DisplayLockGuard lock(this);
        if (lock) { ShowFaceOrWallpaper(); }
    }
    return ok;
}

// ---------------- 帧 timer ----------------

void FaceSkinDisplay::OnFrameTimer() {
    DisplayLockGuard lock(this);
    if (!lock) { return; }  // fail-closed
    if (core_ == nullptr) {
        return;
    }

    // 250ms 设备态对账（真源；协议事件只做即时预置）
    const uint32_t now = lv_tick_get();
    if (now - last_poll_ms_ >= 250) {
        last_poll_ms_ = now;
        PollDeviceState();
    }

    // 说话态隔帧降 15fps：状态推进不跳（render=false 只是不碰对象），
    // 给音频/网络任务让出一半渲染预算（pet 皮肤同款先例）
    const bool speaking =
        (Application::GetInstance().GetDeviceState() == kDeviceStateSpeaking);
    bool render = true;
    if (speaking) {
        frame_div_ = !frame_div_;
        render = !frame_div_;
    } else {
        frame_div_ = false;
    }
    face_core_tick(core_, render);
}

void FaceSkinDisplay::PollDeviceState() {
    if (core_ == nullptr) {
        return;
    }
    // interact 傲娇彩蛋窗口：轮询让路（回弹 520ms + 表情 1.8s 展示完
    // 再回到设备态，250ms 对账不会把彩蛋表情立刻打回）
    if (face_core_in_interact(core_)) {
        return;
    }
    face_expr_t target;
    face_glow_t glow;
    switch (Application::GetInstance().GetDeviceState()) {
        case kDeviceStateSpeaking:
            target = FACE_EXPR_TALKING;  // 点头 + 嘴 90ms 开合拟态
            glow = FACE_GLOW_SPEAKING;   // 暖橙
            break;
        case kDeviceStateListening:
            target = FACE_EXPR_HAPPY;  // 在听：注视（游荡停）+ 微笑
            glow = FACE_GLOW_LISTENING;  // 青绿
            break;
        case kDeviceStateConnecting:
            target = FACE_EXPR_THINK;  // 等服务器回话：一字嘴思考
            glow = FACE_GLOW_CONNECTING;  // 琥珀慢闪
            break;
        case kDeviceStateFatalError:
            target = FACE_EXPR_ANGRY;  // 致命错误：方嘴生气
            glow = FACE_GLOW_ERROR;     // 珊瑚红
            break;
        default:
            target = expr_;  // 待机/其余：情绪记忆（协议 SetEmotion 落的值）
            glow = FACE_GLOW_IDLE;  // 原稿淡蓝
            break;
    }
    if (target != face_core_expr(core_)) {
        face_core_set_expr(core_, target);
    }
    face_core_set_glow(core_, glow);  // 幂等（内部查同值短路）
}

// ---------------- 协议钩子 ----------------

void FaceSkinDisplay::SetEmotion(const char* emotion) {
    if (!IsSetupUICalled() || emotion == nullptr || core_ == nullptr) {
        return;
    }
    // interact 彩蛋窗口让路（pet easter_until_tick_ 同款语义）
    if (face_core_in_interact(core_)) {
        return;
    }
    expr_ = MapEmotion(emotion);
    // 说话中只记不切：TTS 期间轮询锁 TALKING，结束后回落自然带出情绪
    if (Application::GetInstance().GetDeviceState() == kDeviceStateSpeaking) {
        return;
    }
    DisplayLockGuard lock(this);
    if (!lock) { return; }
    face_core_set_expr(core_, expr_);
}

void FaceSkinDisplay::SetChatMessage(const char* role, const char* content) {
    // 基类：UA 过滤 / 激活码卡片 / splash 收起判定 / 系统卡片收起
    //（气泡写入在脸主题里不可见，语义无副作用）
    YhSkinDisplay::SetChatMessage(role, content);
    if (!IsSetupUICalled() || core_ == nullptr) {
        return;
    }
    // AI 说话内容 → 记一层笑意：TTS 中轮询锁 TALKING，说完自然回落到
    // HAPPY，形成"说完还在笑"的余韵（pet「说话默认带笑意」同款思路）
    if (content == nullptr || content[0] == '\0' || role == nullptr ||
        strcmp(role, "assistant") != 0 || face_core_in_interact(core_)) {
        return;
    }
    expr_ = FACE_EXPR_HAPPY;
    if (Application::GetInstance().GetDeviceState() == kDeviceStateSpeaking) {
        return;
    }
    DisplayLockGuard lock(this);
    if (!lock) { return; }
    face_core_set_expr(core_, expr_);
}

// ---------------- 按键与彩蛋 ----------------

void FaceSkinDisplay::HandleKeyEvent(int ev) {
    if (!IsSetupUICalled() || core_ == nullptr) {
        return;
    }
    auto state = Application::GetInstance().GetDeviceState();

    switch (ev) {
        case 0:  // 短按：进入聆听（Application::ToggleChatState 已由板级处理）
            if (state == kDeviceStateIdle || state == kDeviceStateSpeaking) {
                if (face_core_in_interact(core_)) {
                    break;
                }
                DisplayLockGuard lock(this);
                if (!lock) { break; }
                expr_ = FACE_EXPR_HAPPY;  // 微笑注视预置，轮询随后接管
                face_core_set_expr(core_, expr_);
                face_core_set_glow(core_, FACE_GLOW_LISTENING);  // 青绿即时亮
            }
            break;
        case 1:  // 双击：待机傲娇回弹彩蛋；说话中眨个眼
            if (state == kDeviceStateIdle) {
                NextEasterEgg();
            } else if (state == kDeviceStateSpeaking) {
                DisplayLockGuard lock(this);
                if (!lock) { break; }
                face_core_blink(core_);
            }
            break;
        case 2:  // 长按：静音切换落到脸上（静音蔫脸 / 开心脸）
            if (state == kDeviceStateIdle) {
                auto codec = Board::GetInstance().GetAudioCodec();
                bool muted = (codec != nullptr && codec->output_volume() == 0);
                DisplayLockGuard lock(this);
                if (!lock) { break; }
                expr_ = muted ? FACE_EXPR_SLEEPY : FACE_EXPR_HAPPY;
                face_core_set_expr(core_, expr_);
            } else if (state == kDeviceStateListening) {
                DisplayLockGuard lock(this);
                if (!lock) { break; }
                face_core_blink(core_);  // 聆听中长按：眨眼示意
            }
            break;
        default:
            break;
    }
}

void FaceSkinDisplay::NextEasterEgg() {
    // 待机双击：傲娇回弹 520ms + 随机小表情 1.8s（HTML interact() 原样）
    DisplayLockGuard lock(this);
    if (!lock || core_ == nullptr) { return; }
    face_core_interact(core_);
}

// ════════════════════════════════════════════════════════════════════════
// 猫咪 cat 主题 · 显示层实现（cat_skin_display.cc）
// ════════════════════════════════════════════════════════════════════════
// LVGL v9。只覆写渲染层：Application / 协议 / MCP / 音频链路零改动。
// 骨架继承 YhSkinDisplay（壁纸双槽 / 字体退休池 / 锁纪律 / 占位族 /
// 系统卡片 / profile 几何）。素材管线：theme/cat/tools/video_to_frames.py
// → theme/cat/frames/ → CMake DEFAULT_ASSETS_EXTRA_FILES → assets 分区。
//
// 状态区分（用户硬需求）：表情动画通道之外，角标（cat_badge_t）是
// 独立第二信号通道——动画在随机循环里天然不区分状态，角标颜色才是
// "我现在是什么状态"的稳定答案。聆听态再加动画骤停（定格 idle1
// 注视帧），与待机循环形成动作层面的差异。
//
// BOOT 键视觉反馈：板级已做行为（短按 ToggleChatState / 双击 / 长按
// 静音切换），本层 HandleKeyEvent 只做即时视觉预置——不等 250ms 轮询，
// 按下那一刻角标/动画就变（face 主题教训：反馈必须即时）。
//
// WiFi 配网：基类 SetupUI 建品牌 splash + 系统卡片族，Connecting/
// WifiConfiguring 态由轮询自动亮琥珀角标；配网卡片界面由基类
// ShowNotification 白嫖（用户要求"不要忘记配网"——复用不重造）。
//
// 已知取舍：基类 Tick1s 的早晚问候走 LcdDisplay::SetEmotion（非虚直调）
// 且文案在气泡里——猫主题里两者都不可见，属纯文字特性，按选型放弃；
// 协议 SetEmotion（AI 情绪）仍然完整驱动表情。

#include "cat_skin_display.h"

#include "application.h"
#include "board.h"

#include <esp_log.h>

#include <cstring>

#define TAG "CatSkin"

namespace {

// 协议 emotion 字符串 → 猫动画编号（未匹配回落 idle1）。
// 对应原项目 anim_engine.c 的情绪映射：
//   happy/excited/surprised → happy, sad → sad, angry → angry,
//   fear/cry → cry, shy/love → shy, 中性/思考 → idle
struct EmotionMapEntry {
    const char* name;
    cat_anim_id_t anim;
};
const EmotionMapEntry kEmotionMap[] = {
    {"happy", CAT_ANIM_HAPPY},       {"laughing", CAT_ANIM_HAPPY},
    {"loving", CAT_ANIM_HAPPY},      {"excited", CAT_ANIM_HAPPY},
    {"surprised", CAT_ANIM_HAPPY},   {"winking", CAT_ANIM_HAPPY},
    {"proud", CAT_ANIM_HAPPY},       {"cool", CAT_ANIM_HAPPY},
    {"sad", CAT_ANIM_SAD},           {"sleepy", CAT_ANIM_IDLE3},
    {"crying", CAT_ANIM_CRY},        {"angry", CAT_ANIM_ANGRY},
    {"fear", CAT_ANIM_CRY},          {"shy", CAT_ANIM_SHY},
    {"embarrassed", CAT_ANIM_SHY},   {"silly", CAT_ANIM_SHY},
    {"thinking", CAT_ANIM_IDLE1},    {"confused", CAT_ANIM_IDLE2},
    {"serious", CAT_ANIM_IDLE1},     {"neutral", CAT_ANIM_IDLE1},
    {"dizzy", CAT_ANIM_IDLE3},
};

cat_anim_id_t MapEmotion(const char* emotion) {
    if (emotion == nullptr) {
        return CAT_ANIM_IDLE1;
    }
    for (const auto& entry : kEmotionMap) {
        if (strcmp(emotion, entry.name) == 0) {
            return entry.anim;
        }
    }
    return CAT_ANIM_IDLE1;
}

}  // namespace

// ---------------- 构造 / 析构 ----------------

CatSkinDisplay::CatSkinDisplay(esp_lcd_panel_io_handle_t panel_io,
                               esp_lcd_panel_handle_t panel, int width, int height,
                               int offset_x, int offset_y, bool mirror_x, bool mirror_y,
                               bool swap_xy, const YhSkinProfile& profile)
    : YhSkinDisplay(panel_io, panel, width, height, offset_x, offset_y, mirror_x, mirror_y,
                    swap_xy, profile) {}

CatSkinDisplay::~CatSkinDisplay() {
    // 防御性：显示对象实际与板子同生命周期（板级裸指针持有），
    // 但受控析构时先停 timer 再拆对象树，不留野回调。
    if (frame_timer_ != nullptr) {
        lv_timer_delete(frame_timer_);
        frame_timer_ = nullptr;
    }
    if (anim_ != nullptr) {
        cat_anim_destroy(anim_);
        anim_ = nullptr;
    }
}

// ---------------- SetupUI ----------------

void CatSkinDisplay::SetupUI() {
    if (IsSetupUICalled()) {
        return;
    }
    // 基类：占位族 / 壁纸链 / chrome 控件 / 品牌 splash（屿禾工坊，用户选定保留）
    YhSkinDisplay::SetupUI();

    DisplayLockGuard lock(this);
    if (!lock) { return; }  // fail-closed

    // 屏幕底色纯黑（猫脸四周留黑）
    lv_obj_t* screen = lv_screen_active();
    lv_obj_set_style_bg_color(screen, lv_color_black(), 0);
    lv_obj_set_style_bg_grad_color(screen, lv_color_black(), 0);
    lv_obj_set_style_bg_opa(screen, LV_OPA_COVER, 0);

    // 基类 chrome 全部隐退（零文字猫脸；指针保留——基类判空安全）
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

    // 猫脸渲染核心（几何按 profile 换算）。z 序天然正确：canvas 建在
    // chrome 之后 → 在 bg_image_ 之上；开机 splash 与系统卡片都是
    // move_foreground 的全屏容器，恒在猫脸之上，互不遮挡。
    cat_geom_t geom = cat_geom_make(profile().width, profile().height);
    anim_ = cat_anim_create(screen, &geom);
    if (anim_ == nullptr) {
        ESP_LOGE(TAG, "cat anim create failed (assets missing?); chrome stays hidden");
        // 素材缺失（拷机/老 assets.bin）：不做任何猫脸 UI——基类 chrome
        // 已隐藏，屏幕留黑 + 系统卡片仍可用（配网/激活不受影响）。
        return;
    }

    // 无用户壁纸 → 隐藏 bg_image_ 露纯黑底
    ShowCatOrWallpaper();

    // 唯一常驻 timer：66ms（15fps，与素材帧率一致）+ 内部 250ms 设备态对账
    frame_timer_ = lv_timer_create(
        [](lv_timer_t* timer) {
            static_cast<CatSkinDisplay*>(lv_timer_get_user_data(timer))->OnFrameTimer();
        },
        CAT_FRAME_MS, this);
    if (frame_timer_ == nullptr) {
        ESP_LOGE(TAG, "lv_timer_create failed; cat will be static");
    }

    ESP_LOGI(TAG, "cat skin ready (%dx%d round=%d)", profile().width, profile().height,
             profile().round);
}

// ---------------- 壁纸联动 ----------------

void CatSkinDisplay::ShowCatOrWallpaper() {
    if (bg_image_ == nullptr) {
        return;
    }
    // 用户壁纸存在 → 显示（用户意志优先）；否则隐藏露纯黑底。
    if (GetWallpaper() != nullptr) {
        lv_obj_remove_flag(bg_image_, LV_OBJ_FLAG_HIDDEN);
    } else {
        lv_obj_add_flag(bg_image_, LV_OBJ_FLAG_HIDDEN);
    }
}

bool CatSkinDisplay::SetWallpaper(const lv_img_dsc_t* image) {
    const bool ok = YhSkinDisplay::SetWallpaper(image);
    if (ok) {
        DisplayLockGuard lock(this);
        if (lock) { ShowCatOrWallpaper(); }
    }
    return ok;
}

bool CatSkinDisplay::ClearWallpaper() {
    const bool ok = YhSkinDisplay::ClearWallpaper();
    if (ok) {
        DisplayLockGuard lock(this);
        if (lock) { ShowCatOrWallpaper(); }
    }
    return ok;
}

// ---------------- 帧 timer ----------------

void CatSkinDisplay::OnFrameTimer() {
    DisplayLockGuard lock(this);
    if (!lock) { return; }  // fail-closed
    if (anim_ == nullptr) {
        return;
    }

    // 250ms 设备态对账（真源；协议事件只做即时预置）
    const uint32_t now = lv_tick_get();
    if (now - last_poll_ms_ >= 250) {
        last_poll_ms_ = now;
        PollDeviceState();
    }

    // 15fps 全帧渲染（帧动画对丢帧敏感；逐帧按需解码 ~10ms/帧，
    // 66ms 间隔内余量充足。说话态表情帧推进在 tick 内部暂停——
    // 嘴形全帧顶替显示，解码表情帧纯属浪费，音频链路正忙）
    cat_anim_tick(anim_, true);
}

void CatSkinDisplay::PollDeviceState() {
    if (anim_ == nullptr) {
        return;
    }
    // 彩蛋窗口：轮询让路（彩蛋动画 2s 展示完再回到设备态，
    // 250ms 对账不会把彩蛋动画立刻打回）
    if (cat_anim_in_easter(anim_)) {
        return;
    }
    // 待机随机循环 / 说话猫脸动画都是「当前动画」的自然延续，
    // 轮询不强制切动画（只在状态明确要求时切）：
    //   聆听 = idle1 定格（与待机循环的骤停差异）
    //   错误 = angry 锁定
    //   其余 = 不打断（说话/连接/待机沿用当前动画，嘴形/角标照常）
    // 这是与 face 主题的关键差异：face 的表情是参数化的（set_expr 幂等），
    // cat 的动画是序列（每 250ms 强切会把随机循环打回情绪动画，循环永续不了）。
    cat_badge_t badge;
    bool frozen = false;
    bool mouth = false;
    cat_anim_id_t force_anim = CAT_ANIM_IDLE1;
    bool force = false;
    const auto state = Application::GetInstance().GetDeviceState();
    switch (state) {
        case kDeviceStateSpeaking:
            badge = CAT_BADGE_SPEAKING;  // 暖橙
            mouth = true;                // 说话嘴形轮换
            break;
        case kDeviceStateListening:
            badge = CAT_BADGE_LISTENING;  // 青绿
            frozen = true;
            if (cat_anim_current(anim_) != CAT_ANIM_IDLE1) {
                force_anim = CAT_ANIM_IDLE1;
                force = true;  // 聆听切 idle1（定格注视帧）
            }
            break;
        case kDeviceStateFatalError:
            badge = CAT_BADGE_ERROR;  // 珊瑚红
            if (cat_anim_current(anim_) != CAT_ANIM_ANGRY) {
                force_anim = CAT_ANIM_ANGRY;
                force = true;  // 致命错误锁 angry
            }
            break;
        case kDeviceStateConnecting:
        case kDeviceStateActivating:
        case kDeviceStateUpgrading:
        case kDeviceStateWifiConfiguring:
        case kDeviceStateNotifying:
            badge = CAT_BADGE_CONNECTING;  // 琥珀慢闪
            break;
        default:
            badge = CAT_BADGE_IDLE;  // 淡蓝：待机随机循环继续
            break;
    }
    // 说话→非说话转换：TTS 期间记下的情绪余韵播一次（淡入——
    // 说话末帧是嘴形帧，硬切会闪跳）
    const bool speaking_now = (state == kDeviceStateSpeaking);
    if (was_speaking_ && !speaking_now) {
        force_anim = expr_;
        force = true;
        frozen = false;
    }
    was_speaking_ = speaking_now;
    cat_anim_set_badge(anim_, badge);  // 幂等（内部查同值短路）
    cat_anim_mouth_active(anim_, mouth);
    cat_anim_set_frozen(anim_, frozen);
    if (force) {
        // 聆听/错误切换：淡入（从动画骤停切到注视帧，平滑过渡）
        cat_anim_play(anim_, force_anim, true);
        if (frozen) {
            // 聆听定格：取 idle1 中段稳定帧作注视画面
            cat_anim_seek(anim_, CAT_ANIM_FRAMES / 2);
        }
    }
}

// ---------------- 协议钩子 ----------------

void CatSkinDisplay::SetEmotion(const char* emotion) {
    if (!IsSetupUICalled() || emotion == nullptr || anim_ == nullptr) {
        return;
    }
    // 彩蛋窗口让路（pet easter_until_tick_ 同款语义）
    if (cat_anim_in_easter(anim_)) {
        return;
    }
    expr_ = MapEmotion(emotion);
    // 说话中只记不切：TTS 结束回 Idle 后，下一个 250ms 轮询周期里
    // SetEmotion 的情绪动画由「段播完随机循环」自然带出——但协议情绪
    // 应当即时可见，所以在非说话态直接播。
    if (Application::GetInstance().GetDeviceState() == kDeviceStateSpeaking) {
        return;
    }
    DisplayLockGuard lock(this);
    if (!lock) { return; }
    cat_anim_play(anim_, expr_, true);  // 情绪指令：淡入（原项目 EXPR 路径）
}

void CatSkinDisplay::SetChatMessage(const char* role, const char* content) {
    // 基类：UA 过滤 / 激活码卡片 / splash 收起判定 / 系统卡片收起
    //（气泡写入在猫主题里不可见，语义无副作用）
    YhSkinDisplay::SetChatMessage(role, content);
    if (!IsSetupUICalled() || anim_ == nullptr) {
        return;
    }
    // AI 说话内容 → 记一层开心：TTS 中轮询锁 speaking，说完自然回落到
    // happy，形成"说完还在笑"的余韵（face「说话默认带笑意」同款思路）
    if (content == nullptr || content[0] == '\0' || role == nullptr ||
        strcmp(role, "assistant") != 0 || cat_anim_in_easter(anim_)) {
        return;
    }
    expr_ = CAT_ANIM_HAPPY;
    if (Application::GetInstance().GetDeviceState() == kDeviceStateSpeaking) {
        return;
    }
    DisplayLockGuard lock(this);
    if (!lock) { return; }
    cat_anim_play(anim_, expr_, true);  // 淡入
}

// ---------------- 按键与彩蛋 ----------------

void CatSkinDisplay::HandleKeyEvent(int ev) {
    if (!IsSetupUICalled() || anim_ == nullptr) {
        return;
    }
    auto state = Application::GetInstance().GetDeviceState();

    switch (ev) {
        case 0:  // 短按：进聆听（板级已 ToggleChatState，这里即时视觉预置）
            if (state == kDeviceStateIdle || state == kDeviceStateSpeaking) {
                if (cat_anim_in_easter(anim_)) {
                    break;
                }
                DisplayLockGuard lock(this);
                if (!lock) { break; }
                // 不等 250ms 轮询：按下那一刻猫脸定格 + 青绿角标亮
                cat_anim_play(anim_, CAT_ANIM_IDLE1, true);  // 淡入到注视帧
                cat_anim_seek(anim_, CAT_ANIM_FRAMES / 2);
                cat_anim_set_frozen(anim_, true);
                cat_anim_mouth_active(anim_, false);
                cat_anim_set_badge(anim_, CAT_BADGE_LISTENING);  // 青绿即时亮
            }
            break;
        case 1:  // 双击：彩蛋动画（cry/angry/sad 随机，播完回待机循环）
            if (state == kDeviceStateIdle) {
                NextEasterEgg();
            }
            break;
        case 2:  // 长按：板级已做静音切换/取消对话，这里只做视觉反馈
            if (state == kDeviceStateIdle) {
                auto codec = Board::GetInstance().GetAudioCodec();
                const bool muted = (codec != nullptr && codec->output_volume() == 0);
                DisplayLockGuard lock(this);
                if (!lock) { break; }
                if (muted) {
                    // 已静音：灰角标短显 2s（tick 内部自动回落 idle 角标）
                    cat_anim_set_badge(anim_, CAT_BADGE_MUTED);
                } else {
                    // 开声了：开心一下（声音回来的正反馈，淡入）
                    expr_ = CAT_ANIM_HAPPY;
                    cat_anim_play(anim_, expr_, true);
                }
            }
            break;
        default:
            break;
    }
}

void CatSkinDisplay::NextEasterEgg() {
    // 待机双击：随机彩蛋动画（cry/angry/sad），播完自动回待机随机循环
    DisplayLockGuard lock(this);
    if (!lock || anim_ == nullptr) { return; }
    cat_anim_easter_egg(anim_);
}

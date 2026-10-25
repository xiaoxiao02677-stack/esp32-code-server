// ════════════════════════════════════════════════════════════════════════
// 灯语 DengYu 主题 · 显示层实现（dengyu_skin_display.cc）
// ════════════════════════════════════════════════════════════════════════
// LVGL v9。只覆写渲染层：Application / 协议 / MCP / 音频链路零改动。
// 骨架继承 YhSkinDisplay（壁纸双槽 / 字体退休池 / 锁纪律 / 占位族 /
// 系统卡片 / profile 几何）。设计提案见 theme/DengYu/docs/。
//
// 色板（RGB565 量化值，与提案 token 表逐一对账）：
//   night #080C19 0x0863 / ember400 #F7A65A 0xF52B / ember300 #FFCA8C 0xFE51
//   cream #F7EFE6 0xF77C / haze500 #8C96BD 0x8CB7 / sage #ADDBB5 0xAED6
//   coral #EF715A 0xEB8B / paper #F7EFE6 0xF77C / d-text #312819 0x3143
//
// 字体方案（零新增 flash 依赖 + 固定文案专属字档）：
//   动态聊天文本  → 跟随主题 text 字体：basic 890 字（编译期）→
//                   assets 运行时 common 档接管（5258 字），继承基类
//                   退休池/重绑全部机制，无悬垂风险（2026-10-08 事故根因）。
//   固定文案      → font_dengyu_16_4 专属字档（158 码位，~24KB flash，
//                   由 gen_dengyu_font.py 生成，与 yh_skin/font_splash_20_4
//                   同一模式）：16_4 组件字档是限词表，连「灯/萤」都没有，
//                   固定文案若绑 16_4 必出豆腐块。
//   晨间时钟      → 主题 text（20_4）即可：冒号+数字 basic 全有。
//
// 状态机真源：Application::GetDeviceState()，250ms lv_timer 轮询对账
//（PetSkinDisplay 同款先例：不依赖协议消息回灌，TTS 结束自然回待机）。
// 协议事件（SetChatMessage/ShowNotification/HandleKeyEvent）只做即时预置。
// 线程纪律：DisplayLockGuard 递归锁，fail-closed；timer 回调在 taskLVGL。

#include "dengyu_skin_display.h"

#include "application.h"
#include "board.h"
#include "display/yh_skin/yh_skin_boot.h"
#include "settings.h"

#include <esp_log.h>

#include <cmath>
#include <cstdio>
#include <cstring>
#include <ctime>
#include <string>

#define TAG "DengYuSkin"

namespace {
// LVGL 动画回调必须是 void(void*, int32_t)：lv_obj_set_style_opa 的三参
// 原型不能直接强转（强转后调用是 UB，三参那版只会把 obj 传进 style selector 位）
static void row_opa_cb(void* var, int32_t v) {
    lv_obj_set_style_opa(static_cast<lv_obj_t*>(var), static_cast<lv_opa_t>(v), 0);
}
}  // namespace

// DengYu 固定文案专属字档（gen_dengyu_font.py 生成，158 码位）
extern const lv_font_t font_dengyu_16_4;

// ---- 色板 ----
static const uint32_t kNight = 0x080C19;
static const uint32_t kEmber400 = 0xF7A65A;
static const uint32_t kEmber300 = 0xFFCA8C;
static const uint32_t kCream = 0xF7EFE6;
static const uint32_t kHaze500 = 0x8C96BD;
static const uint32_t kSage = 0xADDBB5;
static const uint32_t kCoral = 0xEF715A;
static const uint32_t kPaper = 0xF7EFE6;
static const uint32_t kDText = 0x312819;
static const uint32_t kDCream = 0x5A4D3A;

// ---- 固定文案（全部字符已打包进 font_dengyu_16_4）----
static const char* kIdleWords[] = {"想着你", "今晚风好安静", "等你说晚安", "我在呢"};
static constexpr size_t kIdleWordsCount = sizeof(kIdleWords) / sizeof(kIdleWords[0]);
static const char* kThinkWords[] = {"想想哦", "让我翻翻记忆", "快好了", "在想啦"};
static constexpr size_t kThinkWordsCount = sizeof(kThinkWords) / sizeof(kThinkWords[0]);

// ---- 字幕 ----
static constexpr uint16_t kSubtitleMaxCodepoints = 56;  // 16px 一行约 14 字 × 4 行
static constexpr uint16_t kTypeBufferSize = 448;        // 56 汉字 × 3B + null

// 打字机逐字间隔（90~140ms 随机抖动，提案 tier 值）
static uint32_t TypewriterDelay() {
    return 90 + (lv_tick_get() % 51);
}

// UTF-8 安全截断（不切半码点；超长补 …）
static size_t Utf8ByteLen(const char* s, size_t max_bytes, size_t max_cp) {
    size_t len = strlen(s);
    size_t pos = 0, cp = 0;
    while (pos < len && cp < max_cp) {
        unsigned char lead = static_cast<unsigned char>(s[pos]);
        size_t seq = 1;
        if ((lead & 0x80u) == 0x00u) {
            seq = 1;
        } else if ((lead & 0xE0u) == 0xC0u) {
            seq = 2;
        } else if ((lead & 0xF0u) == 0xE0u) {
            seq = 3;
        } else if ((lead & 0xF8u) == 0xF0u) {
            seq = 4;
        }
        if (pos + seq > len || pos + seq > max_bytes) {
            break;
        }
        pos += seq;
        ++cp;
    }
    return pos;
}

// 一个 UTF-8 码点的字节长度
static size_t Utf8SeqLenAt(const char* s) {
    unsigned char lead = static_cast<unsigned char>(*s);
    if ((lead & 0x80u) == 0x00u) return 1;
    if ((lead & 0xE0u) == 0xC0u) return 2;
    if ((lead & 0xF0u) == 0xE0u) return 3;
    if ((lead & 0xF8u) == 0xF0u) return 4;
    return 1;
}

// ---------------- 构造 / 析构 ----------------

DengYuSkinDisplay::DengYuSkinDisplay(esp_lcd_panel_io_handle_t panel_io,
                                     esp_lcd_panel_handle_t panel, int width, int height,
                                     int offset_x, int offset_y, bool mirror_x, bool mirror_y,
                                     bool swap_xy, const YhSkinProfile& profile)
    : YhSkinDisplay(panel_io, panel, width, height, offset_x, offset_y, mirror_x, mirror_y,
                    swap_xy, profile) {
    round_screen_ = profile.round;
    // 几何：光萤中心 + 字幕区（短边 240 基准，profile.scaled 等比）
    const int w = profile.width;
    const int h = profile.height;
    if (profile.round || w < h) {
        // 圆屏/竖屏：光萤上区（y 中心 ≈ 屏高 40%），字幕流下区
        orb_center_x_ = w / 2;
        orb_center_y_ = h * 40 / 100;
        flow_left_ = w / 12;
        flow_width_ = w - 2 * flow_left_;
        flow_top_ = h * 58 / 100;
        flow_height_ = h - flow_top_ - h / 16;
        rows_capacity_ = profile.round ? 1 : 5;
    } else {
        // 横屏 320x240：左光萤（x ≈ 屏宽 22%），右字幕流（44% → 右缘）
        orb_center_x_ = w * 22 / 100;
        orb_center_y_ = h / 2;
        flow_left_ = w * 44 / 100;
        flow_width_ = w - flow_left_ - w / 20;
        flow_top_ = h / 14;
        flow_height_ = h - flow_top_ - h / 10;
        rows_capacity_ = 5;
    }
    orb_diameter_ = profile.scaled(64);
}

DengYuSkinDisplay::~DengYuSkinDisplay() {
    // 防御性：显示对象实际与板子同生命周期（板级裸指针持有），
    // 但受控析构时先停 timer 再拆对象，不留野回调。
    if (eq_timer_ != nullptr) {
        lv_timer_delete(eq_timer_);
        eq_timer_ = nullptr;
    }
    if (poll_timer_ != nullptr) {
        lv_timer_delete(poll_timer_);
        poll_timer_ = nullptr;
    }
    StopTypewriter();
    if (orb_ != nullptr) {
        dengyu_orb_destroy(orb_);
        orb_ = nullptr;
    }
    if (mini_orb_ != nullptr) {
        dengyu_orb_destroy(mini_orb_);
        mini_orb_ = nullptr;
    }
}

// ---------------- SetupUI ----------------

void DengYuSkinDisplay::SetupUI() {
    if (IsSetupUICalled()) {
        return;
    }
    // 基类：占位族 / 壁纸链 / chrome 控件 / 品牌 splash（屿禾工坊，用户选定保留）
    YhSkinDisplay::SetupUI();

    DisplayLockGuard lock(this);
    if (!lock) { return; }  // fail-closed

    // 屏幕底色换成灯语夜幕（覆盖基类深紫渐变）
    lv_obj_t* screen = lv_screen_active();
    lv_obj_set_style_bg_color(screen, lv_color_hex(kNight), 0);
    lv_obj_set_style_bg_grad_color(screen, lv_color_hex(kNight), 0);
    lv_obj_set_style_bg_opa(screen, LV_OPA_COVER, 0);

    // 基类 chrome 隐退：灯语布局不用时间/电量/气泡/提示行/表情
    // （指针保留——基类 SetStatus/SetEmotion/ShowNotification 判空安全）
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

    BuildDengYuScene();
    LoadPalette();
    LoadCompanionDays();

    // 250ms 设备态对账（真源），运行在 taskLVGL，递归加锁安全
    poll_timer_ = lv_timer_create(PollTimerCb, 250, this);
    if (poll_timer_ != nullptr) {
        lv_timer_set_user_data(poll_timer_, this);
    }

    // 待机光语（splash 盖着不冲突：splash 是不透明全屏容器，z 序最上）
    EnterDengYuState(DENGYU_STATE_IDLE);

    ESP_LOGI(TAG, "dengyu skin ready (%dx%d round=%d)", profile().width, profile().height,
             round_screen_);
}

void DengYuSkinDisplay::BuildDengYuScene() {
    lv_obj_t* screen = lv_screen_active();

    // 主光萤（wrapper 直径=涟漪最大径 d·178/64，中心在 orb_center_）
    orb_ = dengyu_orb_create(screen, orb_center_x_, orb_center_y_, orb_diameter_);

    // 说话态迷你光萤（顶部居中 y=24，隐藏创建）
    mini_orb_ = dengyu_mini_orb_create(screen, profile().width / 2, profile().scaled(24),
                                       profile().scaled(26));
    if (mini_orb_ != nullptr) {
        dengyu_orb_set_visible(mini_orb_, false);
    }

    // 状态短语 / 待机短句（叠在光萤下方同一位置，状态机互斥显隐）
    int info_y = orb_center_y_ + orb_diameter_ * 100 / 64;  // 光萤外圈下缘
    status_line_ = lv_label_create(screen);
    lv_label_set_text(status_line_, "");
    lv_obj_set_style_text_font(status_line_, &font_dengyu_16_4, 0);
    lv_obj_set_style_text_color(status_line_, lv_color_hex(kCream), 0);
    lv_obj_align(status_line_, LV_ALIGN_TOP_MID, 0, info_y);
    lv_obj_add_flag(status_line_, LV_OBJ_FLAG_HIDDEN);

    idle_word_ = lv_label_create(screen);
    lv_label_set_text(idle_word_, kIdleWords[0]);
    lv_obj_set_style_text_font(idle_word_, &font_dengyu_16_4, 0);
    lv_obj_set_style_text_color(idle_word_, lv_color_hex(kCream), 0);
    lv_obj_set_style_opa(idle_word_, LV_OPA_70, 0);
    lv_obj_align(idle_word_, LV_ALIGN_TOP_MID, 0, info_y);

    // 字幕流容器（flex column，底部对齐；圆屏不用它，仍建一个隐藏防判空）
    flow_ = lv_obj_create(screen);
    lv_obj_set_size(flow_, flow_width_, flow_height_);
    lv_obj_set_pos(flow_, flow_left_, flow_top_);
    lv_obj_set_style_bg_opa(flow_, LV_OPA_TRANSP, 0);
    lv_obj_set_style_border_width(flow_, 0, 0);
    lv_obj_set_style_pad_all(flow_, 0, 0);
    lv_obj_set_flex_flow(flow_, LV_FLEX_FLOW_COLUMN);
    lv_obj_set_flex_align(flow_, LV_FLEX_ALIGN_END, LV_FLEX_ALIGN_START, LV_FLEX_ALIGN_START);
    lv_obj_remove_flag(flow_, LV_OBJ_FLAG_SCROLLABLE);
    lv_obj_remove_flag(flow_, LV_OBJ_FLAG_CLICKABLE);
    if (round_screen_) {
        lv_obj_add_flag(flow_, LV_OBJ_FLAG_HIDDEN);
    }

    // 圆屏单行字幕（居中，超长 WRAP 两行）——动态文本，跟随主题字体
    sub_label_ = lv_label_create(screen);
    lv_label_set_text(sub_label_, "");
    lv_obj_set_style_text_color(sub_label_, lv_color_hex(kCream), 0);
    lv_obj_set_width(sub_label_, profile().width - profile().scaled(36));
    lv_label_set_long_mode(sub_label_, LV_LABEL_LONG_WRAP);
    lv_obj_set_style_text_align(sub_label_, LV_TEXT_ALIGN_CENTER, 0);
    lv_obj_align(sub_label_, LV_ALIGN_BOTTOM_MID, 0, -profile().scaled(28));
    {
        auto fonts = CurrentFonts();
        if (fonts.text != nullptr) {
            lv_obj_set_style_text_font(sub_label_, fonts.text, 0);
        }
    }
    if (!round_screen_) {
        lv_obj_add_flag(sub_label_, LV_OBJ_FLAG_HIDDEN);
    }

    BuildEq();
    BuildMorningCard();
}

// ---------------- EQ 声纹 ----------------

void DengYuSkinDisplay::BuildEq() {
    eq_box_ = lv_obj_create(lv_screen_active());
    lv_obj_set_size(eq_box_, profile().scaled(96), profile().scaled(24));
    // 挂在光萤下方：EQ 是说话态专属视觉，跟随光萤位置（横屏在左区）
    lv_obj_align(eq_box_, LV_ALIGN_TOP_MID, 0, orb_center_y_ + orb_diameter_ * 100 / 64);
    lv_obj_set_style_bg_opa(eq_box_, LV_OPA_TRANSP, 0);
    lv_obj_set_style_border_width(eq_box_, 0, 0);
    lv_obj_set_style_pad_all(eq_box_, 0, 0);
    lv_obj_remove_flag(eq_box_, LV_OBJ_FLAG_SCROLLABLE);
    lv_obj_remove_flag(eq_box_, LV_OBJ_FLAG_CLICKABLE);
    lv_obj_set_flex_flow(eq_box_, LV_FLEX_FLOW_ROW);
    lv_obj_set_flex_align(eq_box_, LV_FLEX_ALIGN_CENTER, LV_FLEX_ALIGN_CENTER,
                          LV_FLEX_ALIGN_CENTER);
    lv_obj_add_flag(eq_box_, LV_OBJ_FLAG_HIDDEN);

    for (int i = 0; i < 5; i++) {
        eq_bars_[i] = lv_bar_create(eq_box_);
        lv_obj_set_size(eq_bars_[i], profile().scaled(4), profile().scaled(12));
        lv_bar_set_range(eq_bars_[i], 0, 20);
        lv_bar_set_value(eq_bars_[i], 8, LV_ANIM_OFF);
        lv_obj_set_style_radius(eq_bars_[i], 2, LV_PART_MAIN);
        lv_obj_set_style_bg_color(eq_bars_[i], lv_color_hex(kEmber300), LV_PART_INDICATOR);
        lv_obj_set_style_bg_opa(eq_bars_[i], LV_OPA_TRANSP, LV_PART_MAIN);
        lv_obj_remove_flag(eq_bars_[i], LV_OBJ_FLAG_CLICKABLE);
    }
}

void DengYuSkinDisplay::EqStart() {
    if (eq_box_ == nullptr) {
        return;
    }
    lv_obj_clear_flag(eq_box_, LV_OBJ_FLAG_HIDDEN);
    if (eq_timer_ == nullptr) {
        eq_timer_ = lv_timer_create(EqBarTimerCb, 110, this);
        if (eq_timer_ != nullptr) {
            lv_timer_set_user_data(eq_timer_, this);
        }
    }
}

void DengYuSkinDisplay::EqStop() {
    if (eq_timer_ != nullptr) {
        lv_timer_delete(eq_timer_);
        eq_timer_ = nullptr;
    }
    if (eq_box_ != nullptr) {
        lv_obj_add_flag(eq_box_, LV_OBJ_FLAG_HIDDEN);
    }
}

void DengYuSkinDisplay::EqBarTimerCb(lv_timer_t* timer) {
    auto* self = static_cast<DengYuSkinDisplay*>(lv_timer_get_user_data(timer));
    if (self == nullptr) {
        return;
    }
    DisplayLockGuard lock(self);
    if (!lock) { return; }
    // ~3Hz 正弦能量拟态：5 根柱相位差 0.9rad
    uint32_t t = lv_tick_get();
    for (int i = 0; i < 5; i++) {
        if (self->eq_bars_[i] == nullptr) {
            continue;
        }
        float phase = static_cast<float>(t % 340u) / 340.0f * 6.28318f + i * 0.9f;
        float energy = 0.5f + 0.5f * sinf(phase);
        int v = static_cast<int>(4 + energy * 16);
        lv_bar_set_value(self->eq_bars_[i], v, LV_ANIM_OFF);
    }
}

// ---------------- 晨间卡片 ----------------

void DengYuSkinDisplay::BuildMorningCard() {
    lv_obj_t* screen = lv_screen_active();
    morning_root_ = lv_obj_create(screen);
    lv_obj_set_size(morning_root_, profile().width, profile().height);
    lv_obj_align(morning_root_, LV_ALIGN_CENTER, 0, 0);
    lv_obj_set_style_bg_color(morning_root_, lv_color_hex(kPaper), 0);
    lv_obj_set_style_bg_opa(morning_root_, LV_OPA_COVER, 0);
    lv_obj_set_style_border_width(morning_root_, 0, 0);
    lv_obj_set_style_radius(morning_root_, 0, 0);
    lv_obj_set_style_pad_all(morning_root_, 0, 0);
    lv_obj_remove_flag(morning_root_, LV_OBJ_FLAG_SCROLLABLE);
    lv_obj_remove_flag(morning_root_, LV_OBJ_FLAG_CLICKABLE);
    lv_obj_add_flag(morning_root_, LV_OBJ_FLAG_HIDDEN);

    // 时钟用主题 text（20_4）：冒号+数字 basic 档全有；assets 换字体后由
    // 基类 RebindStaleFontsEverywhere 全树改绑兜底（勿绑 font_dengyu_16_4，
    // 那是静态字档，绑了就享受不到 common 档升级）
    morning_clock_ = lv_label_create(morning_root_);
    lv_label_set_text(morning_clock_, "--:--");
    lv_obj_set_style_text_color(morning_clock_, lv_color_hex(kDText), 0);
    lv_obj_align(morning_clock_, LV_ALIGN_TOP_MID, 0, profile().scaled(40));
    {
        auto fonts = CurrentFonts();
        if (fonts.text != nullptr) {
            lv_obj_set_style_text_font(morning_clock_, fonts.text, 0);
        }
    }

    morning_greet_ = lv_label_create(morning_root_);
    lv_obj_set_style_text_font(morning_greet_, &font_dengyu_16_4, 0);
    lv_obj_set_style_text_color(morning_greet_, lv_color_hex(kDCream), 0);
    lv_label_set_long_mode(morning_greet_, LV_LABEL_LONG_WRAP);
    lv_obj_set_width(morning_greet_, profile().width - profile().scaled(48));
    lv_obj_set_style_text_align(morning_greet_, LV_TEXT_ALIGN_CENTER, 0);
    lv_label_set_text(morning_greet_, "");
    lv_obj_align(morning_greet_, LV_ALIGN_TOP_MID, 0, profile().scaled(100));
}

void DengYuSkinDisplay::TryEnterMorning() {
    if (morning_root_ == nullptr || morning_until_tick_ >= 0) {
        return;
    }
    // 调用路径有二：SetStatus（协议任务，基类锁已释放）与 Tick1s（esp_timer
    // 任务）——两者此刻都不持锁，这里必须自锁；DisplayLockGuard 递归，重入安全。
    DisplayLockGuard lock(this);
    if (!lock) { return; }  // fail-closed
    if (morning_until_tick_ >= 0) {
        return;  // 双重检查：拿锁间隙可能已被另一路径开过
    }
    time_t now = time(nullptr);
    struct tm tmv;
    localtime_r(&now, &tmv);
    // 年份 < 2025 = 时间未同步，别用 1970 瞎开卡片（基类问候同款判断）
    if (tmv.tm_year < 2025 - 1900) {
        return;
    }
    if (tmv.tm_hour != 7) {
        return;
    }
    // 每天只开一次：跨天（last_morning_day_ != mday）才允许再触发
    if (last_morning_day_ == tmv.tm_mday) {
        return;
    }
    last_morning_day_ = tmv.tm_mday;
    morning_until_tick_ = tick_count_ + 30;  // 30 秒卡片
    UpdateMorningClock();

    char greet[96];
    if (companion_days_ > 0) {
        snprintf(greet, sizeof(greet),
                 "早安，今天是我们在一起的第 %ld 天。\n去把今天过好，我在家等你。",
                 static_cast<long>(companion_days_));
    } else {
        snprintf(greet, sizeof(greet), "早安。\n新的一天，我也在。");
    }
    lv_label_set_text(morning_greet_, greet);

    // 盖住主界面（z 序最上；光萤动画停住）
    lv_obj_clear_flag(morning_root_, LV_OBJ_FLAG_HIDDEN);
    lv_obj_move_foreground(morning_root_);
    // 天气胶囊：服务器 weather 指令通道未接时保持隐藏（占位预留）
    EnterDengYuState(DENGYU_STATE_MORNING);
    ESP_LOGI(TAG, "morning card shown (day %ld)", static_cast<long>(companion_days_));
}

void DengYuSkinDisplay::ExitMorning() {
    if (morning_until_tick_ < 0) {
        return;
    }
    morning_until_tick_ = -1;
    if (morning_root_ != nullptr) {
        lv_obj_add_flag(morning_root_, LV_OBJ_FLAG_HIDDEN);
    }
    // 回待机：状态机真源（poll）会立刻对账到实际设备态
    EnterDengYuState(DENGYU_STATE_IDLE);
}

void DengYuSkinDisplay::UpdateMorningClock() {
    if (morning_clock_ == nullptr) {
        return;
    }
    time_t now = time(nullptr);
    struct tm tmv;
    localtime_r(&now, &tmv);
    char buf[8];
    snprintf(buf, sizeof(buf), "%02d:%02d", tmv.tm_hour, tmv.tm_min);
    lv_label_set_text(morning_clock_, buf);
}

// ---------------- 状态机 ----------------

bool DengYuSkinDisplay::IsRound() const {
    return round_screen_;
}

bool DengYuSkinDisplay::IsTall() const {
    return !round_screen_ && profile().width < profile().height;
}

bool DengYuSkinDisplay::IsWide() const {
    return !round_screen_ && profile().width >= profile().height;
}

void DengYuSkinDisplay::PollTimerCb(lv_timer_t* timer) {
    auto* self = static_cast<DengYuSkinDisplay*>(lv_timer_get_user_data(timer));
    if (self != nullptr) {
        self->PollDeviceState();
    }
}

void DengYuSkinDisplay::PollDeviceState() {
    DisplayLockGuard lock(this);
    if (!lock) { return; }  // fail-closed
    if (morning_until_tick_ >= 0) {
        return;  // 晨间卡片期间状态机冻结（30s 后 ExitMorning 复原）
    }
    // 开机 splash 期间不抢镜：设备态先映射到 IDLE，光萤在 splash 下
    // 呼吸营造氛围，Dismiss 后真值接管（首个非 Idle/Starting 状态到达）
    auto state = Application::GetInstance().GetDeviceState();
    dengyu_state_t target;
    switch (state) {
        case kDeviceStateListening:
            target = DENGYU_STATE_LISTENING;
            break;
        case kDeviceStateSpeaking:
            target = DENGYU_STATE_SPEAKING;
            break;
        case kDeviceStateConnecting:
            // 连接中：光萤转「思考」三点（等服务器回话的隐喻）
            target = DENGYU_STATE_THINKING;
            break;
        case kDeviceStateFatalError:
            target = DENGYU_STATE_ERROR;
            break;
        default:
            target = error_latch_ ? DENGYU_STATE_ERROR : DENGYU_STATE_IDLE;
            break;
    }
    if (target != dengyu_state_) {
        EnterDengYuState(target);
    }
}

void DengYuSkinDisplay::EnterDengYuState(dengyu_state_t state) {
    dengyu_state_ = state;

    // 说话态：主光萤隐退，迷你光萤登场；其余状态反之
    if (orb_ != nullptr) {
        dengyu_orb_set_visible(orb_, state != DENGYU_STATE_SPEAKING);
    }
    if (mini_orb_ != nullptr) {
        if (state == DENGYU_STATE_SPEAKING) {
            dengyu_orb_set_visible(mini_orb_, true);
            dengyu_orb_set_palette(mini_orb_, dengyu_orb_colors(palette_));
            dengyu_mini_orb_idle(mini_orb_);
        } else {
            dengyu_orb_set_visible(mini_orb_, false);
        }
    }

    switch (state) {
        case DENGYU_STATE_IDLE:
            if (orb_ != nullptr) {
                // 离开断连/聆听后回轮换盘配色
                dengyu_orb_set_palette(orb_, dengyu_orb_colors(palette_));
                dengyu_orb_idle(orb_);
            }
            if (idle_word_ != nullptr) {
                lv_obj_clear_flag(idle_word_, LV_OBJ_FLAG_HIDDEN);
            }
            HideStatusLine();
            EqStop();
            break;
        case DENGYU_STATE_LISTENING:
            if (orb_ != nullptr) {
                dengyu_orb_listen(orb_);  // 内部切青苔绿
            }
            if (idle_word_ != nullptr) {
                lv_obj_add_flag(idle_word_, LV_OBJ_FLAG_HIDDEN);
            }
            ShowStatusLine("在听，慢慢说", kSage);
            EqStop();
            break;
        case DENGYU_STATE_THINKING:
            if (orb_ != nullptr) {
                dengyu_orb_think(orb_);
            }
            if (idle_word_ != nullptr) {
                lv_obj_add_flag(idle_word_, LV_OBJ_FLAG_HIDDEN);
            }
            ShowStatusLine(kThinkWords[0], kEmber300);
            EqStop();
            break;
        case DENGYU_STATE_SPEAKING:
            if (idle_word_ != nullptr) {
                lv_obj_add_flag(idle_word_, LV_OBJ_FLAG_HIDDEN);
            }
            HideStatusLine();
            EqStart();
            break;
        case DENGYU_STATE_MORNING:
            if (orb_ != nullptr) {
                dengyu_orb_stop(orb_);
            }
            if (idle_word_ != nullptr) {
                lv_obj_add_flag(idle_word_, LV_OBJ_FLAG_HIDDEN);
            }
            HideStatusLine();
            EqStop();
            break;
        case DENGYU_STATE_ERROR:
            if (orb_ != nullptr) {
                dengyu_orb_error(orb_);
            }
            if (idle_word_ != nullptr) {
                lv_obj_add_flag(idle_word_, LV_OBJ_FLAG_HIDDEN);
            }
            ShowStatusLine("信号走丢了", kCoral);
            EqStop();
            break;
    }
}

// ---------------- 字幕流 ----------------

void DengYuSkinDisplay::OnRowEnterDeleted(lv_event_t* e) {
    // 行删除时若它正是打字机目标行，提前失效句柄（防悬垂）。
    // 场景：行数上限挤掉最旧行 / ClearChatMessages 清理 flow_。
    auto* self = static_cast<DengYuSkinDisplay*>(lv_event_get_user_data(e));
    if (self == nullptr) {
        return;
    }
    lv_obj_t* obj = static_cast<lv_obj_t*>(lv_event_get_target(e));
    if (obj == self->type_label_) {
        self->type_label_ = nullptr;
    }
}

void DengYuSkinDisplay::PushSubtitleRow(const char* who, const char* text, bool is_user) {
    if (round_screen_) {
        // 圆屏变体：只显示当前一句（单行居中，超长 WRAP 两行）
        if (sub_label_ == nullptr) {
            return;
        }
        lv_obj_clear_flag(sub_label_, LV_OBJ_FLAG_HIDDEN);
        lv_obj_set_style_text_color(sub_label_, lv_color_hex(is_user ? kEmber400 : kCream), 0);
        lv_label_set_text(sub_label_, text);
        return;
    }
    if (flow_ == nullptr) {
        return;
    }
    // 行数上限：超出删最旧行
    uint32_t child_count = lv_obj_get_child_count(flow_);
    if (child_count >= static_cast<uint32_t>(rows_capacity_)) {
        lv_obj_t* first = lv_obj_get_child(flow_, 0);
        if (first != nullptr) {
            lv_obj_delete(first);  // 若含打字机行，OnRowEnterDeleted 会失效句柄
        }
    }
    lv_obj_t* row = lv_obj_create(flow_);
    lv_obj_set_width(row, flow_width_);
    lv_obj_set_style_bg_opa(row, LV_OPA_TRANSP, 0);
    lv_obj_set_style_border_width(row, 0, 0);
    lv_obj_set_style_pad_all(row, 0, 0);
    lv_obj_set_style_pad_bottom(row, profile().scaled(4), 0);
    lv_obj_remove_flag(row, LV_OBJ_FLAG_SCROLLABLE);
    lv_obj_remove_flag(row, LV_OBJ_FLAG_CLICKABLE);

    // who 标签（小字 haze500）
    lv_obj_t* who_label = lv_label_create(row);
    lv_obj_set_style_text_font(who_label, &font_dengyu_16_4, 0);
    lv_obj_set_style_text_color(who_label, lv_color_hex(kHaze500), 0);
    lv_label_set_text(who_label, who);
    lv_obj_set_width(who_label, flow_width_);
    if (is_user) {
        lv_obj_set_style_text_align(who_label, LV_TEXT_ALIGN_RIGHT, 0);
    }

    // 正文：跟随主题字体（basic → assets common，退休池保平安）
    lv_obj_t* label = lv_label_create(row);
    lv_obj_set_width(label, flow_width_);
    lv_label_set_long_mode(label, LV_LABEL_LONG_WRAP);
    lv_obj_set_style_text_color(label, lv_color_hex(is_user ? kEmber400 : kCream), 0);
    lv_obj_set_style_text_align(label, is_user ? LV_TEXT_ALIGN_RIGHT : LV_TEXT_ALIGN_LEFT, 0);
    auto fonts = CurrentFonts();
    if (fonts.text != nullptr) {
        lv_obj_set_style_text_font(label, fonts.text, 0);
    }
    lv_label_set_text(label, text);

    lv_obj_set_flex_flow(row, LV_FLEX_FLOW_COLUMN);
    lv_obj_set_flex_align(row, LV_FLEX_ALIGN_END, LV_FLEX_ALIGN_START, LV_FLEX_ALIGN_START);

    // 入场动画：y+8 → 0 + opa（一次性，340ms ease-out）
    lv_anim_t a;
    lv_anim_init(&a);
    lv_anim_set_var(&a, row);
    lv_anim_set_exec_cb(&a, (lv_anim_exec_xcb_t)lv_obj_set_y);
    lv_anim_set_values(&a, lv_obj_get_y(row) + profile().scaled(8), lv_obj_get_y(row));
    lv_anim_set_duration(&a, 340);
    lv_anim_set_path_cb(&a, lv_anim_path_ease_out);
    lv_anim_start(&a);

    lv_anim_t o;
    lv_anim_init(&o);
    lv_anim_set_var(&o, row);
    lv_anim_set_exec_cb(&o, row_opa_cb);
    lv_anim_set_values(&o, LV_OPA_TRANSP, LV_OPA_COVER);
    lv_anim_set_duration(&o, 340);
    lv_anim_set_path_cb(&o, lv_anim_path_ease_out);
    lv_anim_start(&o);
}

void DengYuSkinDisplay::StartTypewriter(const char* text) {
    StopTypewriter();
    if (text == nullptr || text[0] == '\0' || flow_ == nullptr) {
        return;
    }
    // UTF-8 安全截断（不切半码点；超长补 …）
    size_t len = Utf8ByteLen(text, kTypeBufferSize - 1, kSubtitleMaxCodepoints);
    memset(type_buffer_, 0, sizeof(type_buffer_));
    strncpy(type_buffer_, text, len);
    if (len < strlen(text)) {
        size_t base = Utf8ByteLen(text, kTypeBufferSize - 4, kSubtitleMaxCodepoints - 1);
        memset(type_buffer_, 0, sizeof(type_buffer_));
        strncpy(type_buffer_, text, base);
        strncat(type_buffer_, "…", sizeof(type_buffer_) - base - 1);
    }
    type_len_ = static_cast<uint16_t>(strlen(type_buffer_));
    type_pos_ = 0;

    // 行数上限防御：打字机行入场前同样挤旧行
    uint32_t child_count = lv_obj_get_child_count(flow_);
    if (child_count >= static_cast<uint32_t>(rows_capacity_)) {
        lv_obj_t* first = lv_obj_get_child(flow_, 0);
        if (first != nullptr) {
            lv_obj_delete(first);
        }
    }

    // 建「正在打字」的 AI 行（who 标签 + 空正文，逐字往里追加）
    lv_obj_t* row = lv_obj_create(flow_);
    lv_obj_set_width(row, flow_width_);
    lv_obj_set_style_bg_opa(row, LV_OPA_TRANSP, 0);
    lv_obj_set_style_border_width(row, 0, 0);
    lv_obj_set_style_pad_all(row, 0, 0);
    lv_obj_set_style_pad_bottom(row, profile().scaled(4), 0);
    lv_obj_remove_flag(row, LV_OBJ_FLAG_SCROLLABLE);
    lv_obj_remove_flag(row, LV_OBJ_FLAG_CLICKABLE);
    // 行被删时失效打字机句柄（防悬垂）
    lv_obj_add_event_cb(row, OnRowEnterDeleted, LV_EVENT_DELETE, this);

    lv_obj_t* who_label = lv_label_create(row);
    lv_obj_set_style_text_font(who_label, &font_dengyu_16_4, 0);
    lv_obj_set_style_text_color(who_label, lv_color_hex(kHaze500), 0);
    lv_label_set_text(who_label, "灯灯");
    lv_obj_set_width(who_label, flow_width_);

    type_label_ = lv_label_create(row);
    lv_obj_set_width(type_label_, flow_width_);
    lv_label_set_long_mode(type_label_, LV_LABEL_LONG_WRAP);
    lv_obj_set_style_text_color(type_label_, lv_color_hex(kCream), 0);
    auto fonts = CurrentFonts();
    if (fonts.text != nullptr) {
        lv_obj_set_style_text_font(type_label_, fonts.text, 0);
    }
    lv_label_set_text(type_label_, "");

    lv_obj_set_flex_flow(row, LV_FLEX_FLOW_COLUMN);
    lv_obj_set_flex_align(row, LV_FLEX_ALIGN_END, LV_FLEX_ALIGN_START, LV_FLEX_ALIGN_START);

    type_timer_ = lv_timer_create(TypewriterTimerCb, TypewriterDelay(), this);
    if (type_timer_ != nullptr) {
        lv_timer_set_user_data(type_timer_, this);
    }
}

void DengYuSkinDisplay::TypewriterTimerCb(lv_timer_t* timer) {
    auto* self = static_cast<DengYuSkinDisplay*>(lv_timer_get_user_data(timer));
    if (self == nullptr) {
        return;
    }
    self->AdvanceTypewriter();
}

void DengYuSkinDisplay::AdvanceTypewriter() {
    DisplayLockGuard lock(this);
    if (!lock) { return; }
    if (type_timer_ == nullptr || type_label_ == nullptr) {
        StopTypewriter();
        return;
    }
    if (type_pos_ >= type_len_) {
        StopTypewriter();  // 全文播完
        return;
    }
    // 一次追加 1 个 UTF-8 码点（绝不切半）
    size_t seq = Utf8SeqLenAt(type_buffer_ + type_pos_);
    char ch[5] = {0};
    memcpy(ch, type_buffer_ + type_pos_, seq);
    lv_label_ins_text(type_label_, LV_LABEL_POS_LAST, ch);
    type_pos_ += static_cast<uint16_t>(seq);
    // 每字随机 90~140ms 抖动：改 timer 周期，下个 tick 生效
    if (type_timer_ != nullptr) {
        lv_timer_set_period(type_timer_, TypewriterDelay());
    }
}

void DengYuSkinDisplay::StopTypewriter() {
    if (type_timer_ != nullptr) {
        lv_timer_delete(type_timer_);
        type_timer_ = nullptr;
    }
    type_label_ = nullptr;
    type_pos_ = 0;
    type_len_ = 0;
}

void DengYuSkinDisplay::ShowStatusLine(const char* text, uint32_t color, int ttl_ticks) {
    if (status_line_ == nullptr || text == nullptr) {
        return;
    }
    lv_obj_clear_flag(status_line_, LV_OBJ_FLAG_HIDDEN);
    lv_obj_set_style_text_color(status_line_, lv_color_hex(color), 0);
    lv_label_set_text(status_line_, text);
    status_until_tick_ = (ttl_ticks > 0) ? tick_count_ + ttl_ticks : -1;
}

void DengYuSkinDisplay::HideStatusLine() {
    if (status_line_ != nullptr) {
        lv_obj_add_flag(status_line_, LV_OBJ_FLAG_HIDDEN);
    }
    status_until_tick_ = -1;
}

void DengYuSkinDisplay::RotateIdleWord() {
    idle_word_idx_ = (idle_word_idx_ + 1) % kIdleWordsCount;
    if (idle_word_ != nullptr) {
        lv_label_set_text(idle_word_, kIdleWords[idle_word_idx_]);
    }
}

// ---------------- 协议钩子 ----------------

void DengYuSkinDisplay::SetStatus(const char* status) {
    if (!IsSetupUICalled() || status == nullptr) {
        return;
    }
    // 基类行为：HH:MM 进顶部时间位（DengYu 已隐藏时间位，视觉上无变化），
    // 但它内部会 DismissSplashIfNeeded()——「进待机」的收起信号照旧生效；
    // splash 吸收逻辑照旧（基类负责开机状态行）。
    YhSkinDisplay::SetStatus(status);
    // 时间更新顺带检查晨间卡片
    if (strlen(status) == 5 && status[2] == ':') {
        TryEnterMorning();
    }
}

void DengYuSkinDisplay::SetEmotion(const char* emotion) {
    // 光语主题：表情由光萤状态承担，emoji 不画（avatar 已隐藏）。
    // 基类彩蛋窗口判定（10 秒）对本类无意义：彩蛋=光萤配色轮换，
    // 由 HandleKeyEvent 双击直达。这里空转，不碰 emoji 路径。
    if (!IsSetupUICalled() || emotion == nullptr) {
        return;
    }
    (void)emotion;
}

void DengYuSkinDisplay::SetChatMessage(const char* role, const char* content) {
    if (!IsSetupUICalled()) {
        ESP_LOGW(TAG, "SetChatMessage before SetupUI");
        return;
    }
    // 空消息复位：圆屏清空字幕，横/竖屏清空字幕流
    if (content == nullptr || content[0] == '\0') {
        DisplayLockGuard lock(this);
        if (!lock) { return; }  // fail-closed
        StopTypewriter();
        if (sub_label_ != nullptr && round_screen_) {
            lv_label_set_text(sub_label_, "");
        }
        if (flow_ != nullptr) {
            lv_obj_clean(flow_);  // 若含打字机行，OnRowEnterDeleted 同步失效句柄
        }
        EnterDengYuState(DENGYU_STATE_IDLE);
        return;
    }
    // system 角色的 UA 串 / 激活码仍走基类卡片逻辑（含 HideCards 等语义）
    if (role != nullptr && strcmp(role, "system") == 0) {
        YhSkinDisplay::SetChatMessage(role, content);
        return;
    }
    DisplayLockGuard lock(this);
    if (!lock) { return; }  // fail-closed

    bool is_user = (role != nullptr && strcmp(role, "user") == 0);
    StopTypewriter();
    if (is_user) {
        PushSubtitleRow("你", content, true);
        // 用户发言 = 真对话 = 开机流程完成（非 system 角色同基类判定）
        DismissBootSplash();
    } else {
        PushSubtitleRow("灯灯", "", false);
        StartTypewriter(content);  // 正文逐字填充
        // AI 回复 = 说话态即将开始（真源 250ms 轮询会跟上）
        DismissBootSplash();
    }
}

void DengYuSkinDisplay::ClearChatMessages() {
    if (!IsSetupUICalled()) {
        return;
    }
    DisplayLockGuard lock(this);
    if (!lock) { return; }  // fail-closed
    StopTypewriter();
    if (sub_label_ != nullptr && round_screen_) {
        lv_label_set_text(sub_label_, "");
    }
    if (flow_ != nullptr) {
        lv_obj_clean(flow_);
    }
    EnterDengYuState(DENGYU_STATE_IDLE);
}

void DengYuSkinDisplay::ShowNotification(const char* notification, int duration_ms) {
    if (!IsSetupUICalled() || notification == nullptr) {
        return;
    }
    // 断连/恢复嗅探：先清再嗅（"已连接"/"连接成功"会命中恢复关键词）
    if (strstr(notification, "已连接") != nullptr || strstr(notification, "连接成功") != nullptr ||
        strstr(notification, "Connected") != nullptr) {
        DisplayLockGuard lock(this);
        if (!lock) { return; }
        error_latch_ = false;
        if (dengyu_state_ == DENGYU_STATE_ERROR) {
            EnterDengYuState(DENGYU_STATE_IDLE);
            ShowStatusLine("回来啦", kSage, 3);
        }
    }
    if (strstr(notification, "断开") != nullptr || strstr(notification, "断连") != nullptr ||
        strstr(notification, "重连") != nullptr || strstr(notification, "网络") != nullptr ||
        strstr(notification, "offline") != nullptr || strstr(notification, "disconnect") != nullptr) {
        DisplayLockGuard lock(this);
        if (!lock) { return; }
        error_latch_ = true;
        if (dengyu_state_ != DENGYU_STATE_MORNING) {
            EnterDengYuState(DENGYU_STATE_ERROR);
        }
    }
    // 其余沿用基类（配网/升级卡片、连接成功回落）
    YhSkinDisplay::ShowNotification(notification, duration_ms);
}

void DengYuSkinDisplay::ShowNotification(const std::string& notification, int duration_ms) {
    ShowNotification(notification.c_str(), duration_ms);
}

// ---------------- 按键 / 彩蛋 ----------------

void DengYuSkinDisplay::HandleKeyEvent(int ev) {
    if (!IsSetupUICalled()) {
        return;
    }
    auto state = Application::GetInstance().GetDeviceState();

    switch (ev) {
        case 0:  // 短按：进入聆听（板级已 ToggleChatState；这里落即时预置）
            if (state == kDeviceStateIdle || state == kDeviceStateSpeaking) {
                DisplayLockGuard lock(this);
                if (!lock) { return; }  // fail-closed
                EnterDengYuState(DENGYU_STATE_LISTENING);
            }
            break;
        case 1:  // 双击：待机轮换光萤配色（NVS 记忆）
            if (state == kDeviceStateIdle) {
                NextEasterEgg();
            }
            break;
        case 2:  // 长按：静音切换提示（语义同基类，文案灯语化）
            if (state == kDeviceStateIdle) {
                DisplayLockGuard lock(this);
                if (!lock) { return; }  // fail-closed
                auto codec = Board::GetInstance().GetAudioCodec();
                bool muted = (codec != nullptr && codec->output_volume() == 0);
                ShowStatusLine(muted ? "已静音" : "声音开着", kCream, 3);
            } else if (state == kDeviceStateListening) {
                DisplayLockGuard lock(this);
                if (!lock) { return; }  // fail-closed
                ShowStatusLine("我在呢", kSage, 3);
            }
            break;
        default:
            break;
    }
}

void DengYuSkinDisplay::NextEasterEgg() {
    DisplayLockGuard lock(this);
    if (!lock) { return; }  // fail-closed
    palette_ = static_cast<dengyu_palette_t>((palette_ + 1) % DENGYU_PALETTE_MAX);
    SavePalette();
    if (orb_ != nullptr) {
        dengyu_orb_set_palette(orb_, dengyu_orb_colors(palette_));
    }
    if (mini_orb_ != nullptr) {
        dengyu_orb_set_palette(mini_orb_, dengyu_orb_colors(palette_));
    }
    char text[48];
    snprintf(text, sizeof(text), "光萤换成了%s", dengyu_palette_name(palette_));
    ShowStatusLine(text, kCream, 3);
}

// ---------------- 1s 节拍 ----------------

void DengYuSkinDisplay::Tick1s() {
    if (!IsSetupUICalled()) {
        return;
    }
    tick_count_++;

    // 晨间卡片倒计时 + 时钟刷新
    if (morning_until_tick_ >= 0) {
        if (tick_count_ >= morning_until_tick_) {
            DisplayLockGuard lock(this);
            if (!lock) { return; }  // fail-closed
            ExitMorning();
        } else {
            DisplayLockGuard lock(this);
            if (!lock) { return; }  // fail-closed
            UpdateMorningClock();
        }
    }

    // 状态短语 ttl 到期隐藏
    if (status_until_tick_ > 0 && tick_count_ >= status_until_tick_) {
        DisplayLockGuard lock(this);
        if (!lock) { return; }  // fail-closed
        HideStatusLine();
    }

    // 待机短句轮播（4.2s）
    if (dengyu_state_ == DENGYU_STATE_IDLE && tick_count_ - last_idle_word_tick_ >= 4) {
        last_idle_word_tick_ = tick_count_;
        DisplayLockGuard lock(this);
        if (!lock) { return; }  // fail-closed
        RotateIdleWord();
    }

    // 思考轮词（2.4s，状态短语位轮换）
    if (dengyu_state_ == DENGYU_STATE_THINKING && (tick_count_ % 2) == 0) {
        DisplayLockGuard lock(this);
        if (!lock) { return; }  // fail-closed
        think_word_idx_ = (think_word_idx_ + 1) % kThinkWordsCount;
        ShowStatusLine(kThinkWords[think_word_idx_], kEmber300);
    }

    // 整分钟：晨间入口 + 陪伴天数触碰
    if (tick_count_ % 60 == 0) {
        TryEnterMorning();
        TouchCompanionDays();
    }

    // 基类节拍（时间刷新 → 回调本类 SetStatus；早晚问候走 emoji 路径，
    // 光语下不可见，属可接受损耗——基类状态栏时间位已隐藏）
    YhSkinDisplay::Tick1s();
}

// ---------------- NVS（Settings 栈式 RAII，非单例）----------------

void DengYuSkinDisplay::LoadPalette() {
    Settings settings("dengyu", false);
    int32_t v = settings.GetInt("palette", DENGYU_PALETTE_EMBER);
    if (v < 0 || v >= DENGYU_PALETTE_MAX) {
        v = DENGYU_PALETTE_EMBER;
    }
    palette_ = static_cast<dengyu_palette_t>(v);
    if (orb_ != nullptr) {
        dengyu_orb_set_palette(orb_, dengyu_orb_colors(palette_));
    }
    if (mini_orb_ != nullptr) {
        dengyu_orb_set_palette(mini_orb_, dengyu_orb_colors(palette_));
    }
}

void DengYuSkinDisplay::SavePalette() {
    Settings settings("dengyu", true);
    settings.SetInt("palette", static_cast<int32_t>(palette_));
}

void DengYuSkinDisplay::LoadCompanionDays() {
    Settings settings("dengyu", false);
    companion_days_ = settings.GetInt("days", 0);
    if (companion_days_ < 0) {
        companion_days_ = 0;
    }
}

void DengYuSkinDisplay::TouchCompanionDays() {
    time_t now = time(nullptr);
    struct tm tmv;
    localtime_r(&now, &tmv);
    if (tmv.tm_year < 2025 - 1900) {
        return;  // 时间未同步，别把 1970 算进去
    }
    if (last_sync_day_ == tmv.tm_mday) {
        return;  // 当天已记
    }
    last_sync_day_ = tmv.tm_mday;
    companion_days_++;
    Settings settings("dengyu", true);
    settings.SetInt("days", companion_days_);
    if (companion_days_ > 1) {
        ESP_LOGI(TAG, "companion days: %ld", static_cast<long>(companion_days_));
    }
}

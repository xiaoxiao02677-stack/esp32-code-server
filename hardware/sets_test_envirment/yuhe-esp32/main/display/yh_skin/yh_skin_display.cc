#include "yh_skin_display.h"

#include "application.h"
#include "assets/lang_config.h"
#include "board.h"
#include "system_info.h"
#include "wallpaper/wallpaper_manager.h"
#include "yh_skin_boot.h"
#include "yh_skin_cards.h"

#include <esp_app_desc.h>
#include <esp_log.h>
#include <noto_emoji.h>

#include <cstdio>
#include <cstring>
#include <ctime>
#include <memory>
#include <string>
#include <utility>
#include <vector>

// 屿禾「小柚」皮肤：1:1 迁移自 small_secreen 的 my-s3-tft RoundScreenDisplay，
// 并补上两块原实现没有的能力：
//   1) 开机首帧接管（SetupUI 里先画品牌画面，原生 UI 一帧都不出现）；
//   2) 系统态卡片（配网/激活码/升级/错误），不再把长文本塞进 200x50 气泡。

#define TAG "YhSkin"

namespace {

// 气泡文本上限（按 UTF-8 码点计）。72 是防御性上限：180px 宽 2 行约 18 汉字，
// 超出部分被气泡裁切（不会画到气泡外），与基准行为一致；本常量的真正职责是
// 保证截断**绝不切半个码点**。
constexpr size_t kBubbleMaxCodepoints = 72;

size_t Utf8SeqLen(unsigned char lead) {
    if ((lead & 0x80u) == 0x00u) return 1;
    if ((lead & 0xE0u) == 0xC0u) return 2;
    if ((lead & 0xF0u) == 0xE0u) return 3;
    if ((lead & 0xF8u) == 0xF0u) return 4;
    return 1;
}

size_t Utf8ByteOffset(const char* s, size_t len, size_t n) {
    size_t pos = 0, count = 0;
    while (pos < len && count < n) {
        size_t seq = Utf8SeqLen(static_cast<unsigned char>(s[pos]));
        if (seq > len - pos) {
            break;  // 尾部残缺序列
        }
        pos += seq;
        ++count;
    }
    return pos;
}

std::string TruncateUtf8(const char* text, size_t max_codepoints) {
    if (text == nullptr || max_codepoints == 0) {
        return std::string();
    }
    size_t len = strlen(text);
    if (Utf8ByteOffset(text, len, max_codepoints) >= len) {
        return std::string(text, len);
    }
    std::string out(text, Utf8ByteOffset(text, len, max_codepoints - 1));
    out += "…";
    return out;
}

bool Contains(const char* haystack, const char* needle) {
    return haystack != nullptr && needle != nullptr && strstr(haystack, needle) != nullptr;
}

// 从一段文字里抽出 6 位连续数字（激活码）。找不到返回空串。
std::string ExtractSixDigits(const char* text) {
    if (text == nullptr) {
        return std::string();
    }
    int run = 0;
    const char* start = nullptr;
    for (const char* p = text; *p != '\0'; ++p) {
        if (*p >= '0' && *p <= '9') {
            if (run == 0) {
                start = p;
            }
            if (++run == 6) {
                return std::string(start, 6);
            }
        } else {
            run = 0;
        }
    }
    return std::string();
}

// 提取百分比（"67%" / "升级中 67%"）。找不到返回 -1。
int ExtractPercent(const char* text) {
    if (text == nullptr) {
        return -1;
    }
    for (const char* p = text; *p != '\0'; ++p) {
        if (*p >= '0' && *p <= '9') {
            int value = 0;
            const char* q = p;
            while (*q >= '0' && *q <= '9' && value < 1000) {
                value = value * 10 + (*q - '0');
                ++q;
            }
            if (*q == '%' && value >= 0 && value <= 100) {
                return value;
            }
            p = q - 1;
        }
    }
    return -1;
}

// 开机时 Application::Initialize 会把 SystemInfo::GetUserAgent() 当 system 消息
// 打进消息区（原生态的「机型+版本」串）。皮肤里必须丢掉它，否则品牌画面下方
// 会立刻出现一行 "yh-154tft-wifi/2.5.1"，正是用户要求去掉的观感。
//
// ★ 真实格式是 BOARD_NAME "/" version（system_info.cc: GetUserAgent），
//   即 "yh-154tft-wifi/2.5.1"，**不是** 空格分隔。早期只认 "ESP32"/空格分隔，
//   结果开机 430ms 就把 UA 当普通消息塞进气泡，并顺带 DismissSplash()，
//   品牌画面只活 430ms（R2 失效）。这里必须同时认 '/' 与 ' ' 两种分隔，
//   且要求分隔符后是纯「数字+点」版本号，避免误伤正常中文消息。
bool LooksLikeUserAgent(const char* content) {
    if (content == nullptr) {
        return false;
    }
    if (Contains(content, "ESP32") || Contains(content, "yuhe") || Contains(content, "Yuhe")) {
        return true;
    }
    const size_t len = strlen(content);
    if (len == 0 || len >= 48) {
        return false;
    }
    // 取最后一个 '/'；若同时存在空格且空格更靠右，则以空格为分隔
    const char* sep = strrchr(content, '/');
    const char* space = strrchr(content, ' ');
    if (space != nullptr && (sep == nullptr || space > sep)) {
        sep = space;
    }
    if (sep == nullptr || sep == content) {
        return false;
    }
    const char* ver = sep + 1;
    if (ver[0] < '0' || ver[0] > '9') {
        return false;
    }
    bool has_dot = false;
    bool in_suffix = false;
    for (const char* p = ver; *p != '\0'; ++p) {
        const char c = *p;
        if (!in_suffix && c == '.') {
            has_dot = true;
            continue;
        }
        if (c >= '0' && c <= '9') {
            continue;
        }
        // 预发布/构建后缀：2.5.1-rc1、2.5.1+build7
        if (!in_suffix && (c == '-' || c == '+')) {
            in_suffix = true;
            continue;
        }
        if (in_suffix && ((c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z') || c == '.' ||
                          c == '-' || c == '+')) {
            continue;
        }
        return false;
    }
    return has_dot;
}

// ---------------- 字体退休池 ----------------
//
// 背景（一次真实的循环重启现场）：
//   Assets::LvglStrategy::Apply() 加载 assets 里的 common 字体后调
//   Display::SetTextFont()，LvglDisplay::SetTextFont() 会把主题里的
//   shared_ptr 换成新字体，函数末尾对旧 shared_ptr 做 reset() → 旧对象析构。
//   而 LVGL 的样式只存裸 const lv_font_t*，只要有一个控件没被重绑，它就
//   握着一个已经 free() 的地址。
//
//   崩溃现场正好抓到了铁证：
//     EXCVADDR = 0x0、PC = 0x0（跳到 0 执行）、A12 = 0x5c0f（'小'）、
//     A7 = 0x67da（'柚'）—— 正在对字符串「小柚」取字形，
//     A8 落在 lv_font.c:112 即 f->get_glyph_dsc(...) 那条 callx，
//     A0 落在 lv_font_get_glyph_width（lv_font.c:163）。
//   第一个字就崩，说明 font 从一开头就是死的；而 lv_font_t 的
//   get_glyph_dsc 正好在偏移 0，堆块被 free() 后首字被写成空闲链表
//   的 next 指针（0）→ 于是 callx0 0 → InstrFetchProhibited。
//
// 对策（两道，都很便宜）：
//   ① 退休池：换下来的字体对象永不释放。一个 lv_font_t 才几十字节，
//      真正的大数组在 flash/PSRAM 里不归它管；一辈子只换一次字体，
//      留着是成本最低、最不可能再出错的做法。
//   ② 全树改绑：把整棵对象树里"还指着退休字体"的控件统一改绑到新字体。
//      这一步不依赖任何句柄 —— 开机画面、高温弹窗、基类占位族、将来
//      新加的控件全都被覆盖，不会因为"忘了重绑某个 g_xxx"再崩一次。

std::vector<std::shared_ptr<LvglFont>>& RetiredFontOwners() {
    static std::vector<std::shared_ptr<LvglFont>> owners;
    return owners;
}

std::vector<const lv_font_t*>& RetiredFontPtrs() {
    static std::vector<const lv_font_t*> ptrs;
    return ptrs;
}

// 把 theme 上当前挂着的文本字体收进退休池，并返回其裸指针。
const lv_font_t* RetireThemeTextFont(LvglTheme* theme) {
    if (theme == nullptr || theme->text_font() == nullptr) {
        return nullptr;
    }
    const lv_font_t* raw = theme->text_font()->font();
    if (raw == nullptr) {
        return nullptr;
    }
    for (auto* existing : RetiredFontPtrs()) {
        if (existing == raw) {
            return raw;  // 已经在池子里，别重复收
        }
    }
    RetiredFontOwners().push_back(theme->text_font());
    RetiredFontPtrs().push_back(raw);
    return raw;
}

bool IsRetiredFont(const lv_font_t* font) {
    if (font == nullptr) {
        return false;
    }
    for (auto* retired : RetiredFontPtrs()) {
        if (retired == font) {
            return true;
        }
    }
    return false;
}

struct RebindFontCtx {
    const lv_font_t* replacement = nullptr;
    int rebound = 0;
};

lv_obj_tree_walk_res_t RebindStaleFontCb(lv_obj_t* obj, void* user_data) {
    auto* ctx = static_cast<RebindFontCtx*>(user_data);
    if (obj == nullptr || ctx == nullptr || ctx->replacement == nullptr) {
        return LV_OBJ_TREE_WALK_NEXT;
    }
    // get_style 取的是"实际会用来渲染的"字体（含继承），所以父容器把旧字体
    // 传给子控件的情况也能被抓到。图标字体/emoji 字体不在池子里，不会被误改。
    const lv_font_t* current = lv_obj_get_style_text_font(obj, LV_PART_MAIN);
    if (IsRetiredFont(current)) {
        lv_obj_set_style_text_font(obj, ctx->replacement, LV_PART_MAIN);
        ++ctx->rebound;
    }
    return LV_OBJ_TREE_WALK_NEXT;
}

// 覆盖四个根：活动屏幕 + top/sys/bottom 三个图层。
void RebindStaleFontsEverywhere(const lv_font_t* replacement, int* out_rebound = nullptr) {
    if (replacement == nullptr) {
        return;
    }
    RebindFontCtx ctx;
    ctx.replacement = replacement;
    lv_obj_t* roots[] = {lv_screen_active(), lv_layer_top(), lv_layer_sys(), lv_layer_bottom()};
    for (auto* root : roots) {
        if (root != nullptr) {
            lv_obj_tree_walk(root, RebindStaleFontCb, &ctx);
        }
    }
    if (ctx.rebound > 0) {
        ESP_LOGI(TAG, "Rebound %d widget(s) off a retired text font", ctx.rebound);
    }
    if (out_rebound != nullptr) {
        *out_rebound = ctx.rebound;
    }
}

}  // namespace

YhSkinDisplay::YhSkinDisplay(esp_lcd_panel_io_handle_t panel_io, esp_lcd_panel_handle_t panel,
                             int width, int height, int offset_x, int offset_y, bool mirror_x,
                             bool mirror_y, bool swap_xy, const YhSkinProfile& profile)
    : SpiLcdDisplay(panel_io, panel, width, height, offset_x, offset_y, mirror_x, mirror_y,
                    swap_xy),
      profile_(profile) {}

YhSkinFonts YhSkinDisplay::CurrentFonts() const {
    YhSkinFonts fonts;
    auto* theme = static_cast<LvglTheme*>(current_theme_);
    if (theme == nullptr) {
        return fonts;
    }
    if (theme->text_font() != nullptr) {
        fonts.text = theme->text_font()->font();
    }
    if (theme->icon_font() != nullptr) {
        fonts.icon = theme->icon_font()->font();
    }
    if (theme->large_icon_font() != nullptr) {
        fonts.large = theme->large_icon_font()->font();
    }
    if (theme->emoji_font() != nullptr) {
        fonts.emoji = theme->emoji_font()->font();
    }
    return fonts;
}

void YhSkinDisplay::SetupUI() {
    if (setup_ui_called_) {
        return;
    }
    // ★ 开机版本戳：这一行能让串口日志自证"跑的是哪一次构建"。
    //   本项目反复出现"改了代码、烧了固件、但现象没变"的情况，而唯一的
    //   判据是某条日志文案有没有变 —— 没有版本戳时只能靠反汇编地址去猜，
    //   猜错一次就要多排查一轮。加这一行以后，对不上就先怀疑烧写。
    ESP_LOGI(TAG, "yh_skin build %s %s", __DATE__, __TIME__);
    // 只调用 Display::SetupUI()（仅置标志位），跳过 LcdDisplay::SetupUI 的原生布局：
    // 状态栏/聊天区/机器人 logo 一旦建出来就会在开机瞬间闪一帧，正是要避免的。
    //
    // ★ 顺序：先拿锁，再置标志位。
    //   若先 Display::SetupUI()（它把 setup_ui_called_ 置 true）再拿锁、拿不到就
    //   return，就会留下"标志说界面已建好、实际一个对象都没有"的半状态 ——
    //   之后所有 SetChatMessage/SetStatus 都会 deref 空句柄。反过来写，
    //   拿不到锁时什么都没改，下次调用还能重试。
    DisplayLockGuard lock(this);
    if (!lock) { return; }  // fail-closed：拿不到 LVGL 锁就不碰对象树
    Display::SetupUI();

    BuildMainScreen();
    AttachHiddenPlaceholders();

    // ★ boot 壁纸 flash 早期恢复（联网前、splash 建立前）：
    //   splash 是 boot 壁纸的唯一展示面，而它马上就要建了 —— 必须在这里把
    //   flash 里的图读进 boot 槽，ShowBootSplash 才有图可用。同步读 115KB
    //   + MD5 约 50ms，开机阶段可接受（此时屏幕还没亮任何东西）。
    //   无图 / 校验失败 / 分区不适用 → nullptr，splash 回落 idle 壁纸/品牌
    //   底纹，联网后走网络重拉（旧行为，不变）。
    //   幂等：重复 SetupUI（主题切换重建）时槽里已有图，函数内部直接回指针。
    WallpaperManager::GetInstance().EarlyRestoreBootWallpaper();

    // 首帧即品牌画面：此时 Application 还会继续做音频/网络初始化，
    // splash 会一直盖着，直到首次进入待机（见 DismissSplashIfNeeded）。
    // 走虚分发：子类皮肤（像素宠物 PetSkinDisplay）覆写 ShowBootSplash()
    // 即可换掉开机画面，不必复制整个 SetupUI。
    ShowBootSplash();
}

void YhSkinDisplay::BuildMainScreen() {
    auto screen = lv_screen_active();
    auto fonts = CurrentFonts();

    // 屏幕级底色：背景图加载异常时的兜底（与基准一致的深紫渐变）
    lv_obj_set_style_bg_color(screen, lv_color_hex(kColorBgTop), 0);
    lv_obj_set_style_bg_grad_color(screen, lv_color_hex(kColorBgBottom), 0);
    lv_obj_set_style_bg_grad_dir(screen, LV_GRAD_DIR_VER, 0);

    // 背景图用 lv_image 对象而不是 bg_image_src：
    // 后者无法缩放，320x240 / 240x320 屏上会留出大片底色。
    bg_image_ = lv_image_create(screen);
    lv_image_set_src(bg_image_, &yh_skin_bg);
    lv_obj_remove_flag(bg_image_, LV_OBJ_FLAG_CLICKABLE);
    int scale = 256 * profile_.long_side() / 240;
    if (scale > 256) {
        lv_image_set_scale(bg_image_, static_cast<uint32_t>(scale));
    }
    lv_obj_align(bg_image_, LV_ALIGN_CENTER, 0, 0);
    lv_obj_move_background(bg_image_);

    // ---- 顶部：时间 y=10 / 电量 y=28（基准坐标，按 profile 等比缩放）----
    time_label_ = lv_label_create(screen);
    lv_label_set_text(time_label_, "--:--");
    if (fonts.text != nullptr) {
        lv_obj_set_style_text_font(time_label_, fonts.text, 0);
    }
    lv_obj_set_style_text_color(time_label_, lv_color_hex(kColorTextSub), 0);
    lv_obj_align(time_label_, LV_ALIGN_TOP_MID, 0, profile_.scaled(10));

    battery_text_ = lv_label_create(screen);
    lv_label_set_text(battery_text_, "");
    if (fonts.text != nullptr) {
        lv_obj_set_style_text_font(battery_text_, fonts.text, 0);
    }
    lv_obj_set_style_text_color(battery_text_, lv_color_hex(kColorTextSub), 0);
    lv_obj_align(battery_text_, LV_ALIGN_TOP_MID, 0, profile_.scaled(28));
    if (!profile_.has_battery) {
        // 无电池检测的板子（yh-n16r8-st7789）永远不会有电量数据，直接隐藏
        lv_obj_add_flag(battery_text_, LV_OBJ_FLAG_HIDDEN);
    }

    // ---- 中心：表情头像 y=-15 ----
    // emoji_label_/emoji_image_ 必须挂在同一个容器里：LcdDisplay::SetEmotion
    // 直接操作这两个成员，容器只负责定位与裁切。
    const int avatar = profile_.scaled(120);
    avatar_box_ = lv_obj_create(screen);
    lv_obj_set_size(avatar_box_, avatar, avatar);
    lv_obj_align(avatar_box_, LV_ALIGN_CENTER, 0, -profile_.scaled(15));
    lv_obj_set_style_bg_opa(avatar_box_, LV_OPA_TRANSP, 0);
    lv_obj_set_style_border_width(avatar_box_, 0, 0);
    lv_obj_set_style_radius(avatar_box_, 0, 0);
    lv_obj_set_style_pad_all(avatar_box_, 0, 0);
    lv_obj_remove_flag(avatar_box_, LV_OBJ_FLAG_SCROLLABLE);

    emoji_label_ = lv_label_create(avatar_box_);
    if (fonts.emoji != nullptr) {
        lv_obj_set_style_text_font(emoji_label_, fonts.emoji, 0);
    }
    lv_obj_set_style_text_color(emoji_label_, lv_color_hex(kColorTextMain), 0);
    lv_label_set_text(emoji_label_, noto_emoji_get_utf8("neutral"));
    lv_obj_center(emoji_label_);

    emoji_image_ = lv_image_create(avatar_box_);
    lv_obj_center(emoji_image_);
    lv_obj_add_flag(emoji_image_, LV_OBJ_FLAG_HIDDEN);

    // ---- 气泡：底部居中 y=-55，基准 200x50 / 圆角 16 / 粉色边框 ----
    bubble_ = lv_obj_create(screen);
    lv_obj_set_size(bubble_, profile_.scaled(200), profile_.scaled(50));
    lv_obj_align(bubble_, LV_ALIGN_BOTTOM_MID, 0, -profile_.scaled(55));
    lv_obj_set_style_bg_color(bubble_, lv_color_hex(kColorBubbleBg), 0);
    lv_obj_set_style_bg_opa(bubble_, LV_OPA_80, 0);
    lv_obj_set_style_radius(bubble_, profile_.scaled(16), 0);
    lv_obj_set_style_border_width(bubble_, 1, 0);
    lv_obj_set_style_border_color(bubble_, lv_color_hex(kColorPrimary), 0);
    lv_obj_set_style_pad_all(bubble_, profile_.scaled(4), 0);
    lv_obj_remove_flag(bubble_, LV_OBJ_FLAG_SCROLLABLE);

    bubble_label_ = lv_label_create(bubble_);
    lv_label_set_text(bubble_label_, "我在呢");
    lv_obj_set_width(bubble_label_, profile_.scaled(180));
    lv_label_set_long_mode(bubble_label_, LV_LABEL_LONG_WRAP);
    lv_obj_set_style_text_align(bubble_label_, LV_TEXT_ALIGN_CENTER, 0);
    if (fonts.text != nullptr) {
        lv_obj_set_style_text_font(bubble_label_, fonts.text, 0);
    }
    lv_obj_set_style_text_color(bubble_label_, lv_color_hex(kColorTextMain), 0);
    lv_obj_center(bubble_label_);

    // ---- 底部提示 y=-18（基准 y=-12 贴圆边会被裁，这是基准里的 D5 修复）----
    hint_label_ = lv_label_create(screen);
    lv_label_set_text(hint_label_, "短按说话  长按菜单");
    if (fonts.text != nullptr) {
        lv_obj_set_style_text_font(hint_label_, fonts.text, 0);
    }
    lv_obj_set_style_text_color(hint_label_, lv_color_hex(kColorTextHint), 0);
    lv_obj_align(hint_label_, LV_ALIGN_BOTTOM_MID, 0,
                 profile_.round ? -profile_.scaled(18) : -profile_.scaled(12));
}

void YhSkinDisplay::AttachHiddenPlaceholders() {
    // 基类（LcdDisplay::SetTheme / LvglDisplay::SetStatus/ShowNotification）会
    // 无条件解引用这些成员，且部分路径只判空不全判。皮肤完全接管布局后它们
    // 不再有视觉意义，但必须存在 —— 否则就是 2026-10-08 那次
    // 「Refreshing display theme 后 InstrFetchProhibited」崩溃循环。
    auto screen = lv_screen_active();
    auto fonts = CurrentFonts();

    container_ = lv_obj_create(screen);
    lv_obj_set_size(container_, 1, 1);
    lv_obj_add_flag(container_, LV_OBJ_FLAG_HIDDEN);
    lv_obj_set_style_bg_opa(container_, LV_OPA_TRANSP, 0);
    lv_obj_set_style_border_width(container_, 0, 0);

    auto make_hidden_label = [&](const lv_font_t* font) {
        lv_obj_t* label = lv_label_create(container_);
        if (font != nullptr) {
            lv_obj_set_style_text_font(label, font, 0);
        }
        lv_label_set_text(label, "");
        lv_obj_add_flag(label, LV_OBJ_FLAG_HIDDEN);
        return label;
    };

    network_label_ = make_hidden_label(fonts.icon);
    mute_label_ = make_hidden_label(fonts.icon);
    battery_label_ = make_hidden_label(fonts.icon);
    status_label_ = make_hidden_label(fonts.text);
    notification_label_ = make_hidden_label(fonts.text);

    low_battery_popup_ = lv_obj_create(container_);
    lv_obj_set_size(low_battery_popup_, 1, 1);
    lv_obj_add_flag(low_battery_popup_, LV_OBJ_FLAG_HIDDEN);
    lv_obj_set_style_bg_opa(low_battery_popup_, LV_OPA_TRANSP, 0);
    lv_obj_set_style_border_width(low_battery_popup_, 0, 0);
    low_battery_label_ = lv_label_create(low_battery_popup_);
    lv_label_set_text(low_battery_label_, "");
    if (fonts.text != nullptr) {
        lv_obj_set_style_text_font(low_battery_label_, fonts.text, 0);
    }

    // content_ / chat_message_label_ 独立占位：不能指向气泡，否则基类任何
    // 「清空消息列表」的路径都会把气泡拆掉（基准踩过这个坑）。
    content_ = lv_obj_create(container_);
    lv_obj_set_size(content_, 1, 1);
    lv_obj_add_flag(content_, LV_OBJ_FLAG_HIDDEN);
    lv_obj_set_style_bg_opa(content_, LV_OPA_TRANSP, 0);
    lv_obj_set_style_border_width(content_, 0, 0);
    chat_message_label_ = make_hidden_label(fonts.text);

    preview_image_ = lv_image_create(screen);
    lv_obj_set_size(preview_image_, profile_.width / 2, profile_.height / 2);
    lv_obj_align(preview_image_, LV_ALIGN_CENTER, 0, 0);
    lv_obj_add_flag(preview_image_, LV_OBJ_FLAG_HIDDEN);

    // ★ 收尾必须补一次 ApplyBackground()。
    //   bg_image_ 上面是按 yh_skin_bg 硬编码建的，而 user_wallpaper_ 可能在
    //   UI 建好之前就被 SetWallpaper() 写进来了（开机 device_config / NVS 恢复
    //   都早于或紧跟 SetupUI），那份壁纸会被这里的硬编码 src 覆盖掉，之后
    //   没有任何路径会再画它 —— 配合 wallpaper 侧"已应用"的记账，就是
    //   「屏幕永远是默认底纹，重下发还被 already applied 挡回」。
    //   放在最后调，是为了让 bg_image_ 已经存在、缩放/对齐都按最终状态算。
    ApplyBackground();
}

// ---------------- 开机画面 ----------------

void YhSkinDisplay::ShowBootSplash() {
    if (!setup_ui_called_) {
        return;
    }
    DisplayLockGuard lock(this);
    if (!lock) { return; }  // fail-closed：拿不到 LVGL 锁就不碰对象树
    yh_skin::SplashInfo info;
    info.brand = "琳琳";
    info.subtitle = "AI 陪伴助手";
    info.version = esp_app_get_description()->version;
    // 开机底图回落链：boot 壁纸 > idle 壁纸（指针只读不接管）。
    // 全空时 SplashInfo::background 为 nullptr，splash 内部回落 yh_skin_bg。
    // ★ flash 早期恢复的图在 WallpaperManager boot 槽里（SetupUI 里刚调过
    //   EarlyRestoreBootWallpaper），boot_wallpaper_ 成员此刻还是空 ——
    //   主动拉一次。已应用过的会话里两者相同，取成员优先（少一次锁）。
    const lv_img_dsc_t* boot_image = boot_wallpaper_;
    if (boot_image == nullptr) {
        boot_image = WallpaperManager::GetInstance().EarlyRestoreBootWallpaper();
    }
    info.background = boot_image != nullptr ? boot_image : user_wallpaper_;
    yh_skin::BuildSplash(lv_screen_active(), profile_, CurrentFonts(), info);
}

void YhSkinDisplay::DismissBootSplash() {
    DisplayLockGuard lock(this);
    if (!lock) { return; }  // fail-closed：拿不到 LVGL 锁就不碰对象树
    yh_skin::DismissSplash();
}

void YhSkinDisplay::DismissSplashIfNeeded() {
    // 「进待机」= 基类状态栏刷新出 HH:MM，或收到真实对话内容。
    // 两个信号任一出现就说明开机流程走完了，可以交还主界面。
    // DismissSplash() 自带 g_root/g_dismissing 幂等判断，这里不必再判一次。
    DisplayLockGuard lock(this);
    if (!lock) { return; }  // fail-closed：拿不到 LVGL 锁就不碰对象树
    yh_skin::DismissSplash();
}

// ---------------- 协议层钩子 ----------------

void YhSkinDisplay::SetBubbleText(const char* text) {
    if (bubble_label_ == nullptr || text == nullptr) {
        return;
    }
    // ★ 自己拿锁：这是共享层里少数几个"公开给内部随便调"的裸原语。
    //   现在所有调用点都在别人已持锁的临界区里（递归锁，重复加锁安全），
    //   但它是将来新代码最容易被无锁调用的入口 —— 一旦有第二个任务在这里
    //   lv_label_set_text，就会和 taskLVGL 并发 push 事件，把 event_head
    //   写成自环（详见 DisplayLockGuard 里的说明）。锁放在这里，比在每个
    //   调用点各写一遍可靠。
    DisplayLockGuard lock(this);
    if (!lock) { return; }  // fail-closed：拿不到 LVGL 锁就不碰对象树
    lv_label_set_text(bubble_label_, text);
}

void YhSkinDisplay::SetStatus(const char* status) {
    if (!setup_ui_called_ || status == nullptr) {
        return;
    }
    if (yh_skin::SplashAbsorbsStatus(status)) {
        // 开机噪声（待机/初始化/连接中）不进气泡：splash 上已有专属状态行
        DisplayLockGuard lock(this);
        if (!lock) { return; }  // fail-closed：拿不到 LVGL 锁就不碰对象树
        yh_skin::SetSplashStatus(status);
        return;
    }
    DisplayLockGuard lock(this);
    if (!lock) { return; }  // fail-closed：拿不到 LVGL 锁就不碰对象树

    // 纯时间格式（5 字符 "HH:MM"）→ 顶部时间位；同时说明已进待机
    if (strlen(status) == 5 && status[2] == ':') {
        if (time_label_ != nullptr) {
            lv_label_set_text(time_label_, status);
        }
        DismissSplashIfNeeded();
        return;
    }
    if (bubble_label_ != nullptr) {
        lv_label_set_text(bubble_label_, status);
    }
}

void YhSkinDisplay::SetEmotion(const char* emotion) {
    if (!setup_ui_called_ || emotion == nullptr) {
        return;
    }
    // 彩蛋展示期间不覆盖（10 秒后自动恢复）
    if (easter_egg_until_tick_ > tick_count_) {
        return;
    }
    // 完全复用基类的资产/emoji 渲染（协议名 -> emoji 图 / noto emoji 字符）
    LcdDisplay::SetEmotion(emotion);
}

void YhSkinDisplay::SetChatMessage(const char* role, const char* content) {
    if (!setup_ui_called_) {
        ESP_LOGW(TAG, "SetChatMessage('%s','%s') before SetupUI", role ? role : "",
                 content ? content : "");
        return;
    }
    if (content == nullptr || content[0] == '\0') {
        DisplayLockGuard lock(this);
        if (!lock) { return; }  // fail-closed：拿不到 LVGL 锁就不碰对象树
        yh_skin::HideCards();
        SetBubbleText("我在呢");
        return;
    }
    bool is_system = (role != nullptr && strcmp(role, "system") == 0);
    if (is_system && LooksLikeUserAgent(content)) {
        ESP_LOGI(TAG, "Drop native user-agent banner: %s", content);
        return;
    }

    // 激活码：6 位数字 + 说明文字 → 大字卡片（原生态是塞进 14px 消息区）
    std::string code = is_system ? ExtractSixDigits(content) : std::string();
    if (is_system && !code.empty()) {
        DisplayLockGuard lock(this);
        if (!lock) { return; }  // fail-closed：拿不到 LVGL 锁就不碰对象树
        yh_skin::ShowActivationCard(lv_screen_active(), profile_, CurrentFonts(), code, content);
        // 激活是开机流程的一部分，不是「流程走完」：同样不收开机画面
        return;
    }

    DisplayLockGuard lock(this);
    if (!lock) { return; }  // fail-closed：拿不到 LVGL 锁就不碰对象树
    yh_skin::HideCards();
    std::string text = TruncateUtf8(content, kBubbleMaxCodepoints);
    SetBubbleText(text.c_str());
    // ★ 只有真实对话内容才允许收开机画面。
    //   system 角色是设备自报状态（UA 串、错误提示、公告…），把它当成
    //   「开机流程走完」的信号太脆弱：UA 一旦换个格式漏判，品牌画面就只活
    //   几百毫秒（实测 430ms），并且会在动画进行到一半时删掉整屏对象。
    if (!is_system) {
        DismissSplashIfNeeded();
    }
}

void YhSkinDisplay::ClearChatMessages() {
    if (!setup_ui_called_) {
        return;
    }
    DisplayLockGuard lock(this);
    if (!lock) { return; }  // fail-closed：拿不到 LVGL 锁就不碰对象树
    yh_skin::HideCards();
    // 不调基类实现：它会 lv_obj_clean(content_)，那是 1x1 占位对象，
    // 清理本身无害，但语义上会让气泡与消息区脱节；这里直接复位气泡。
    SetBubbleText("我在呢");
}

void YhSkinDisplay::ShowNotification(const char* notification, int duration_ms) {
    (void)duration_ms;  // 气泡常驻，由下一次 SetStatus/SetChatMessage 自然覆盖
    if (!setup_ui_called_ || notification == nullptr) {
        return;
    }

    // 连接成功必须先处理：「已连接 WiFi」同时命中下面的 WiFi 关键词，
    // 若不提前拦截，配网卡片会在联网成功后永久驻留，直到下一次空消息才被收走。
    if (Contains(notification, "已连接") || Contains(notification, "连接成功") ||
        Contains(notification, "Connected")) {
        DisplayLockGuard lock(this);
        if (!lock) { return; }  // fail-closed：拿不到 LVGL 锁就不碰对象树
        yh_skin::HideCards();
        std::string text = TruncateUtf8(notification, kBubbleMaxCodepoints);
        if (bubble_label_ != nullptr) {
            lv_label_set_text(bubble_label_, text.c_str());
        }
        return;
    }

    // 配网模式：SSID/密码/入口地址这类长文本塞进 200x50 气泡读不全 → 走卡片
    if (Contains(notification, "配网") || Contains(notification, "热点") ||
        Contains(notification, "Wi-Fi") || Contains(notification, "WiFi")) {
        DisplayLockGuard lock(this);
        if (!lock) { return; }  // fail-closed：拿不到 LVGL 锁就不碰对象树
        // splash 仍是全屏不透明容器，卡片会被它盖住；先把开机画面收掉，
        // 避免两个全屏容器在同一片屏幕上叠着互相干扰。
        yh_skin::DismissSplash();
        yh_skin::WifiCardInfo info;
        info.hint = notification;
        yh_skin::ShowWifiCard(lv_screen_active(), profile_, CurrentFonts(), info);
        return;
    }
    // 升级：有百分比就画进度条
    if (Contains(notification, "升级") || Contains(notification, "更新") ||
        Contains(notification, "OTA")) {
        DisplayLockGuard lock(this);
        if (!lock) { return; }  // fail-closed：拿不到 LVGL 锁就不碰对象树
        yh_skin::DismissSplash();
        yh_skin::ShowProgressCard(lv_screen_active(), profile_, CurrentFonts(), "正在升级",
                                  notification, ExtractPercent(notification));
        return;
    }

    DisplayLockGuard lock(this);
    if (!lock) { return; }  // fail-closed：拿不到 LVGL 锁就不碰对象树
    // 其余通知落气泡（比原生态的顶部状态栏更显眼）。
    // 先收起可能驻留的系统卡片：新通知到达即视为旧卡片已被取代，
    // 否则配网/升级卡片会一直盖在主界面上。
    yh_skin::HideCards();
    std::string text = TruncateUtf8(notification, kBubbleMaxCodepoints);
    if (bubble_label_ != nullptr) {
        lv_label_set_text(bubble_label_, text.c_str());
    }
}

void YhSkinDisplay::ShowNotification(const std::string& notification, int duration_ms) {
    ShowNotification(notification.c_str(), duration_ms);
}

void YhSkinDisplay::SetTheme(Theme* theme) {
    // 先调基类（内部加锁，重绑基类占位 label 的样式与配色）。
    LcdDisplay::SetTheme(theme);

    DisplayLockGuard lock(this);
    if (!lock) { return; }  // fail-closed：拿不到 LVGL 锁就不碰对象树
    // 卡片用皮肤自己的配色与底纹，不随主题重排，也不在 ApplyFonts() 的重绑
    // 范围内 —— 留着只会与主界面观感割裂。切主题时直接丢弃，下次需要再建。
    yh_skin::DropCardsImmediately();
    ApplyFonts();
    ApplyBackground();
}

bool YhSkinDisplay::SetTextFont(std::shared_ptr<LvglFont> text_font) {
    // 旧字体"退休池"：故意永不释放。
    //   LvglBuiltInFont 把 lv_font_t 按值存在自己身上（lvgl_font.h:15/20），
    //   而 LVGL 的样式只存裸指针；基类 SetTextFont 换掉 shared_ptr 之后会
    //   对旧指针 reset()，旧对象立刻析构，没被重绑的控件当场变悬垂 ——
    //   这正是 InstrFetchProhibited / EXCVADDR=0x0 / PC=0x0 那一轮的成因。
    //   必须在调基类之前把旧字体收进池子，因为基类返回时对象已经死了。
    auto& theme_manager = LvglThemeManager::GetInstance();
    RetireThemeTextFont(theme_manager.GetTheme("light"));
    RetireThemeTextFont(theme_manager.GetTheme("dark"));

    return LvglDisplay::SetTextFont(std::move(text_font));
}

void YhSkinDisplay::ApplyFonts() {
    auto fonts = CurrentFonts();
    auto apply = [](lv_obj_t* obj, const lv_font_t* font) {
        if (obj != nullptr && font != nullptr) {
            lv_obj_set_style_text_font(obj, font, 0);
        }
    };
    apply(time_label_, fonts.text);
    apply(battery_text_, fonts.text);
    apply(hint_label_, fonts.text);
    apply(bubble_label_, fonts.text);
    apply(emoji_label_, fonts.emoji);
    // 基类占位族里带文字的这几个也要重绑：它们是按旧字体建的，
    // 旧字体对象一旦退休（见 SetTextFont），不留神就会留下悬垂裸指针。
    apply(status_label_, fonts.text);
    apply(notification_label_, fonts.text);
    apply(low_battery_label_, fonts.text);
    apply(chat_message_label_, fonts.text);

    // ★ 开机画面也要重绑。
    //   SetupUI() 跑在 application.cc:169，assets 的 common 字体要到
    //   CheckAssetsVersion()（application.cc:534 附近）才加载，所以 splash
    //   建的时候用的还是编译进固件的 basic（890 字）。不在这里补一次，
    //   品牌名「小柚」的「柚」就永远是方框，而气泡/卡片却是好的 ——
    //   正是"有些字乱、有些字正常"的来源。
    yh_skin::SetSplashFont(fonts.text);

    // ★ 兜底全树改绑：上面这些是"我们知道句柄"的控件，但对象树里还有
    //   别人建的（基类 lcd_display 的、本板高温弹窗 high_temp_label_ 的、
    //   以后新加的）。它们的字体是 assets 加载前建的，一旦旧字体退休就是
    //   悬垂裸指针 —— 高温弹窗虽然 HIDDEN，layout_update_core 照样递归进去，
    //   一取字形就崩。这一步按"当前实际渲染字体是否已退休"判定，不依赖句柄。
    RebindStaleFontsEverywhere(fonts.text);
}

bool YhSkinDisplay::ApplyBackground() {
    const lv_img_dsc_t* image = nullptr;

    if (user_wallpaper_ != nullptr) {
        image = user_wallpaper_;
    } else {
        auto* theme = static_cast<LvglTheme*>(current_theme_);
        if (theme != nullptr && theme->background_image() != nullptr) {
            image = theme->background_image()->image_dsc();
        } else {
            image = &yh_skin_bg;
        }
    }
    if (image == nullptr || bg_image_ == nullptr) {
        // UI 还没建 / 图像不可用：什么都没改，如实告诉调用方
        return false;
    }
    if (!BindBackgroundImage(image)) {
        return false;
    }
    // splash 还盖在屏上时同步换它的底图：壁纸通常在开机阶段（splash 亮着、
    // 还没进待机）被下发，SetWallpaper 成功走完这里，让用户壁纸立刻上屏，
    // 而不是只换掉被盖住的背景、等下次开机才看到。ShowBootSplash 重建场景
    // 传的 background 也是同一条回落链，两条路殊途同归。
    ApplySplashBackground();
    return true;
}

// 已持锁调用：把指定图绑到主界面 bg_image_（set_src + 回读确认 + 等比缩放
// + 显式标脏）。ApplyBackground 的正常回落链与 SetBootWallpaper 的"splash
// 已收起"兜底共用。返回 false = lv_image_set_src 被拒（UI 未建/图无效）。
bool YhSkinDisplay::BindBackgroundImage(const lv_img_dsc_t* image) {
    if (image == nullptr || bg_image_ == nullptr) {
        return false;
    }
    lv_image_set_src(bg_image_, image);
    // LVGL 会在 set_src 里做解码校验，失败时保留旧 src 并打日志。
    // 用 get_src 回读确认"真的换过去了"，这是 SetWallpaper 返回值的唯一依据 ——
    // 没有这一步，'已应用' 就只能靠猜，而猜错的代价是之后永远跳过。
    if (lv_image_get_src(bg_image_) != static_cast<const void*>(image)) {
        ESP_LOGE(TAG, "BindBackgroundImage: lv_image_set_src rejected %p (src=%p)",
                 (const void*)image, lv_image_get_src(bg_image_));
        return false;
    }
    // 用户壁纸尺寸由服务端下发，按短边等比放大到刚好铺满
    int scale = 256;
    if (image->header.w > 0) {
        int need = 256 * profile_.long_side() / image->header.w;
        if (need > 256) {
            scale = need;
        }
    }
    lv_image_set_scale(bg_image_, static_cast<uint32_t>(scale));
    lv_obj_align(bg_image_, LV_ALIGN_CENTER, 0, 0);
    lv_obj_move_background(bg_image_);
    // 显式标脏：VARIABLE 的 set_src 每次都重读 header 并 invalidate
    // （lv_image.c 的 VARIABLE 分支，同指针也不短路；只有 FILE/SYMBOL 会比指针）。
    // 这里保留是为了防御将来版本对同 src 做短路优化，并覆盖"同一个 &dsc 地址
    // 换了内容后重绑"这种情况 —— 没有它就可能出现"调了 SetWallpaper 但一帧没重画"。
    lv_obj_invalidate(bg_image_);
    return true;
}

bool YhSkinDisplay::ApplySplashBackground() {
    // splash 底图回落链：boot 壁纸 > idle 壁纸 > 品牌底纹（nullptr 由
    // UpdateSplashBackground 内部回落 yh_skin_bg）。
    // 未设 boot 壁纸的设备沿用 idle 壁纸打底 —— 与旧版开机行为一致。
    const lv_img_dsc_t* splash_bg = boot_wallpaper_ != nullptr ? boot_wallpaper_
                                                               : user_wallpaper_;
    // splash 不存在时 UpdateSplashBackground 静默空转（无法上屏）。
    // 这里没法直接探测 g_root（模块内部状态），用 SplashVisible() 判断；
    // splash 已淡出时换底图无意义，直接算成功（屏幕上已没有它）。
    if (!yh_skin::SplashVisible()) {
        return true;
    }
    yh_skin::UpdateSplashBackground(splash_bg);
    return true;
}

bool YhSkinDisplay::SetBootWallpaper(const lv_img_dsc_t* image) {
    // 镜像 SetWallpaper 的"零残留失败"协议：所有 return false 路径不改任何成员。
    // boot 槽只影响 splash 底图，UI 未建时 splash 同样不存在，只需记下指针？
    // 不 —— 记指针而 splash 不存在同样会造成"假成功"，让 applied_version 记账
    // 之后同版本被 already applied 挡回。但与 idle 槽不同：splash 是 SetupUI
    // 最后一个建的（BuildMainScreen 之后），UI 未建 ⇒ splash 必不存在 ⇒ 拒收。
    if (image == nullptr) {
        // 等价于"恢复开机默认底图"
        if (!setup_ui_called_) {
            boot_wallpaper_ = nullptr;
            return false;
        }
        DisplayLockGuard lock(this);
        if (!lock) { return false; }
        boot_wallpaper_ = nullptr;
        ApplySplashBackground();
        return true;
    }
    if (!setup_ui_called_) {
        ESP_LOGW(TAG, "SetBootWallpaper called before SetupUI, rejected");
        return false;
    }
    DisplayLockGuard lock(this);
    if (!lock) { return false; }
    boot_wallpaper_ = image;
    // splash 已淡出后再设 boot 壁纸：屏幕上已没有开机画面可换。
    // 老行为是"只缓存指针等下次开机"，用户看到的就是"下发了、成功了、
    // 屏幕毫无变化"。兜底：idle 槽没有自己的壁纸时，把 boot 图投到主界面
    // 背景作为可见反馈；idle 槽有图时保持 idle 图（用户显式设置的待机
    // 壁纸优先级更高，boot 图只等下次开机展示）。
    if (!yh_skin::SplashVisible() && user_wallpaper_ == nullptr && bg_image_ != nullptr) {
        ESP_LOGI(TAG, "SetBootWallpaper: splash gone, mirroring to background as feedback");
        if (!BindBackgroundImage(image)) {
            // ★ 零残留失败协议：绑定被拒必须回滚成员——调用方（ApplyToDisplay）
            //   会据此回滚并释放新 buffer，若 boot_wallpaper_ 还指着它就是悬垂。
            boot_wallpaper_ = nullptr;
            return false;
        }
        return true;
    }
    ApplySplashBackground();
    return true;
}

bool YhSkinDisplay::ClearBootWallpaper() {
    if (!setup_ui_called_) {
        boot_wallpaper_ = nullptr;  // 还没有 UI 可重绘，只清状态
        return true;
    }
    DisplayLockGuard lock(this);
    if (!lock) { return false; }
    // ★ 镜像兜底的解绑义务：splash 收起后到达的 boot 图曾被镜像到主界面背景
    //   （见 SetBootWallpaper）。此刻若 bg_image_ 还绑着它（idle 槽无图、
    //   src 指向 boot_wallpaper_），必须先解绑再让调用方 free —— 否则渲染
    //   线程下一帧就读已释放的 PSRAM。boot_wallpaper_ 尚未置空时比对才有效，
    //   顺序不能反。
    const bool mirrored = (user_wallpaper_ == nullptr && bg_image_ != nullptr &&
                           boot_wallpaper_ != nullptr &&
                           lv_image_get_src(bg_image_) == static_cast<const void*>(boot_wallpaper_));
    boot_wallpaper_ = nullptr;
    if (mirrored) {
        ApplyBackground();  // idle 槽无图 → 主题背景 / good.jpg
    }
    ApplySplashBackground();
    return true;
}

bool YhSkinDisplay::SetWallpaper(const lv_img_dsc_t* image) {
    // ★ 失败路径必须"零残留"：三个 return false 之前都不改任何成员。
    //   反过来说，先说 user_wallpaper_ = image 再判锁/判 UI，会留下一个致命组合：
    //   调用方以为"没生效"于是回滚并 free(new_buffer)，而 bg_image_ 已经指向新图、
    //   user_wallpaper_ 也还记着它 —— 下一帧拿一块已释放的 PSRAM 去渲染。
    if (image == nullptr) {
        // 等价于"恢复默认背景"
        if (!setup_ui_called_) {
            user_wallpaper_ = nullptr;
            return false;
        }
        DisplayLockGuard lock(this);
        if (!lock) { return false; }  // fail-closed：拿不到 LVGL 锁就不碰对象树
        user_wallpaper_ = nullptr;
        ApplyBackground();
        return true;
    }
    if (!setup_ui_called_) {
        // UI 还没建（bg_image_ 不存在）。不接：让调用方回 fail 并重试，
        // 而不是"记下指针假装成功"——那正是以前循环跳过的源头。
        ESP_LOGW(TAG, "SetWallpaper called before SetupUI, rejected");
        return false;
    }
    DisplayLockGuard lock(this);
    if (!lock) { return false; }  // fail-closed：拿不到 LVGL 锁就不碰对象树
    const lv_img_dsc_t* previous = user_wallpaper_;
    user_wallpaper_ = image;
    if (!ApplyBackground()) {
        // ApplyBackground 自己没有改 src（或已回滚），这里把成员一起还原，
        // 保证调用方 reset dsc/buffer 时显示层已经不再引用它。
        user_wallpaper_ = previous;
        ESP_LOGW(TAG, "SetWallpaper: lv_image_set_src rejected, rolled back");
        return false;
    }
    return true;
}

bool YhSkinDisplay::ClearWallpaper() {
    if (!setup_ui_called_) {
        user_wallpaper_ = nullptr;  // 还没有 UI 可重绘，只清状态
        return true;
    }
    DisplayLockGuard lock(this);
    // 拿不到锁就"什么都不改"并如实返回 false：先清成员再判锁，会出现"状态说已清空、
    // bg_image_ 还指着旧图"的不一致，而调用方紧接着就会把 dsc/buffer 清掉 → 悬空源。
    if (!lock) { return false; }
    user_wallpaper_ = nullptr;
    ApplyBackground();
    return true;
}

void YhSkinDisplay::SetHideSubtitle(bool hide) {
    subtitle_hidden_ = hide;
    if (!setup_ui_called_ || bubble_ == nullptr) {
        return;
    }
    DisplayLockGuard lock(this);
    if (!lock) { return; }  // fail-closed：拿不到 LVGL 锁就不碰对象树
    if (hide) {
        lv_obj_add_flag(bubble_, LV_OBJ_FLAG_HIDDEN);
    } else {
        lv_obj_remove_flag(bubble_, LV_OBJ_FLAG_HIDDEN);
    }
}

void YhSkinDisplay::UpdateStatusBar(bool update_all) {
    // 基类节拍负责时间（会回调我们覆写的 SetStatus → 落到顶部时间位）
    LvglDisplay::UpdateStatusBar(update_all);

    if (!profile_.has_battery || battery_text_ == nullptr) {
        return;
    }
    auto& board = Board::GetInstance();
    int battery_level = 0;
    bool charging = false;
    bool discharging = false;
    if (!board.GetBatteryLevel(battery_level, charging, discharging)) {
        return;
    }
    bool low_battery = false;
    {
        DisplayLockGuard lock(this);
        if (!lock) { return; }  // fail-closed：拿不到 LVGL 锁就不碰对象树
        char buf[24];
        if (charging) {
            // 不用 ⚡ 符号：内置 font_noto_sans_basic 没有该字形，会显示成方框
            snprintf(buf, sizeof(buf), "充电%d%%", battery_level);
        } else {
            snprintf(buf, sizeof(buf), "%d%%", battery_level);
        }
        lv_label_set_text(battery_text_, buf);

        // 低电量提醒：只在电量跳变时提示一次，避免每分钟刷屏
        if (!charging && battery_level <= 15 && battery_level != last_bat_percent_) {
            SetBubbleText("我有点饿了，快充电");
            low_battery = true;
        }
        last_bat_percent_ = battery_level;
    }
    // SetEmotion 内部自己加锁，必须放在锁作用域之外调用，否则死锁
    if (low_battery) {
        LcdDisplay::SetEmotion("sad");
    }
}

// ---------------- 单 BOOT 键三事件（皮肤层反馈）----------------

void YhSkinDisplay::HandleKeyEvent(int ev) {
    if (!setup_ui_called_) {
        return;
    }
    auto state = Application::GetInstance().GetDeviceState();

    switch (ev) {
        case 0:  // 短按
            if (state == kDeviceStateIdle || state == kDeviceStateSpeaking) {
                // Application::ToggleChatState() 已由板级回调处理，这里只做视觉预置
                LcdDisplay::SetEmotion("laughing");
                DisplayLockGuard lock(this);
                if (!lock) { return; }  // fail-closed：拿不到 LVGL 锁就不碰对象树
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
            if (state == kDeviceStateIdle) {
                auto codec = Board::GetInstance().GetAudioCodec();
                bool muted = (codec != nullptr && codec->output_volume() == 0);
                LcdDisplay::SetEmotion(muted ? "sad" : "cool");
                DisplayLockGuard lock(this);
                if (!lock) { return; }  // fail-closed：拿不到 LVGL 锁就不碰对象树
                SetBubbleText(muted ? "已静音" : "声音开启啦");
            } else if (state == kDeviceStateListening) {
                LcdDisplay::SetEmotion("neutral");
                DisplayLockGuard lock(this);
                if (!lock) { return; }  // fail-closed：拿不到 LVGL 锁就不碰对象树
                SetBubbleText("我在呢");
            }
            break;
        default:
            break;
    }
}

void YhSkinDisplay::NextEasterEgg() {
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
    DisplayLockGuard lock(this);
    if (!lock) { return; }  // fail-closed：拿不到 LVGL 锁就不碰对象树
    SetBubbleText(eggs[egg_index_].text);
    easter_egg_until_tick_ = tick_count_ + 10;  // 10 秒后恢复协议驱动表情
}

void YhSkinDisplay::Tick1s() {
    if (!setup_ui_called_) {
        return;
    }
    tick_count_++;

    // 彩蛋超时恢复
    if (easter_egg_until_tick_ > 0 && tick_count_ >= easter_egg_until_tick_) {
        easter_egg_until_tick_ = -1;
        if (Application::GetInstance().GetDeviceState() == kDeviceStateIdle) {
            // 锁必须在 SetEmotion 之前：本函数由 esp_timer 每秒回调，
            // 不在 LVGL 任务上下文，裸调 lv_* 会与 LVGL 任务并发破坏对象树。
            DisplayLockGuard lock(this);
            if (!lock) { return; }  // fail-closed：拿不到 LVGL 锁就不碰对象树
            LcdDisplay::SetEmotion("neutral");
            SetBubbleText("我在呢");
        }
    }

    // 自动问候只在待机和整分钟触发
    if (Application::GetInstance().GetDeviceState() != kDeviceStateIdle) {
        return;
    }
    if (tick_count_ % 60 != 0) {
        return;
    }
    time_t now = time(nullptr);
    struct tm* tm_now = localtime(&now);
    if (tm_now == nullptr || tm_now->tm_year < 2025 - 1900) {
        return;  // 时间未同步，别用 1970 瞎问候
    }
    static int last_behavior_min = -1;
    int cur_min = tm_now->tm_hour * 60 + tm_now->tm_min;
    if (cur_min == last_behavior_min) {
        return;
    }
    if (cur_min == 23 * 60 + 30) {
        last_behavior_min = cur_min;
        DisplayLockGuard lock(this);
        if (!lock) { return; }  // fail-closed：拿不到 LVGL 锁就不碰对象树
        LcdDisplay::SetEmotion("sleepy");
        SetBubbleText("该睡啦，别熬夜");
    } else if (cur_min == 7 * 60) {
        last_behavior_min = cur_min;
        LcdDisplay::SetEmotion("happy");
        DisplayLockGuard lock(this);
        if (!lock) { return; }  // fail-closed：拿不到 LVGL 锁就不碰对象树
        SetBubbleText("早呀宝宝，今天也要加油");
    }
}

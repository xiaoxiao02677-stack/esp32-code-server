#include "yh_skin_cards.h"

#include <cstdio>
#include <cstring>

// splash 专用小字体（286 码位，覆盖本卡片全部固定文案 + lang_config 状态串）：
// 卡片出现得极早（扫描 Wi-Fi 在开机最早期，assets 的 common 档要到激活完成
// 后 assets.Apply() 才加载），此时 fonts.text 还是 basic 档（890 字）——
// 「密/码/页/面…」不在其中。文字一律走回落链：主题 text 字体 → 本字体。
// ★ 绝不能用 fonts.large 渲染文字：它是 Material Symbols 图标字体
//   （U+E000–F8FF 私用区），拿它渲染「配网模式」四个字 100% 全方框
//   （与 yh_skin_boot.cc 品牌名字体是同一个坑，只是换了张卡片）。
extern const lv_font_t font_splash_20_4;

// 系统态卡片：把「配网 / 激活码 / 升级 / 错误」四类信息从 14px 状态栏搬到全屏浮层。
//
// 为什么是「一个容器 + 清空重建内容」而不是四套独立对象：
//   四张卡不会同时出现，共用外壳可以把 LVGL 对象数压到最低（ESP32-S3 上每个
//   对象都要吃 LVGL 堆），也天然保证「重复调用只更新内容」的幂等性——
//   每次 Show* 只 lv_obj_clean(body) 后重加 label，不会堆积。

#define TAG "YhSkinCards"

namespace yh_skin {
namespace {

constexpr uint32_t kPrimary = 0xFF7AA2;
constexpr uint32_t kCardBg = 0x3A2440;
constexpr uint32_t kTextMain = 0xFFF7FB;
constexpr uint32_t kTextSub = 0xC9B8D9;
constexpr uint32_t kTextHint = 0x8B7A99;
constexpr uint32_t kErrorRed = 0xFF6B6B;

lv_obj_t* g_root = nullptr;   // 全屏遮罩
lv_obj_t* g_card = nullptr;   // 卡片本体
lv_obj_t* g_title = nullptr;  // 标题
lv_obj_t* g_body = nullptr;   // 正文容器（每次清空重建）
bool g_hiding = false;

YhSkinProfile g_profile;
YhSkinFonts g_fonts;

void Font(lv_obj_t* obj, const lv_font_t* font) {
    if (obj != nullptr && font != nullptr) {
        lv_obj_set_style_text_font(obj, font, 0);
    }
}

// 文字字体回落链：主题 text 字体（common 档）→ splash 专用字体（basic 阶段兜底）。
// 主题字体在 assets 加载前是 basic 档（890 字），缺卡片文案里的多个常用字；
// splash 字体编译进固件、开机即可用。
const lv_font_t* TextFont() {
    return g_fonts.text != nullptr ? g_fonts.text : &font_splash_20_4;
}

// 按文字内容选字体：主题 text 字体缺任何一个字形（basic 档场景）就整体回落
// splash 字体。逐字符混排两种字体会导致行高/基线跳动，宁可整行同字体。
// hint/标题等短文案逐字符探测成本可忽略（<100 码点）。
const lv_font_t* TextFontFor(const char* text) {
    const lv_font_t* primary = TextFont();
    if (text == nullptr || primary == nullptr || primary == &font_splash_20_4) {
        return primary;
    }
    lv_font_glyph_dsc_t dsc;
    const unsigned char* p = reinterpret_cast<const unsigned char*>(text);
    while (*p != '\0') {
        uint32_t cp = 0;
        int seq = 1;
        if ((*p & 0x80u) == 0x00u) {
            cp = *p;
        } else if ((*p & 0xE0u) == 0xC0u) {
            cp = *p & 0x1Fu; seq = 2;
        } else if ((*p & 0xF0u) == 0xE0u) {
            cp = *p & 0x0Fu; seq = 3;
        } else if ((*p & 0xF8u) == 0xF0u) {
            cp = *p & 0x07u; seq = 4;
        }
        for (int i = 1; i < seq && p[i] != '\0'; ++i) {
            cp = (cp << 6) | (p[i] & 0x3Fu);
        }
        // ASCII 与中文都查；图标私用区（E000-F8FF）不会出现在文字文案里
        if (!lv_font_get_glyph_dsc(primary, &dsc, cp, 0)) {
            return &font_splash_20_4;  // 主题字体缺这个字 → 整行回落
        }
        p += seq;
    }
    return primary;
}

// 按 UTF-8 码点截断，绝不在多字节序列中间下刀（否则汉字变乱码方块）
std::string TruncateUtf8(const char* text, size_t max_codepoints) {
    if (text == nullptr) {
        return std::string();
    }
    size_t len = strlen(text);
    size_t pos = 0;
    size_t count = 0;
    while (pos < len && count < max_codepoints) {
        unsigned char lead = static_cast<unsigned char>(text[pos]);
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
        if (seq > len - pos) {
            break;  // 尾部残缺序列，直接丢
        }
        pos += seq;
        ++count;
    }
    if (pos >= len) {
        return std::string(text, len);
    }
    std::string out(text, pos);
    out += "…";
    return out;
}

void EnsureCard(lv_obj_t* parent, const YhSkinProfile& profile, const YhSkinFonts& fonts) {
    g_profile = profile;
    g_fonts = fonts;
    g_hiding = false;

    // 句柄自检：屏幕重建/父容器更换后，静态句柄可能已失效或挂到了别的父节点上。
    // 不校验就把这种句柄交给 lv_anim_set_var，等于把悬垂指针灌进动画系统。
    if (g_root != nullptr && (!lv_obj_is_valid(g_root) || lv_obj_get_parent(g_root) != parent)) {
        lv_obj_t* stale = g_root;
        g_root = nullptr;
        g_card = nullptr;
        g_title = nullptr;
        g_body = nullptr;
        if (lv_obj_is_valid(stale)) {
            lv_anim_delete(stale, nullptr);  // 先撤掉可能还在飞的淡出动画（含其回调）
            lv_obj_delete_async(stale);
        }
    }

    if (g_root != nullptr) {
        // 已存在：只按新 profile 重排尺寸（旋转屏切换时会走到这里）
        lv_obj_set_size(g_root, profile.width, profile.height);
        lv_obj_set_size(g_card, profile.short_side() * 86 / 100, LV_SIZE_CONTENT);
        lv_obj_align(g_card, LV_ALIGN_CENTER, 0, 0);
        return;
    }
    if (parent == nullptr) {
        return;
    }

    g_root = lv_obj_create(parent);
    lv_obj_remove_flag(g_root, LV_OBJ_FLAG_SCROLLABLE);
    lv_obj_add_flag(g_root, LV_OBJ_FLAG_IGNORE_LAYOUT);
    lv_obj_set_size(g_root, profile.width, profile.height);
    lv_obj_set_pos(g_root, 0, 0);
    lv_obj_set_style_radius(g_root, 0, 0);
    lv_obj_set_style_border_width(g_root, 0, 0);
    lv_obj_set_style_pad_all(g_root, 0, 0);
    lv_obj_set_style_bg_color(g_root, lv_color_black(), 0);
    lv_obj_set_style_bg_opa(g_root, LV_OPA_60, 0);
    lv_obj_move_foreground(g_root);

    g_card = lv_obj_create(g_root);
    lv_obj_remove_flag(g_card, LV_OBJ_FLAG_SCROLLABLE);
    lv_obj_set_size(g_card, profile.short_side() * 86 / 100, LV_SIZE_CONTENT);
    lv_obj_align(g_card, LV_ALIGN_CENTER, 0, 0);
    lv_obj_set_style_radius(g_card, profile.scaled(18), 0);
    lv_obj_set_style_border_width(g_card, 1, 0);
    lv_obj_set_style_border_color(g_card, lv_color_hex(kPrimary), 0);
    lv_obj_set_style_bg_color(g_card, lv_color_hex(kCardBg), 0);
    lv_obj_set_style_bg_opa(g_card, LV_OPA_COVER, 0);
    lv_obj_set_style_pad_all(g_card, profile.scaled(14), 0);
    lv_obj_set_style_pad_row(g_card, profile.scaled(6), 0);
    lv_obj_set_flex_flow(g_card, LV_FLEX_FLOW_COLUMN);
    lv_obj_set_flex_align(g_card, LV_FLEX_ALIGN_CENTER, LV_FLEX_ALIGN_CENTER,
                          LV_FLEX_ALIGN_CENTER);

    g_title = lv_label_create(g_card);
    lv_obj_set_style_text_color(g_title, lv_color_hex(kTextMain), 0);
    // 标题是中文（配网模式/设备激活/正在升级/出错了）——必须走文字回落链，
    // fonts.large 是图标字体（见文件头注释）。此处先给基准字体，ResetContent
    // 设置标题文案时会按内容重新探测（basic 阶段自动落 splash 字体）。
    Font(g_title, TextFont());

    g_body = lv_obj_create(g_card);
    lv_obj_remove_flag(g_body, LV_OBJ_FLAG_SCROLLABLE);
    lv_obj_set_width(g_body, LV_PCT(100));
    lv_obj_set_height(g_body, LV_SIZE_CONTENT);
    lv_obj_set_style_bg_opa(g_body, LV_OPA_TRANSP, 0);
    lv_obj_set_style_border_width(g_body, 0, 0);
    lv_obj_set_style_pad_all(g_body, 0, 0);
    lv_obj_set_style_pad_row(g_body, profile.scaled(4), 0);
    lv_obj_set_flex_flow(g_body, LV_FLEX_FLOW_COLUMN);
    lv_obj_set_flex_align(g_body, LV_FLEX_ALIGN_CENTER, LV_FLEX_ALIGN_CENTER,
                          LV_FLEX_ALIGN_CENTER);
}

void ResetContent(const char* title, uint32_t title_color) {
    if (g_title != nullptr) {
        lv_label_set_text(g_title, title != nullptr ? title : "");
        // 标题按内容选字体：basic 阶段主题字体缺「了/出」等字，自动回落 splash
        Font(g_title, TextFontFor(g_title == nullptr ? nullptr : lv_label_get_text(g_title)));
        lv_obj_set_style_text_color(g_title, lv_color_hex(title_color), 0);
    }
    if (g_body != nullptr) {
        lv_obj_clean(g_body);  // 清空旧内容，防止连续调用堆积对象
    }
}

lv_obj_t* AddLine(const char* text, const lv_font_t* font, uint32_t color, bool wrap) {
    if (g_body == nullptr) {
        return nullptr;
    }
    lv_obj_t* label = lv_label_create(g_body);
    lv_label_set_text(label, text != nullptr ? text : "");
    Font(label, font);
    lv_obj_set_style_text_color(label, lv_color_hex(color), 0);
    lv_obj_set_style_text_align(label, LV_TEXT_ALIGN_CENTER, 0);
    if (wrap) {
        lv_obj_set_width(label, LV_PCT(100));
        lv_label_set_long_mode(label, LV_LABEL_LONG_WRAP);
    }
    return label;
}

}  // namespace

void ShowWifiCard(lv_obj_t* parent, const YhSkinProfile& profile, const YhSkinFonts& fonts,
                  const WifiCardInfo& info) {
    EnsureCard(parent, profile, fonts);
    if (g_root == nullptr) {
        return;
    }
    ResetContent("配网模式", kTextMain);

    if (!info.ssid.empty()) {
        char buf[96];
        snprintf(buf, sizeof(buf), "热点：%s", info.ssid.c_str());
        AddLine(buf, TextFontFor(buf), kTextMain, true);
    }
    if (!info.password.empty()) {
        char buf[96];
        snprintf(buf, sizeof(buf), "密码：%s", info.password.c_str());
        AddLine(buf, TextFontFor(buf), kTextMain, true);
    }
    if (!info.hint.empty()) {
        AddLine(info.hint.c_str(), TextFontFor(info.hint.c_str()), kTextHint, true);
    }
    if (info.ssid.empty() && info.password.empty() && info.hint.empty()) {
        // 没有具体参数时给一条可操作的兜底提示，而不是一张空卡
        AddLine("请用手机连接设备热点后打开配网页面", TextFontFor("请用手机连接设备热点后打开配网页面"), kTextSub, true);
    }
}

void ShowActivationCard(lv_obj_t* parent, const YhSkinProfile& profile, const YhSkinFonts& fonts,
                        const std::string& code, const std::string& message) {
    EnsureCard(parent, profile, fonts);
    if (g_root == nullptr) {
        return;
    }
    ResetContent("设备激活", kTextMain);

    if (!code.empty() && code.size() <= 8) {
        // 逐位显示：6 位码在小屏上必须一眼能读，等宽排布 + 大字
        lv_obj_t* row = lv_obj_create(g_body);
        lv_obj_remove_flag(row, LV_OBJ_FLAG_SCROLLABLE);
        lv_obj_set_size(row, LV_PCT(100), LV_SIZE_CONTENT);
        lv_obj_set_style_bg_opa(row, LV_OPA_TRANSP, 0);
        lv_obj_set_style_border_width(row, 0, 0);
        lv_obj_set_style_pad_all(row, 0, 0);
        lv_obj_set_style_pad_column(row, profile.scaled(6), 0);
        lv_obj_set_flex_flow(row, LV_FLEX_FLOW_ROW);
        lv_obj_set_flex_align(row, LV_FLEX_ALIGN_CENTER, LV_FLEX_ALIGN_CENTER,
                              LV_FLEX_ALIGN_CENTER);
        for (char c : code) {
            char digit[2] = {c, '\0'};
            lv_obj_t* d = lv_label_create(row);
            lv_label_set_text(d, digit);
            // 激活码是数字但图标字体不含可读 ASCII 字形，同样走文字回落链
            Font(d, TextFont());
            lv_obj_set_style_text_color(d, lv_color_hex(kPrimary), 0);
        }
    } else if (!code.empty()) {
        AddLine(code.c_str(), TextFontFor(code.c_str()), kPrimary, true);
    }

    if (!message.empty()) {
        AddLine(message.c_str(), TextFontFor(message.c_str()), kTextSub, true);
    }
}

void ShowProgressCard(lv_obj_t* parent, const YhSkinProfile& profile, const YhSkinFonts& fonts,
                      const char* title, const char* detail, int percent) {
    EnsureCard(parent, profile, fonts);
    if (g_root == nullptr) {
        return;
    }
    ResetContent((title != nullptr && title[0] != '\0') ? title : "正在升级", kTextMain);

    if (detail != nullptr && detail[0] != '\0') {
        AddLine(detail, TextFontFor(detail), kTextSub, true);
    }
    if (percent < 0) {
        AddLine("请稍候…", TextFontFor("请稍候…"), kTextHint, false);
        return;
    }
    if (percent > 100) {
        percent = 100;
    }
    char buf[16];
    snprintf(buf, sizeof(buf), "%d%%", percent);
    // 百分比数字同样不能走图标字体（文件头注释）
    AddLine(buf, TextFont(), kPrimary, false);

    lv_obj_t* bar = lv_bar_create(g_body);
    lv_obj_set_size(bar, profile.short_side() * 6 / 10, profile.scaled(6));
    lv_obj_set_style_radius(bar, profile.scaled(3), 0);
    lv_obj_set_style_bg_color(bar, lv_color_hex(0x241830), 0);
    lv_obj_set_style_bg_opa(bar, LV_OPA_COVER, 0);
    lv_obj_set_style_bg_color(bar, lv_color_hex(kPrimary), LV_PART_INDICATOR);
    lv_bar_set_range(bar, 0, 100);
    lv_bar_set_value(bar, percent, LV_ANIM_OFF);
}

void ShowErrorCard(lv_obj_t* parent, const YhSkinProfile& profile, const YhSkinFonts& fonts,
                   const char* title, const char* detail) {
    EnsureCard(parent, profile, fonts);
    if (g_root == nullptr) {
        return;
    }
    ResetContent((title != nullptr && title[0] != '\0') ? title : "出错了", kErrorRed);
    // 错误详情可能很长（HTTP 状态+URL），限 90 码点，超长补省略号
    std::string text = TruncateUtf8(detail, 90);
    if (!text.empty()) {
        AddLine(text.c_str(), TextFontFor(text.c_str()), kTextSub, true);
    }
}

void HideCards() {
    if (g_root == nullptr || g_hiding) {
        return;
    }
    g_hiding = true;

    // 先置空指针再删对象：淡出期间若有新的 Show* 调用会走 EnsureCard 重建，
    // 不会拿到一个正在被删的句柄。
    lv_obj_t* root = g_root;
    g_root = nullptr;
    g_card = nullptr;
    g_title = nullptr;
    g_body = nullptr;

    lv_anim_t a;
    lv_anim_init(&a);
    lv_anim_set_var(&a, root);
    // 目标对象随动画携带，回调只认自己这一个句柄（期间可能已 EnsureCard 建了新卡）
    lv_anim_set_user_data(&a, root);
    lv_anim_set_exec_cb(&a, [](void* var, int32_t value) {
        lv_obj_set_style_opa(static_cast<lv_obj_t*>(var), static_cast<lv_opa_t>(value), 0);
    });
    lv_anim_set_values(&a, LV_OPA_COVER, LV_OPA_TRANSP);
    lv_anim_set_duration(&a, 200);
    // ★ 绝不在 completed_cb 里同步删除对象。
    //   lv_anim.c:700 调用本回调，返回后还要访问该 lv_anim_t（line 708 lv_free）。
    //   若此时同步 lv_obj_del，lv_obj_destructor 会对子对象逐个 lv_anim_delete，
    //   把 anim_timer 正在遍历的链表和 obj_delete_core 的事件栈一起破坏 ——
    //   实测崩在 lv_event_mark_deleted（LoadProhibited / EXCVADDR=0x14）并重启循环。
    //   改走 lv_obj_delete_async：删除动作落到独立 async timer 里执行。
    lv_anim_set_completed_cb(&a, [](lv_anim_t* anim) {
        auto* obj = static_cast<lv_obj_t*>(lv_anim_get_user_data(anim));
        if (obj != nullptr && lv_obj_is_valid(obj)) {
            lv_obj_delete_async(obj);
        }
    });
    lv_anim_start(&a);
}

void DropCardsImmediately() {
    lv_obj_t* root = g_root;
    g_root = nullptr;
    g_card = nullptr;
    g_title = nullptr;
    g_body = nullptr;
    g_hiding = false;
    if (root != nullptr && lv_obj_is_valid(root)) {
        lv_anim_delete(root, nullptr);  // 可能正有淡出动画在飞，先撤掉（连回调一起）
        lv_obj_del(root);
    }
}

bool CardVisible() { return g_root != nullptr && !g_hiding; }

}  // namespace yh_skin

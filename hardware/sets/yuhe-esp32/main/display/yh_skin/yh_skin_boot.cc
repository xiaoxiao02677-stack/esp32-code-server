#include "yh_skin_boot.h"

#include <esp_log.h>

#include <cstring>

// splash 专用小字体（约 130 个常用中文 + ASCII，~30KB 编译后）：
// 开机首帧在 assets 分区加载之前渲染，主题字体只有 basic 档（890 字），
// 「柚/陪/伴/助/初/始/稍/候…」都不在其中，开 LV_USE_FONT_PLACEHOLDER 时
// 渲染成方框（即用户看到的"开机乱码"）。本字体覆盖 splash 全部文案
// （品牌名/副标题/lang_config.h 状态串），BuildSplash 首建时直接用它。
// assets 的 common 档到位后 SetSplashFont 仍会重绑——那是双保险，不是依赖。
extern const lv_font_t font_splash_20_4;

// 开机画面：上电后屏幕亮起的第一帧就是品牌画面。
//
// 为什么用文件级静态状态而不是类：
//   全设备只有一个屏，Splash 的生命周期完全由 YhSkinDisplay::SetupUI ~ 首次待机
//   决定；引入类只会让调用方多持一个指针。代价是「不可重入」——本模块的
//   BuildSplash 只能在 SetupUI 里调一次，重复调用会先销毁旧画面再重建（见下）。

#define TAG "YhSkinBoot"

namespace yh_skin {
namespace {

// 品牌配色（与 yh_skin_display.h 的 kColor* 保持一致）
constexpr uint32_t kBgTop = 0x2A1633;
constexpr uint32_t kBgBottom = 0x120B18;
constexpr uint32_t kPrimary = 0xFF7AA2;
constexpr uint32_t kTextMain = 0xFFF7FB;
constexpr uint32_t kTextSub = 0xC9B8D9;
constexpr uint32_t kTextHint = 0x8B7A99;

lv_obj_t* g_root = nullptr;         // 全屏容器（不透明，盖住主界面）
lv_obj_t* g_status_label = nullptr; // 底部状态文案
lv_obj_t* g_bar = nullptr;          // 进度条（默认隐藏）
lv_obj_t* g_brand = nullptr;        // 品牌名标签（换字体时要重绑）
lv_obj_t* g_sub = nullptr;          // 副标题标签（同上）
lv_obj_t* g_bg = nullptr;           // splash 底图（用户壁纸/品牌底纹的宿主）
int g_long_side = 240;              // BuildSplash 时的屏幕长边，换底图时重算放大
bool g_dismissing = false;          // 淡出动画进行中（防重复触发）

// 动画回调：只改样式不碰对象结构，避免在动画帧里 delete
void DotOpaAnimCb(void* var, int32_t value) {
    lv_obj_set_style_opa(static_cast<lv_obj_t*>(var), static_cast<lv_opa_t>(value), 0);
}

void RootOpaAnimCb(void* var, int32_t value) {
    lv_obj_set_style_opa(static_cast<lv_obj_t*>(var), static_cast<lv_opa_t>(value), 0);
}

// 淡出结束：把 splash **隐藏**，不销毁。
//
// 为什么不删：实测崩点就是这个函数里的删对象 →
//   lv_obj_destructor:606 → lv_event_mark_deleted（LoadProhibited / EXCVADDR=0x14，
//   随后 rst:0xc 重启循环）。而 lv_obj_delete_async 只是把时刻挪到 async timer，
//   最终仍走 obj_delete_core → lv_obj_destructor:606 —— 同样要遍历 event_head，
//   对「链已失效」这一成因并不免疫（同事已核实该调用链）。
// splash 全设备只建一次，隐藏的代价只是留在屏外的几个 LVGL 对象；
// 换掉「析构整棵树」这条路径，是当前性价比最高的取舍。
void OnFadeOutCompleted(lv_anim_t* anim) {
    lv_obj_t* target = (anim != nullptr) ? static_cast<lv_obj_t*>(lv_anim_get_user_data(anim)) : nullptr;
    if (target == nullptr) {
        return;
    }
    // 只清理「仍然指向这个对象」的全局状态
    if (g_root == target) {
        g_root = nullptr;
        g_status_label = nullptr;
        g_bar = nullptr;
        g_brand = nullptr;
        g_sub = nullptr;
        g_bg = nullptr;  // 底图是 g_root 的子对象，父隐藏后不再可换图（UpdateSplashBackground 判空即静默）
        g_dismissing = false;
    }
    if (lv_obj_is_valid(target)) {
        lv_obj_add_flag(target, LV_OBJ_FLAG_HIDDEN);
    }
}

void SetFontIfAvailable(lv_obj_t* obj, const lv_font_t* font) {
    // font == nullptr 时不设置 → 继承父对象字体，主题热切换时不会留悬空指针
    if (obj != nullptr && font != nullptr) {
        lv_obj_set_style_text_font(obj, font, 0);
    }
}

// 呼吸点：三个错相位的圆点，用 opa 循环做「设备活着」的视觉锚点。
// 用 lv_anim 而不是 lv_timer：动画由 LVGL 主循环驱动，不需要自己管节拍。
void CreateBreathingDots(lv_obj_t* parent, const YhSkinProfile& profile, int center_y) {
    const int dot = profile.scaled(8);
    const int gap = profile.scaled(14);
    const int total = dot * 3 + gap * 2;
    for (int i = 0; i < 3; ++i) {
        lv_obj_t* d = lv_obj_create(parent);
        lv_obj_remove_flag(d, LV_OBJ_FLAG_SCROLLABLE);
        lv_obj_set_size(d, dot, dot);
        lv_obj_set_style_radius(d, LV_RADIUS_CIRCLE, 0);
        lv_obj_set_style_bg_color(d, lv_color_hex(kPrimary), 0);
        lv_obj_set_style_bg_opa(d, LV_OPA_COVER, 0);
        lv_obj_set_style_border_width(d, 0, 0);
        lv_obj_set_style_pad_all(d, 0, 0);
        lv_obj_align(d, LV_ALIGN_TOP_MID, -total / 2 + dot / 2 + i * (dot + gap), center_y);

        lv_anim_t a;
        lv_anim_init(&a);
        lv_anim_set_var(&a, d);
        lv_anim_set_exec_cb(&a, DotOpaAnimCb);
        lv_anim_set_values(&a, LV_OPA_20, LV_OPA_COVER);
        lv_anim_set_duration(&a, 900);
        lv_anim_set_playback_duration(&a, 900);
        lv_anim_set_repeat_count(&a, LV_ANIM_REPEAT_INFINITE);
        lv_anim_set_delay(&a, i * 200);  // 相位错开，形成流动感
        lv_anim_start(&a);
    }
}

}  // namespace

void BuildSplash(lv_obj_t* parent, const YhSkinProfile& profile, const YhSkinFonts& fonts,
                 const SplashInfo& info) {
    // 先复位「正在淡出」标志：parent 为空提前返回时若把它留在 true，
    // 后续 DismissSplash() 会被永久挡住，开机画面再也收不掉。
    g_dismissing = false;
    if (parent == nullptr) {
        return;
    }
    if (g_root != nullptr) {
        // 重建路径（例如主题切换后重新 SetupUI）：直接丢弃旧画面，避免两份叠加。
        // 必须先撤掉可能还在飞的淡出动画：否则它的 completed_cb 会在旧对象被
        // 删除之后才触发，去删一个悬垂/新对象。
        lv_anim_delete(g_root, RootOpaAnimCb);
        lv_obj_del(g_root);
        g_root = nullptr;
        g_status_label = nullptr;
        g_bar = nullptr;
        g_brand = nullptr;
        g_sub = nullptr;
        g_bg = nullptr;
    }

    g_root = lv_obj_create(parent);
    lv_obj_remove_flag(g_root, LV_OBJ_FLAG_SCROLLABLE);
    lv_obj_add_flag(g_root, LV_OBJ_FLAG_IGNORE_LAYOUT);
    lv_obj_set_size(g_root, profile.width, profile.height);
    lv_obj_set_pos(g_root, 0, 0);
    lv_obj_set_style_radius(g_root, 0, 0);
    lv_obj_set_style_border_width(g_root, 0, 0);
    lv_obj_set_style_pad_all(g_root, 0, 0);
    lv_obj_set_style_bg_color(g_root, lv_color_hex(kBgTop), 0);
    lv_obj_set_style_bg_grad_color(g_root, lv_color_hex(kBgBottom), 0);
    lv_obj_set_style_bg_grad_dir(g_root, LV_GRAD_DIR_VER, 0);
    lv_obj_set_style_bg_opa(g_root, LV_OPA_COVER, 0);  // 必须不透明：它要盖住主界面
    lv_obj_move_foreground(g_root);
    g_long_side = profile.long_side();

    // 背景图：用户已下发过壁纸就用它打底（需求：开机壁纸+背景壁纸都用用户图），
    // 否则回落编译期 good.jpg。非 240 屏按长边等比放大（超出部分显示层自然裁切）。
    // 壁纸是 240x240 RGB565 的 lv_img_dsc_t*，与 yh_skin_bg 同为 VARIABLE 源，
    // lv_image 能直接消费；透明度同样降到 60%，避免压住品牌字与状态文案。
    lv_obj_t* bg = lv_image_create(g_root);
    const lv_img_dsc_t* bg_src = static_cast<const lv_img_dsc_t*>(info.background);
    const bool user_wallpaper = (bg_src != nullptr && bg_src->data != nullptr);
    if (!user_wallpaper) {
        bg_src = &yh_skin_bg;
    }
    lv_image_set_src(bg, bg_src);
    int bg_w = user_wallpaper ? bg_src->header.w : 240;
    int scale = 256 * profile.long_side() / (bg_w > 0 ? bg_w : 240);
    if (scale > 256) {
        lv_image_set_scale(bg, static_cast<uint32_t>(scale));
    }
    lv_obj_set_style_image_opa(bg, LV_OPA_60, 0);
    lv_obj_align(bg, LV_ALIGN_CENTER, 0, 0);
    lv_obj_remove_flag(bg, LV_OBJ_FLAG_CLICKABLE);
    g_bg = bg;

    // 品牌名：文案与字号都可在调用侧给，缺省继承父字体
    lv_obj_t* brand = lv_label_create(g_root);
    lv_label_set_text(brand, info.brand != nullptr ? info.brand : "");
    // ★ 必须用文字字体，不能用 fonts.large。
    //   large 是 Material Symbols 图标字体（U+E000–F8FF 私用区），只含图标码位；
    //   拿它渲染中文会把每个汉字都落到 .notdef 上，而本工程开着
    //   CONFIG_LV_USE_FONT_PLACEHOLDER=y，于是"小柚"稳定渲染成两个方框 ——
    //   这属于 100% 必现，只是容易被误当成"字体加载失败"。
    //   字号想要更大就用 text 字体本身，别借图标字体。
    // ★★ splash 建于 assets 加载之前，fonts.text（basic 890 字）缺「柚」等字。
    //    首建一律用 splash 专用字体；common 到位后 SetSplashFont 会重绑接管。
    SetFontIfAvailable(brand, &font_splash_20_4);
    g_brand = brand;
    lv_obj_set_style_text_color(brand, lv_color_hex(kTextMain), 0);
    lv_obj_align(brand, LV_ALIGN_CENTER, 0, profile.round ? -profile.scaled(26)
                                                          : -profile.scaled(40));

    g_sub = nullptr;  // 没有副标题时别留着上一次的句柄
    if (info.subtitle != nullptr && info.subtitle[0] != '\0') {
        lv_obj_t* sub = lv_label_create(g_root);
        lv_label_set_text(sub, info.subtitle);
        SetFontIfAvailable(sub, &font_splash_20_4);
        g_sub = sub;
        lv_obj_set_style_text_color(sub, lv_color_hex(kTextSub), 0);
        lv_obj_align(sub, LV_ALIGN_CENTER, 0, profile.round ? profile.scaled(6)
                                                           : -profile.scaled(10));
    }

    // 呼吸点放在品牌名/副标题下方；圆屏额外抬高 12px，避开圆弧裁切
    int dots_y = profile.round ? (profile.height / 2 + profile.scaled(34))
                               : (profile.height / 2 + profile.scaled(20));
    CreateBreathingDots(g_root, profile, dots_y);

    // 状态文案（连接中/激活中…），默认空
    g_status_label = lv_label_create(g_root);
    lv_label_set_text(g_status_label, "");
    SetFontIfAvailable(g_status_label, &font_splash_20_4);
    lv_obj_set_style_text_color(g_status_label, lv_color_hex(kTextSub), 0);
    lv_obj_set_style_text_align(g_status_label, LV_TEXT_ALIGN_CENTER, 0);
    lv_obj_align(g_status_label, LV_ALIGN_BOTTOM_MID, 0, -profile.scaled(34));

    // 进度条：默认隐藏，只在真正有进度时出现（不显示假进度）
    g_bar = lv_bar_create(g_root);
    lv_obj_set_size(g_bar, profile.short_side() * 6 / 10, profile.scaled(6));
    lv_obj_set_style_radius(g_bar, profile.scaled(3), 0);
    lv_obj_set_style_bg_color(g_bar, lv_color_hex(0x3A2440), 0);
    lv_obj_set_style_bg_opa(g_bar, LV_OPA_COVER, 0);
    lv_obj_set_style_bg_color(g_bar, lv_color_hex(kPrimary), LV_PART_INDICATOR);
    lv_bar_set_range(g_bar, 0, 100);
    lv_bar_set_value(g_bar, 0, LV_ANIM_OFF);
    lv_obj_align(g_bar, LV_ALIGN_BOTTOM_MID, 0, -profile.scaled(18));
    lv_obj_add_flag(g_bar, LV_OBJ_FLAG_HIDDEN);

    // 版本号：右下角小字，方便现场确认烧的是哪一版
    if (info.version != nullptr && info.version[0] != '\0') {
        lv_obj_t* ver = lv_label_create(g_root);
        lv_label_set_text(ver, info.version);
        SetFontIfAvailable(ver, &font_splash_20_4);
        lv_obj_set_style_text_color(ver, lv_color_hex(kTextHint), 0);
        lv_obj_align(ver, LV_ALIGN_BOTTOM_RIGHT, -profile.scaled(8), -profile.scaled(8));
    }
}

// 换字体：开机画面是**在 assets 生效之前**建好的，建的时候用的还是编译进固件的
// basic 字体（890 字）。assets 里的 common（5258 字）要到 Application 初始化
// 后段才会被加载，那时 splash 早就画完了 —— 品牌名「小柚」里的「柚」不在 basic
// 里，就固定显示成方框（本工程开着 LV_USE_FONT_PLACEHOLDER）。
// 这个函数负责在 assets 就位后把 splash 上的文字重新绑到新字体上。
// 调用方必须已持有 LVGL 锁（ApplyFonts 是这么调的）。
void SetSplashFont(const lv_font_t* text_font) {
    if (text_font == nullptr) {
        return;
    }
    auto apply = [text_font](lv_obj_t* obj) {
        if (obj != nullptr && lv_obj_is_valid(obj)) {
            lv_obj_set_style_text_font(obj, text_font, 0);
        }
    };
    apply(g_brand);
    apply(g_sub);
    apply(g_status_label);
}

void SetSplashStatus(const char* text) {
    if (g_status_label == nullptr) {
        return;
    }
    lv_label_set_text(g_status_label, (text != nullptr) ? text : "");
}

void SetSplashProgress(int percent) {
    if (g_bar == nullptr) {
        return;
    }
    if (percent < 0) {
        lv_obj_add_flag(g_bar, LV_OBJ_FLAG_HIDDEN);
        return;
    }
    if (percent > 100) {
        percent = 100;
    }
    lv_obj_remove_flag(g_bar, LV_OBJ_FLAG_HIDDEN);
    lv_bar_set_value(g_bar, percent, LV_ANIM_ON);
}

void DismissSplash() {
    if (g_root == nullptr || g_dismissing) {
        return;
    }
    g_dismissing = true;
    ESP_LOGI(TAG, "DismissSplash: start fade-out");
    lv_anim_t a;
    lv_anim_init(&a);
    lv_anim_set_var(&a, g_root);
    // 目标对象随动画携带：回调只认自己这一个对象，不受期间重建影响
    lv_anim_set_user_data(&a, g_root);
    lv_anim_set_exec_cb(&a, RootOpaAnimCb);
    lv_anim_set_values(&a, LV_OPA_COVER, LV_OPA_TRANSP);
    lv_anim_set_duration(&a, 300);
    lv_anim_set_completed_cb(&a, OnFadeOutCompleted);
    lv_anim_start(&a);
}

// 淡出过程也算「可见」：这 300ms 里 splash 仍是不透明盖层，
// 若此时返回 false，SplashAbsorbsStatus 会放行「正在连接」之类的噪声文案，
// 让它们闪一下气泡再被淡出带走的品牌画面盖住，观感很脏。
bool SplashVisible() { return g_root != nullptr; }

// splash 显示期间壁纸到达时换底图：与 BuildSplash 的底图段同一套规则
// （壁纸优先 → 回落 yh_skin_bg → 按图宽等比放大到屏幕长边 → 60% 透明度）。
// 典型时序：开机 splash 亮着 → 服务器下发壁纸 → SetWallpaper 成功 →
// ApplyBackground → 这里立刻把开机画面的底图也换掉，用户在开机阶段就能看到
// 自己的图，而不是等下次开机。调用方必须已持 LVGL 锁；splash 不可见时静默空转。
// 传 nullptr = 清除壁纸，回落品牌底纹（与 ApplyBackground 的三级回落一致）。
void UpdateSplashBackground(const void* background) {
    if (g_root == nullptr || g_bg == nullptr || !lv_obj_is_valid(g_bg)) {
        return;
    }
    const lv_img_dsc_t* src = static_cast<const lv_img_dsc_t*>(background);
    const bool user_wallpaper = (src != nullptr && src->data != nullptr);
    if (!user_wallpaper) {
        src = &yh_skin_bg;
    }
    lv_image_set_src(g_bg, src);
    // VARIABLE 源同指针不短路，且换 src 后会按新 header 重算布局；
    // 但缩放不会自动跟（建对象时算好的值会沿用），换图必须重算。
    int bg_w = user_wallpaper ? src->header.w : 240;
    int scale = 256 * g_long_side / (bg_w > 0 ? bg_w : 240);
    if (scale > 256) {
        lv_image_set_scale(g_bg, static_cast<uint32_t>(scale));
    } else {
        lv_image_set_scale(g_bg, 256);
    }
    lv_obj_align(g_bg, LV_ALIGN_CENTER, 0, 0);
    lv_obj_invalidate(g_bg);
}

bool SplashAbsorbsStatus(const char* status) {
    if (!SplashVisible() || status == nullptr || status[0] == '\0') {
        return false;
    }
    // 只吞「开机噪声」：这些文案在原生态里是状态栏文字，出现在气泡里会盖住品牌画面
    static const char* const kNoise[] = {
        "待机", "初始化", "正在连接", "连接中", "启动中", "激活中",
        "STANDBY", "Initializing", "INITIALIZING", "Connecting", "Starting",
    };
    for (const char* key : kNoise) {
        if (strstr(status, key) != nullptr) {
            return true;
        }
    }
    return false;
}

}  // namespace yh_skin

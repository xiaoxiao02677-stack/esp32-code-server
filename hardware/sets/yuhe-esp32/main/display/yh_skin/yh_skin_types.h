#pragma once

// 屿禾「小柚」皮肤 —— 公共类型
//
// 单独成文件的原因：显示层（yh_skin_display）、开机画面（yh_skin_boot）、
// 系统卡片（yh_skin_cards）三者都要用同一份几何画像与字体集合，
// 而字体指针只能由显示层从 LvglTheme 取到后传下去（子模块拿不到 display 实例）。

#include <lvgl.h>

// 几何画像：布局不写死 240 坐标，全部由 width/height/round 推导。
struct YhSkinProfile {
    int width = 240;
    int height = 240;
    bool round = true;        // 圆屏：四角会被裁，内容按内切圆收边
    bool has_battery = true;  // 无电池板（yh-n16r8-st7789）隐藏电量文案

    int short_side() const { return width < height ? width : height; }
    int long_side() const { return width < height ? height : width; }

    // 以 240 为基准的等比缩放；1:1 尺寸时结果与基准实现逐像素一致。
    int scaled(int px_240) const {
        int v = (px_240 * short_side() + 120) / 240;
        return v == 0 ? (px_240 > 0 ? 1 : 0) : v;
    }

    static YhSkinProfile Round240(bool has_battery) {
        YhSkinProfile p;
        p.width = 240;
        p.height = 240;
        p.round = true;
        p.has_battery = has_battery;
        return p;
    }
    static YhSkinProfile Wide320x240() {
        YhSkinProfile p;
        p.width = 320;
        p.height = 240;
        p.round = false;
        p.has_battery = true;
        return p;
    }
    static YhSkinProfile Tall240x320() {
        YhSkinProfile p;
        p.width = 240;
        p.height = 320;
        p.round = false;
        p.has_battery = true;
        return p;
    }
};

// 字体集合：由显示层从当前 LvglTheme 取出后传入子模块。
// 任何一项为 nullptr 时子模块一律「不显式设置字体」→ 继承父对象字体，
// 这样主题热切换时不会留下悬空字体指针（2026-10-08 崩溃的根因）。
struct YhSkinFonts {
    const lv_font_t* text = nullptr;
    const lv_font_t* icon = nullptr;
    const lv_font_t* large = nullptr;
    const lv_font_t* emoji = nullptr;
};

// 共享背景图（240x240 RGB565，定义在 yh_skin_assets.c）。
// 放在 types.h 而不是 display.h：开机画面也要用它，但开机画面不该反向依赖显示层。
// 非 240 屏由使用方按长边等比放大绘制。
extern const lv_image_dsc_t yh_skin_bg;

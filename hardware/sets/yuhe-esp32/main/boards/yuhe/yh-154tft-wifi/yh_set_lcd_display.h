#ifndef YH_SET_LCD_DISPLAY_H
#define YH_SET_LCD_DISPLAY_H

#include "display/yh_skin/yh_skin_display.h"
#include "lvgl_theme.h"

#if CONFIG_YH_UI_THEME_PIXELPET
#include "display/pet_skin/pet_skin_display.h"
#elif CONFIG_YH_UI_THEME_EMOPET
#include "display/emo_skin/emo_skin_display.h"
#elif CONFIG_YH_UI_THEME_DENGYU
#include "display/DengYu_skin/dengyu_skin_display.h"
#elif CONFIG_YH_UI_THEME_FACE
#include "display/face_skin/face_skin_display.h"
#elif CONFIG_YH_UI_THEME_CAT
#include "display/cat_skin/cat_skin_display.h"
#endif

#include <esp_lvgl_port.h>

// 屿禾小方块 1.54 寸 TFT：共享皮肤 + 芯片高温警告弹窗。
//
// 为什么做成皮肤类的子类而不是把弹窗塞进共享层：
//   高温告警只有这一块板有（power_manager 读 NTC），共享层不该为单一硬件
//   背上看门狗式的 UI。子类只做「基类建好界面 → 追加一个浮层」这一件事。
//
// 主题条件编译：YhSetLcdDisplay 始终继承「当前主题的皮肤基类」——
// xiaoyou（默认）= YhSkinDisplay，pixel-pet = PetSkinDisplay，
// emopet = EmoSkinDisplay，dengyu = DengYuSkinDisplay，face = FaceSkinDisplay，
// cat = CatSkinDisplay。高温弹窗等板级浮层对六套主题同样生效。
#if CONFIG_YH_UI_THEME_PIXELPET
class YhSetLcdDisplay : public PetSkinDisplay {
public:
    using PetSkinDisplay::PetSkinDisplay;
    using SkinBase = PetSkinDisplay;
#elif CONFIG_YH_UI_THEME_EMOPET
class YhSetLcdDisplay : public EmoSkinDisplay {
public:
    using EmoSkinDisplay::EmoSkinDisplay;
    using SkinBase = EmoSkinDisplay;
#elif CONFIG_YH_UI_THEME_DENGYU
class YhSetLcdDisplay : public DengYuSkinDisplay {
public:
    using DengYuSkinDisplay::DengYuSkinDisplay;
    using SkinBase = DengYuSkinDisplay;
#elif CONFIG_YH_UI_THEME_FACE
class YhSetLcdDisplay : public FaceSkinDisplay {
public:
    using FaceSkinDisplay::FaceSkinDisplay;
    using SkinBase = FaceSkinDisplay;
#elif CONFIG_YH_UI_THEME_CAT
class YhSetLcdDisplay : public CatSkinDisplay {
public:
    using CatSkinDisplay::CatSkinDisplay;
    using SkinBase = CatSkinDisplay;
#else
class YhSetLcdDisplay : public YhSkinDisplay {
public:
    using YhSkinDisplay::YhSkinDisplay;
    using SkinBase = YhSkinDisplay;
#endif

    void SetupUI() override {
        // ★ SkinBase 而非 YhSkinDisplay：主题子类的 SetupUI 负责建
        //   宠物/发光眼 canvas，限定到 YhSkinDisplay 会整层跳过。
        SkinBase::SetupUI();
        // ★ 必须自己再拿一次锁：基类 SetupUI() 内部的 DisplayLockGuard 在它
        //   返回时就析构了，锁已经放掉。而这里的调用方是 application.cc 的
        //   主任务，此刻 taskLVGL 已经在跑 lv_timer_handler —— 下面
        //   SetupHighTempWarningPopup() 有 13 处 lv_obj_* / lv_label_*，
        //   裸调就是跨任务改对象树。LVGL 的 event_head 是单个全局链表、
        //   自身不加锁（本工程 LV_USE_OS == LV_OS_NONE），并发 push/pop 会把
        //   它指到已返回的栈槽 → 之后要么 mark_deleted 无限循环（挂死），
        //   要么读 0x14 崩 LoadProhibited。
        //   DisplayLockGuard 是递归锁，重复加锁安全。
        DisplayLockGuard lock(this);
        // 基类已建好主界面与开机画面，这里追加告警浮层并压到最上层
        SetupHighTempWarningPopup();
    }

    void SetupHighTempWarningPopup() {
        if (high_temp_popup_ != nullptr) {
            return;  // SetupUI 可能被重复调用（主题切换），浮层只建一次
        }
        auto lvgl_theme = static_cast<LvglTheme*>(current_theme_);
        const lv_font_t* text_font = nullptr;
        if (lvgl_theme != nullptr && lvgl_theme->text_font() != nullptr) {
            text_font = lvgl_theme->text_font()->font();
        }

        high_temp_popup_ = lv_obj_create(lv_screen_active());
        lv_obj_remove_flag(high_temp_popup_, LV_OBJ_FLAG_SCROLLABLE);
        lv_obj_set_size(high_temp_popup_, LV_HOR_RES * 9 / 10,
                        text_font != nullptr ? text_font->line_height * 2 : 48);
        lv_obj_align(high_temp_popup_, LV_ALIGN_BOTTOM_MID, 0, 0);
        lv_obj_set_style_bg_color(high_temp_popup_, lv_palette_main(LV_PALETTE_RED), 0);
        lv_obj_set_style_bg_opa(high_temp_popup_, LV_OPA_COVER, 0);
        lv_obj_set_style_radius(high_temp_popup_, 10, 0);
        lv_obj_set_style_border_width(high_temp_popup_, 0, 0);

        high_temp_label_ = lv_label_create(high_temp_popup_);
        lv_label_set_text(high_temp_label_, "警告：温度过高");
        if (text_font != nullptr) {
            lv_obj_set_style_text_font(high_temp_label_, text_font, 0);
        }
        lv_obj_set_style_text_color(high_temp_label_, lv_color_white(), 0);
        lv_obj_center(high_temp_label_);

        lv_obj_add_flag(high_temp_popup_, LV_OBJ_FLAG_HIDDEN);
        lv_obj_move_foreground(high_temp_popup_);
    }

    // chip_temp 超阈值显示，恢复后隐藏；threshold 由调用方给（默认 75℃）
    void UpdateHighTempWarning(float chip_temp, float threshold = 75.0f) {
        // ★ 本函数由 PowerManager 的温度回调驱动，不在 LVGL 任务上下文，
        //   直接碰 lv_obj_* 属于跨任务访问（会破坏对象树/事件链）。
        //   DisplayLockGuard 是递归锁，即便已在持锁上下文里调用也安全。
        DisplayLockGuard lock(this);
        if (high_temp_popup_ == nullptr) {
            // SetupUI 还没跑到（上电前 1~2 秒 power_manager 就可能回调），忽略即可
            return;
        }
        if (chip_temp >= threshold) {
            ShowHighTempWarning();
        } else {
            HideHighTempWarning();
        }
    }

    void ShowHighTempWarning() {
        if (high_temp_popup_ != nullptr && lv_obj_has_flag(high_temp_popup_, LV_OBJ_FLAG_HIDDEN)) {
            lv_obj_remove_flag(high_temp_popup_, LV_OBJ_FLAG_HIDDEN);
            lv_obj_move_foreground(high_temp_popup_);
        }
    }

    void HideHighTempWarning() {
        if (high_temp_popup_ != nullptr && !lv_obj_has_flag(high_temp_popup_, LV_OBJ_FLAG_HIDDEN)) {
            lv_obj_add_flag(high_temp_popup_, LV_OBJ_FLAG_HIDDEN);
        }
    }

private:
    lv_obj_t* high_temp_popup_ = nullptr;
    lv_obj_t* high_temp_label_ = nullptr;
};

#endif  // YH_SET_LCD_DISPLAY_H

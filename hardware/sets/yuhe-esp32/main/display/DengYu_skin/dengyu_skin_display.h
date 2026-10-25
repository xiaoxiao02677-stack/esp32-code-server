#pragma once

// ════════════════════════════════════════════════════════════════════════
// 灯语 DengYu 主题 · 显示层（dengyu_skin_display.h）
// ════════════════════════════════════════════════════════════════════════
//
// 设计提案：hardware/sets/theme/DengYu/docs/（HTML 高保真渲染稿）。
// DengYuSkinDisplay 继承 YhSkinDisplay，白嫖骨架（壁纸双槽/字体退休池/
// 锁纪律/占位族/系统卡片/几何 profile），只换视觉层：
//   · 光萤（dengyu_orb）取代背景图 + emoji 表情
//   · 剧场字幕流取代气泡（无框、角色分色、逐字浮现）
//   · 状态光语取代表情动画：聆听=青苔绿、思考=三点、说话=EQ、
//     断连=珊瑚红放缓呼吸
//   · 晨间卡片：07:00 定时 30s 纸白底大时钟 + 陪伴天数问候（天气预留）
//
// 主题切换：Kconfig choice YH_UI_THEME（main/Kconfig.projbuild）
//   · YH_UI_THEME_DENGYU —— 灯语，本类
// build.py --theme DengYu 注入 CONFIG_YH_UI_THEME_DENGYU=y。
//
// 板级用法（四个版型同构，见各板 yh_set_*.cc）：
//   #if CONFIG_YH_UI_THEME_DENGYU
//       display_ = new DengYuSkinDisplay(panel_io, panel, W, H, OX, OY,
//                                        MX, MY, SWAP, YhSkinProfile::Tall240x320());
//   #endif
//
// 几何变体（YhSkinProfile 决定，本类内部自适应）：
//   · Tall240x320 / 240 圆屏：光萤上区居中，字幕流下区（圆屏单行字幕）
//   · Wide320x240 横屏：左光萤（90px 上区）+ 右字幕流
//
// 状态映射（Application::GetDeviceState → 皮肤状态）：
//   Idle → DENGYU_STATE_IDLE（暖橙呼吸 + 涟漪 + 短句轮播 4.2s）
//   Listening → LISTENING（青苔绿提速）
//   Speaking → SPEAKING（迷你光萤 + 逐字 + EQ；TTS 完自动回 IDLE）
//   Connecting/Upgrading 等 → 沿用基类卡片（配网/激活/升级），光萤侧不作动
//   网络断开（Application 无独立状态，用 ShowNotification 关键词嗅探）
//
// 字幕文本安全：所有 SetChatMessage 文本走 TruncateUtf8 截断（不切半码点），
// 打字机 buffer 固定 448 字节（56 汉字 × 3B + null），超长截断显示 …。

#include "display/yh_skin/yh_skin_display.h"
#include "dengyu_skin_types.h"
#include "dengyu_orb.h"

#include <lvgl.h>

class DengYuSkinDisplay : public YhSkinDisplay {
public:
    // 构造签名与 YhSkinDisplay 完全一致（板级只换类名）
    DengYuSkinDisplay(esp_lcd_panel_io_handle_t panel_io, esp_lcd_panel_handle_t panel,
                      int width, int height, int offset_x, int offset_y, bool mirror_x,
                      bool mirror_y, bool swap_xy, const YhSkinProfile& profile);
    ~DengYuSkinDisplay() override;

    // ---- Display 渲染层覆写（协议语义与基类一致）----
    void SetupUI() override;
    void SetStatus(const char* status) override;
    void SetEmotion(const char* emotion) override;
    void SetChatMessage(const char* role, const char* content) override;
    void ClearChatMessages() override;
    void ShowNotification(const char* notification, int duration_ms = 3000) override;
    void ShowNotification(const std::string& notification, int duration_ms = 3000) override;
    void HandleKeyEvent(int ev) override;
    void NextEasterEgg() override;
    void Tick1s() override;

private:
    // ---- 状态机 ----
    // 真源是 Application::GetDeviceState()（250ms 轮询对账，PetSkin 同款先例），
    // 协议事件（SetChatMessage/ShowNotification/HandleKeyEvent）只做即时预置。
    void EnterDengYuState(dengyu_state_t state);
    void PollDeviceState();               // 250ms lv_timer：设备态 → 光语态
    static void PollTimerCb(lv_timer_t* timer);
    dengyu_state_t dengyu_state_ = DENGYU_STATE_IDLE;

    // ---- 视觉构建 ----
    void BuildDengYuScene();     // 光萤 + 字幕流 + EQ（SetupUI 调）
    void BuildMorningCard();     // 晨间卡片（SetupUI 即建，07:00 显示）
    bool IsRound() const;        // 圆屏单行字幕布局
    bool IsTall() const;         // 240x320 竖屏
    bool IsWide() const;         // 320x240 横屏（左光萤右字幕）

    // ---- 字幕流 ----
    void PushSubtitleRow(const char* who, const char* text, bool is_user);
    void StartTypewriter(const char* text);
    void StopTypewriter();
    void AdvanceTypewriter();    // lv_timer 回调：每 tick 追加 1 码点
    static void TypewriterTimerCb(lv_timer_t* timer);
    void ShowStatusLine(const char* text, uint32_t color, int ttl_ticks = -1);
    void HideStatusLine();
    void RotateIdleWord();                  // 待机短句轮播
    static void OnRowEnterDeleted(lv_event_t* e);  // 字幕行删除事件（同步打字机句柄）

    // ---- EQ 声纹（说话态）----
    void BuildEq();
    void EqStart();
    void EqStop();
    static void EqBarTimerCb(lv_timer_t* timer);

    // ---- 晨间 ----
    void TryEnterMorning();
    void ExitMorning();
    void UpdateMorningClock();

    // ---- 布局几何（构造时按 profile 算好）----
    int orb_center_x_ = 0, orb_center_y_ = 0;   // 主光萤中心
    int orb_diameter_ = 64;                       // 主光萤直径
    int flow_left_ = 0, flow_top_ = 0;            // 字幕区
    int flow_width_ = 0, flow_height_ = 0;
    int rows_capacity_ = 6;                       // 字幕历史行数上限（圆屏 1）
    bool round_screen_ = false;

    // ---- 对象句柄 ----
    dengyu_orb_t* orb_ = nullptr;         // 主光萤
    dengyu_orb_t* mini_orb_ = nullptr;    // 说话态迷你光萤
    lv_obj_t* flow_ = nullptr;            // 字幕流容器（flex column）
    lv_obj_t* status_line_ = nullptr;     // 状态短语
    lv_obj_t* idle_word_ = nullptr;       // 待机短句
    lv_obj_t* sub_label_ = nullptr;       // 圆屏单行字幕
    lv_obj_t* eq_box_ = nullptr;          // EQ 容器（整体显隐）
    lv_obj_t* eq_bars_[5] = {nullptr};
    lv_timer_t* eq_timer_ = nullptr;
    lv_timer_t* type_timer_ = nullptr;
    lv_timer_t* poll_timer_ = nullptr;    // 250ms 设备态对账

    // ---- 晨间卡片对象 ----
    lv_obj_t* morning_root_ = nullptr;
    lv_obj_t* morning_clock_ = nullptr;
    lv_obj_t* morning_greet_ = nullptr;
    int morning_until_tick_ = -1;   // 1s 节拍计数的截止（-1 无卡片）
    int last_morning_day_ = -1;     // 已触发晨间卡的日期（防 07:xx 重复触发）

    // ---- 打字机 ----
    char type_buffer_[448];
    uint16_t type_pos_ = 0;          // 已显示字节数
    uint16_t type_len_ = 0;          // 全文长度
    lv_obj_t* type_label_ = nullptr; // 正在打字的行（flow 里最后一行 AI 行）

    // ---- 陪伴天数（NVS）----
    int32_t companion_days_ = 0;
    void LoadCompanionDays();
    void TouchCompanionDays();       // 日期变化 +1

    // ---- 光萤配色轮换（NVS 记忆）----
    dengyu_palette_t palette_ = DENGYU_PALETTE_EMBER;
    void LoadPalette();
    void SavePalette();

    // ---- 1s 节拍 ----
    int tick_count_ = 0;
    int last_idle_word_tick_ = 0;
    int think_word_idx_ = 0;        // 思考轮词索引
    int idle_word_idx_ = 0;         // 待机短句索引
    int last_sync_day_ = -1;        // 上次触碰陪伴天数的日期（1~31）
    int status_until_tick_ = -1;    // 状态短语自动隐藏时刻（-1 常驻）
    bool error_latch_ = false;      // 断连锁存：连接成功通知清除
};

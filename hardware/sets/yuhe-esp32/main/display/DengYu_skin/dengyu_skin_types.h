#pragma once

// ════════════════════════════════════════════════════════════════════════
// 灯语 DengYu 主题 · 类型与色板（dengyu_skin_types.h）
// ════════════════════════════════════════════════════════════════════════
//
// 设计来源：hardware/sets/theme/DengYu/docs/（HTML 高保真提案）。
// 概念：屏幕是一盏会说话的灯——顶部光萤承载情绪（呼吸/涟漪/变色），
// 下方剧场字幕流承载语言（无气泡框、角色分色、逐字浮现）。
//
// 色板纪律（与提案一致，全部经 RGB565 量化校准，见提案 token 表）：
//   night   #080C19 (0x0863)  夜幕底
//   ember   #C57D3A (0xC3E7)  炭火橙（默认光萤中圈）
//   cream   #F7EFE6 (0xF77C)  纸白（AI 字幕主色，对底 17.1:1）
//   sage    #ADDBB5 (0xAED6)  青苔绿（聆听态专属，全案唯一冷色）
//   coral   #EF715A (0xEB8B)  珊瑚红（断连/异常专属）
// 光萤辉光 = 4 层硬边同心圆（core #FFF6E1 / l2 / l3 / 外圈），**绝不用渐变**
// —— RGB565 下连续渐变必带色带（banding），分层圆是既定风格不是妥协。
//
// 字体（零新增 flash，全部来自 78__xiaozhi-fonts 组件现成字档）：
//   正文字幕   font_noto_sans_basic_16_4（Regular / bpp4 抗锯齿）
//   状态短语   复用主题 text 字体（20_4）
//   标签/页脚  font_noto_sans_basic_14_1
//   晨间时钟   font_noto_sans_basic_30_4
// 注意：板级 CMake 的 BUILTIN_TEXT_FONT 对 yh 系列板是 20_4，
// DengYu 自建控件**直接 extern 引用组件符号**，不走 theme->text_font()。

#include <lvgl.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

// ---- 状态（映射 Application::GetDeviceState() + 皮肤内部细化）----
typedef enum {
    DENGYU_STATE_IDLE = 0,      // 待机：光萤暖橙呼吸 + 涟漪 + 短句轮播
    DENGYU_STATE_LISTENING,     // 聆听：光萤转青苔绿，呼吸提速
    DENGYU_STATE_THINKING,      // 思考：三点跳动 + 「想想哦」轮词
    DENGYU_STATE_SPEAKING,      // 说话：迷你光萤 + 字幕逐字浮现 + EQ
    DENGYU_STATE_MORNING,       // 晨间：纸白底大时钟卡片（07:00 定时 30s）
    DENGYU_STATE_ERROR,         // 断连：珊瑚红半透明，呼吸放缓
} dengyu_state_t;

// ---- 光萤配色（双击轮换，NVS 记忆）----
typedef enum {
    DENGYU_PALETTE_EMBER = 0,   // 暖橙（默认）炭火
    DENGYU_PALETTE_CYAN,        // 青蓝 月光
    DENGYU_PALETTE_VIOLET,      // 紫暮 薰衣草
    DENGYU_PALETTE_CORAL,       // 珊瑚 蜜桃
    DENGYU_PALETTE_MAX
} dengyu_palette_t;

// 一套光萤配色：4 层同心圆 + 涟漪边 + 状态主色
typedef struct {
    uint32_t core;     // 最亮芯 #FFF6E1 系
    uint32_t l2;       // 第二层
    uint32_t l3;       // 第三层（主色圈）
    uint32_t l4;       // 最外层（深色圈）
    uint32_t ripple;   // 涟漪环颜色
} dengyu_orb_colors_t;

const dengyu_orb_colors_t* dengyu_orb_colors(dengyu_palette_t palette);
const char* dengyu_palette_name(dengyu_palette_t palette);

// ---- 几何（240 短边基准，其余按 profile 缩放）----
typedef struct {
    int16_t orb_d;        // 光萤主体直径（圆内切：光萤=芯 64）
    int16_t orb_layer_d;  // 各层直径：l4 = orb_d，l3 = 0.8125*d，l2 = 0.5625*d
    int16_t ripple_max_d; // 涟漪扩散最大直径
    int16_t mini_orb_d;   // 说话态迷你光萤直径（26）
} dengyu_geom_t;

// ---- 动效参数（ms）----
typedef struct {
    uint16_t breathe_half_ms;   // 呼吸半周期（单向时长）
    uint16_t ripple_period_ms;  // 涟漪一圈
    uint16_t ripple_phase_ms;   // 双道涟漪错相
    uint16_t typewriter_ms;     // 逐字间隔
    uint16_t state_fade_ms;     // 状态切换淡入
} dengyu_motion_t;

const dengyu_geom_t* dengyu_default_geom(void);
const dengyu_motion_t* dengyu_default_motion(void);

#ifdef __cplusplus
}
#endif

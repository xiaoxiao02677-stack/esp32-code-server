#pragma once

// ════════════════════════════════════════════════════════════════════════
// 极简脸 face 主题 · 渲染核心（face_core.h）
// ════════════════════════════════════════════════════════════════════════
//
// 纯 C 渲染循环（对应 HTML 的 loop() + blink() + interact()），
// 由显示层的 30fps lv_timer 驱动（说话态隔帧降 15fps）。
//
// 对象树（全部挂在 face_root_ 容器，纯黑底，零文字零字体依赖）：
//   face_root_（全屏透明容器）
//   ├── eye_l / eye_r（每只 3 层，同心直接定位，免嵌套容器）：
//   │   ├── glow   辉光外圈（d×1.22，glow 色 20% opa）← 最底最淡
//   │   ├── glow2  辉光内圈（d×1.10，glow 色 40% opa）
//   │   └── body   主体圆（d，#E8F4F6 不透明）
//   │   （三层同圆心、每帧按当帧尺寸直接 set_pos/set_size——
//   │     对应 CSS transform 作用于 .eye 整体含 shadow；
//   │     眨眼 squash 时辉光同比压扁，同 CSS scaleY 缩阴影）
//   └── mouth（圆角矩形 #E8F4F6）
//
// 动画实现（全部显式状态机，主循环每帧推进——不用 lv_anim：
//   游荡/呼吸/嘴过渡是持续行为且参数每帧变，声明式动画反而绕）：
//   眨眼    blink_t 0→1 进度，cos 缓动压扁眼高（三层同比 squash）
//   呼吸    sin(now_ms / 周期)×2.5%（idle/sleepy 两档）——乘进眼径/嘴高
//   游荡    target → look lerp 跟随，概率重选目标
//   嘴      四参数 lerp 到当前表情目标值 + talking 开合叠加
//   回弹    interact_t 0→1，sin(π·ease(t))×16%
//
// 线程纪律：只在 LVGL 任务上下文（lv_timer 回调）或已持 DisplayLockGuard
// 时调用；渲染函数自身不加锁（调用方持有）。

#include "face_skin_types.h"

#include <lvgl.h>
#include <stdbool.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

typedef struct face_core_s face_core_t;

// 创建：parent 挂载点（屏幕），geom 几何（按屏型换算过的）
face_core_t* face_core_create(lv_obj_t* parent, const face_geom_t* geom);

// 销毁（删对象树，释放状态）
void face_core_destroy(face_core_t* core);

// 显隐（系统卡片弹出时隐藏，收起后恢复）
void face_core_set_visible(face_core_t* core, bool visible);

// ---- 状态驱动（对应 HTML setMode 家族）----
void face_core_set_expr(face_core_t* core, face_expr_t expr);  // 切表情（嘴平滑过渡）
face_expr_t face_core_expr(const face_core_t* core);

// ---- 状态辉光（纯脸零文字的状态信号，表情通道之外的独立通道）----
// 设备态 → 眼睛辉光层颜色，黑底上一眼可辨（按 BOOT 后不用猜）：
//   idle 原稿淡蓝 / listening 青绿 / speaking 暖橙 / connecting 琥珀慢闪 / error 珊瑚红
// 只换辉光层的色/透明度，主体与嘴保持 #E8F4F6 不动——设计语言不变。
typedef enum {
    FACE_GLOW_IDLE = 0,      // 原稿淡蓝 #B4DCFF（默认）
    FACE_GLOW_LISTENING,     // 青绿 #7BE8A0：在听
    FACE_GLOW_SPEAKING,      // 暖橙 #F7B96A：说话中
    FACE_GLOW_CONNECTING,    // 琥珀 #F7D96A 慢闪 1.6s：联网/升级
    FACE_GLOW_ERROR,         // 珊瑚红 #F76E5E：致命错误
    FACE_GLOW_MAX
} face_glow_t;

void face_core_set_glow(face_core_t* core, face_glow_t glow);

// interact 傲娇回弹：520ms 放大回弹 + 随机小表情（happy/shy/surprise 三选一）
// 1800ms 后回 idle（由内部帧计数管理，显示层无需额外定时器）
void face_core_interact(face_core_t* core);

// interact 彩蛋窗口内（弹跳 520ms + 表情 1.8s）：显示层 SetEmotion 应让路，
// 不用协议表情覆盖彩蛋（pet 皮肤 easter_until_tick_ 同款语义）
bool face_core_in_interact(const face_core_t* core);

// 手动触发一次眨眼
void face_core_blink(face_core_t* core);

// ---- 渲染推进（主循环每帧调，内部完成全部动画状态机）----
// render_this_frame=false 时只推进状态不碰对象（说话态隔帧降 15fps 用）。
// 线程纪律同上：由显示层在持锁/LVGL 任务下调，自身不加锁。
void face_core_tick(face_core_t* core, bool render_this_frame);

#ifdef __cplusplus
}
#endif

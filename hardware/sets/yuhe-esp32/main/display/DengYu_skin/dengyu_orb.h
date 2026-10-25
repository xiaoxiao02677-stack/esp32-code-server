#pragma once

// ════════════════════════════════════════════════════════════════════════
// 灯语 DengYu 主题 · 光萤渲染模块（dengyu_orb.h）
// ════════════════════════════════════════════════════════════════════════
//
// 光萤 = 存在感的全部。对象树（全部挂在 wrapper 透明容器内，
// 子对象 LV_ALIGN_CENTER 对齐——size 动画自动保持居中，不会漂移）：
//
//   wrapper（透明，尺寸=涟漪最大直径，定位到 cx,cy）
//   ├── core_box（透明容器，CENTER）← 呼吸 zoom/opa 动画作用点
//   │   ├── l1 芯 20/64·d  #FFF6E1 系
//   │   ├── l2    36/64·d
//   │   ├── l3    52/64·d
//   │   └── l4 外 64/64·d
//   ├── ripple[0..1]（透明底 2px 边框圆环，CENTER）← size+opa 扩散
//   └── dot[0..2]（思考三点，CENTER + y 偏移动画）
//
// 全部纯色硬边圆，零渐变零模糊（RGB565 纪律）。
// 动画互不冲突：呼吸（zoom）、涟漪（size）、三点（y 偏移）作用于不同对象。
// 线程纪律：只在 LVGL 任务上下文或已持 DisplayLockGuard 时调用。

#include "dengyu_skin_types.h"

#include <lvgl.h>
#include <stdbool.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

typedef struct dengyu_orb_s dengyu_orb_t;

// 创建光萤组：parent 挂载点，cx/cy 中心坐标（相对 parent），d 主体直径
// （建议 = profile.scaled(64)；涟漪最大直径 = d·178/64 由模块内部计算）
dengyu_orb_t* dengyu_orb_create(lv_obj_t* parent, int cx, int cy, int d);

// 迷你光萤（说话态 26px 版本）：3 层 + 单涟漪，无思考点
dengyu_orb_t* dengyu_mini_orb_create(lv_obj_t* parent, int cx, int cy, int d);

// 销毁（先删 anim 再删对象）
void dengyu_orb_destroy(dengyu_orb_t* orb);

// 整组显隐（说话态藏主光萤；对象树保留，动画不停也要先隐藏）
void dengyu_orb_set_visible(dengyu_orb_t* orb, bool visible);

// 换配色（原地改 style 颜色，不重建对象）
void dengyu_orb_set_palette(dengyu_orb_t* orb, const dengyu_orb_colors_t* colors);

// ---- 状态语义（只改动画参数与可见层，不重建对象树）----
void dengyu_orb_idle(dengyu_orb_t* orb);    // 待机：呼吸 4.8s + 双道涟漪
void dengyu_orb_listen(dengyu_orb_t* orb);  // 聆听：呼吸 3.2s + 涟漪提速（配色由调用方切青苔绿）
void dengyu_orb_think(dengyu_orb_t* orb);   // 思考：藏圆层，三点跳动
void dengyu_orb_speak(dengyu_orb_t* orb);   // 说话：呼吸 3.8s，无涟漪
void dengyu_orb_error(dengyu_orb_t* orb);   // 断连：珊瑚红 + 呼吸放缓 7.2s + opa 低
void dengyu_orb_stop(dengyu_orb_t* orb);    // 停全部动画（进晨间卡片前）
void dengyu_mini_orb_idle(dengyu_orb_t* orb); // 迷你光萤轻呼吸 4.2s

#ifdef __cplusplus
}
#endif

/* ============================================================
 * emo_face.h/.c — EMOpet 风格机器人发光眼（主固件移植版）
 *
 * 移植自 hardware/sets/theme/EMOpet/main/src/emopet_face.c。
 * 差异：
 *   1) 几何全部经 emo_layout_t 换算（240 基准 → 任意屏），不再写死 SCR_W/H；
 *   2) 绘制层改为直写 RGB565 buffer（LVGL 9.5 已删除 lv_canvas_draw_* 旧 API，
 *      且绘制任务管线在 ESP32-S3 上每帧数百任务卡成 PPT——2026-10-19 教训）；
 *   3) 顶部点阵状态栏（时间/WiFi/电量）不移植——主固件基类 chrome 已有；
 *   4) 底部声波条保留（wave 数据由基类 SpeakEnergy 正弦拟态驱动）。
 * ============================================================ */
#ifndef EMO_FACE_H
#define EMO_FACE_H

#include "lvgl.h"
#include "emo_skin_types.h"

#ifdef __cplusplus
extern "C" {
#endif

/* 创建全屏黑底 canvas（眼睛画在这里）。失败返回 NULL（PSRAM 分配失败）。 */
lv_obj_t *emo_canvas_create(lv_obj_t *parent, const emo_layout_t *layout);

/* 销毁并释放 buffer（EmojiDisplay 析构路径用不到，防御性提供）*/
void emo_canvas_destroy(void);

/* 切换表情。内部走"闭眼 → 换形 → 睁眼"的 300ms 转场。 */
void emo_set_emotion(emo_id_t id);

/* 手动眨一下 */
void emo_blink(void);

/* 设置眼睛配色（默认冰蓝）*/
void emo_set_color(uint8_t r, uint8_t g, uint8_t b);

/* 开关叠加元素 */
void emo_set_wave(bool on);
void emo_set_auto_blink(bool on);
void emo_set_breathe(bool on);

/* 每帧推进 + 渲染。由 EmojiDisplay 的 lv_timer 调用（33ms）。 */
void emo_tick(void);

/* 说话能量 0..1（驱动 EMO_SPEAK 眼睛跳动）*/
void emo_set_energy(float e);

/* 低电量提示（EMO_LOWBATT 的 pulse 用；基类有电池时由 Tick1s 喂）*/
void emo_set_battery_low(bool low);

/* canvas 是否就绪（buffer 分配成功）*/
bool emo_canvas_ready(void);

#ifdef __cplusplus
}
#endif
#endif /* EMO_FACE_H */

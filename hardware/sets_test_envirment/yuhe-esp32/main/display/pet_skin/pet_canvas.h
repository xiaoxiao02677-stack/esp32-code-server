/* ============================================================
 * pet_canvas.c/.h — 像素宠物绘制（全屏 lv_canvas 自绘）
 *
 * 移植自 hardware/sets/theme/像素宠物/main/src/pet_canvas.c（240x240 独立工程），
 * 差异：
 *   1) 几何全部经 pet_layout_t 换算（240 基准 → 任意屏），不再写死 SCR_W/H；
 *   2) 模块不再持有全局单例 canvas，句柄由 PetSkinDisplay 管理（支持多实例测试）；
 *   3) 表情从"睁/闭眼"二元扩展为 pet_expr_t 五态（协议 emotion 映射）；
 *   4) 绘制 API 增加"仅背景"模式，给壁纸叠加留出通道。
 * ============================================================ */
#ifndef PET_CANVAS_H
#define PET_CANVAS_H

#include "lvgl.h"
#include "pet_skin_types.h"

#ifdef __cplusplus
extern "C" {
#endif

/*
 * 创建宠物 canvas。parent 一般是当前屏幕。返回 canvas 对象（失败 NULL）。
 * buffer 走 PSRAM（240x240x2 ≈ 115KB；320x240 ≈ 153KB），分配失败退内部 RAM，
 * 再失败返回 NULL（调用方应降级：不建宠物层，走基类背景）。
 */
lv_obj_t *pet_canvas_create(lv_obj_t *parent, const pet_layout_t *layout);

/* 销毁并释放 buffer（PetSkinDisplay 析构路径用不到，防御性提供）*/
void pet_canvas_destroy(void);

/* 渲染一帧宠物。
 * prog: 开机进度（NULL = 完成态全 1）
 * energy: 音频能量 0..1（驱动嘴形/耳朵）
 * skin_id / expr / blink: 皮肤 / 表情 / 闭眼帧
 */
void pet_canvas_render(const pet_boot_prog_t *prog, float energy,
                       pet_skin_id_t skin_id, pet_expr_t expr, bool blink);

/* 完成态便捷渲染（等价 render(NULL,...)）*/
void pet_canvas_render_idle(float energy, pet_skin_id_t skin_id, pet_expr_t expr, bool blink);

/* canvas 是否就绪（buffer 分配成功）*/
bool pet_canvas_ready(void);

#ifdef __cplusplus
}
#endif
#endif /* PET_CANVAS_H */

/* ============================================================
 * pet_boot_anim.h — 开机动画进度推进（像素宠物主题）
 * ============================================================ */
#ifndef PET_BOOT_ANIM_H
#define PET_BOOT_ANIM_H

#include "pet_skin_types.h"

#ifdef __cplusplus
extern "C" {
#endif

/* 开机动画结束回调（在 LVGL timer 上下文调用，勿做耗时操作）*/
typedef void (*pet_boot_done_cb_t)(void);

/* 启动开机动画。branch 见 pet_boot_branch_t；done 播放结束回调（可 NULL）。
 * 需循环驱动渲染：调用方（PetSkinDisplay）持 lv_timer 周期调
 * pet_boot_anim_poll() 把最新进度喂给 pet_canvas_render。
 */
void pet_boot_anim_start(pet_boot_branch_t branch, pet_boot_done_cb_t done);
/* 单击跳过（未配网分支不响应；主固件里由 HandleKeyEvent 短按转发）*/
void pet_boot_anim_skip(void);
bool pet_boot_anim_is_done(void);
/* 当前进度（NULL = 已完成，渲染侧置全 1）*/
const pet_boot_prog_t *pet_boot_anim_prog(void);
/* 周期推进（PetSkinDisplay 的 lv_timer 每 tick 调用；内部按系统时钟算进度，
 * 到达终点后触发 done 回调一次并置完成态。不渲染、不碰 LVGL 对象）。*/
void pet_boot_anim_poll(void);

/* 按当前时间选问候语（让每天开机都不重样；未接 RTC 前用随机桶）*/
const char *pet_boot_greeting(void);

#ifdef __cplusplus
}
#endif
#endif /* PET_BOOT_ANIM_H */

#pragma once
/* ============================================================
 * overlay.h — 叠加元素的真实数据源
 *   顶部状态（时间 / Wi-Fi / 电量）+ 底部声波的频段能量
 *
 * 设计原则：
 *   * 每一项都有「真实来源」和「降级方案」，断网/无 ADC 时界面不会崩
 *   * 全部数值由本模块统一产出，绘制层（emopet_face.c）只负责画
 * ============================================================ */
#include <stdint.h>
#include <stdbool.h>

#ifdef __cplusplus
extern "C" {
#endif

/* 声波条数（与 emopet_face.c 的 draw_wave 一致）*/
#define WAVE_BARS     22
/* 频段数：少于条数，绘制时插值，省算力 */
#define WAVE_BANDS     8

typedef struct {
    int      hour, minute;      /* 24h */
    bool     time_valid;        /* 是否已校时（SNTP 成功） */

    int      wifi_level;        /* 0=未连接 1..3=信号格数 */
    bool     wifi_connected;

    int      battery_pct;       /* 0..100 */
    bool     charging;
} overlay_state_t;

/** 初始化：起 RTC / 注册 Wi-Fi 事件监听 / 配置电量 ADC（按 menuconfig）*/
void overlay_init(void);

/** 每帧调用一次（或每 200ms 一次足够）*/
void overlay_update(void);

/** 取当前状态（绘制层只读）*/
const overlay_state_t *overlay_get(void);

/**
 * 取频段能量数组（长度 WAVE_BANDS，每项 0..1）
 * 由音频 RMS 派生：低频慢、高频快，视觉上接近真实频谱，算力几乎为零
 */
void overlay_get_bands(float *out, int n);

/** 平滑后的整体能量 0..1（驱动眼睛跳动）*/
float overlay_get_energy(void);

/** 推入一个音频帧的 RMS（由 audio.c 调用）*/
void overlay_push_rms(float rms);

/** 强制设置电量（无 ADC 时用；也可接你的电量计）*/
void overlay_set_battery(int pct, bool charging);

/** 强制设置时间（无 SNTP 时用，比如从 App 下发）*/
void overlay_set_time(int hour, int minute);

#ifdef __cplusplus
}
#endif

/* ============================================================
 * overlay.c — 叠加元素的真实数据源
 *
 * 三个数据源，每个都有降级方案：
 *   时间  SNTP → RTC → 运行时钟（menuconfig 设初值）
 *   Wi-Fi esp_netif / esp_wifi 事件 → RSSI 映射信号格
 *   电量  ADC1 分压采样 → menuconfig 关掉则用模拟值（缓慢下降）
 *
 * 声波频段：由 RMS 派生 8 个不同时间常数的包络。
 *   —— 不做 FFT（省算力），但低频慢高频快的视觉差异足够像频谱。
 * ============================================================ */
#include <string.h>
#include <math.h>
#include <time.h>
#include <sys/time.h>
#include <stdlib.h>
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "esp_log.h"
#include "esp_timer.h"
#include "esp_system.h"
#include "esp_event.h"
#include "esp_netif.h"
#include "esp_wifi.h"
#include "esp_sntp.h"
#include "nvs_flash.h"
#include "overlay.h"

/* 电量 ADC（可选）*/
#if CONFIG_EMOPET_BATT_ADC_ENABLE
#include "esp_adc/adc_oneshot.h"
#include "esp_adc/adc_cali.h"
#endif

static const char *TAG = "overlay";

static overlay_state_t s_st = {
    .hour = 20, .minute = 14, .time_valid = false,
    .wifi_level = 0, .wifi_connected = false,
    .battery_pct = 78, .charging = false,
};

/* ── 声波频段包络 ─────────────────────────────────────
 * 8 个跟踪器，时间常数从慢到快（低频 → 高频）*/
static float s_band[WAVE_BANDS];
static float s_energy = 0.0f;
/* 各频段的上升/下降系数：低频慢，高频快 */
static const float BAND_ATK[WAVE_BANDS] = {0.18f, 0.24f, 0.30f, 0.38f, 0.46f, 0.55f, 0.64f, 0.72f};
static const float BAND_REL[WAVE_BANDS] = {0.06f, 0.08f, 0.10f, 0.13f, 0.16f, 0.20f, 0.25f, 0.30f};
/* 高频天然能量低，做增益补偿，否则右边几根条永远是矮的 */
static const float BAND_GAIN[WAVE_BANDS] = {1.00f, 1.05f, 1.15f, 1.30f, 1.50f, 1.75f, 2.05f, 2.40f};

static int64_t s_boot_ms = 0;
static uint32_t s_last_min_tick = 0;

#if CONFIG_EMOPET_BATT_ADC_ENABLE
static adc_oneshot_unit_handle_t s_adc = NULL;
#endif

/* ── 时间：SNTP → RTC → 运行时钟 ──────────────────── */
static void time_tick(void)
{
    /* 已校时：直接读系统时间 */
    if (s_st.time_valid) {
        time_t now = 0;
        struct tm tm_now;
        time(&now);
        localtime_r(&now, &tm_now);
        s_st.hour = tm_now.tm_hour;
        s_st.minute = tm_now.tm_min;
        return;
    }
    /* 未校时：用运行时钟 + menuconfig 的初始时间，每分钟 +1 */
    int64_t elapsed_min = (esp_timer_get_time() - s_boot_ms) / (1000LL * 1000LL * 60LL);
    int total = CONFIG_EMOPET_INIT_HOUR * 60 + CONFIG_EMOPET_INIT_MINUTE + (int)elapsed_min;
    total %= (24 * 60);
    s_st.hour = total / 60;
    s_st.minute = total % 60;
}

static void sntp_cb(struct timeval *tv)
{
    (void)tv;
    s_st.time_valid = true;
    ESP_LOGI(TAG, "SNTP 校时成功");
}

static void time_init(void)
{
    s_boot_ms = esp_timer_get_time();
    setenv("TZ", CONFIG_EMOPET_TZ, 1);
    tzset();

#if CONFIG_EMOPET_SNTP_ENABLE
    esp_sntp_setoperatingmode(SNTP_OPMODE_POLL);
    esp_sntp_setservername(0, CONFIG_EMOPET_SNTP_SERVER);
    esp_sntp_init();
    sntp_set_time_sync_notification_cb(sntp_cb);
    ESP_LOGI(TAG, "SNTP 已启动：%s", CONFIG_EMOPET_SNTP_SERVER);
#else
    ESP_LOGW(TAG, "SNTP 未启用，使用 menuconfig 初始时间 %02d:%02d",
             CONFIG_EMOPET_INIT_HOUR, CONFIG_EMOPET_INIT_MINUTE);
#endif
    time_tick();
}

/* ── Wi-Fi：事件驱动 + RSSI 映射信号格 ─────────────── */
static void wifi_event_handler(void *arg, esp_event_base_t base,
                              int32_t id, void *data)
{
    (void)arg; (void)base; (void)data;
    if (id == WIFI_EVENT_STA_START || id == WIFI_EVENT_STA_DISCONNECTED) {
        s_st.wifi_connected = false;
        s_st.wifi_level = 0;
    } else if (id == IP_EVENT_STA_GOT_IP) {
        s_st.wifi_connected = true;
        s_st.wifi_level = 3;      /* 拿到 IP；具体格数由 RSSI 更新覆盖 */
    }
}

static void wifi_init(void)
{
    ESP_ERROR_CHECK(esp_event_handler_register(WIFI_EVENT, ESP_EVENT_ANY_ID,
                                               &wifi_event_handler, NULL));
    ESP_ERROR_CHECK(esp_event_handler_register(IP_EVENT, ESP_EVENT_ANY_ID,
                                               &wifi_event_handler, NULL));
}

static void wifi_poll(void)
{
    if (!s_st.wifi_connected) { s_st.wifi_level = 0; return; }
    wifi_ap_record_t ap;
    if (esp_wifi_sta_get_ap_info(&ap) != ESP_OK) { s_st.wifi_level = 1; return; }
    /* RSSI → 格数：-55 以上满格，-75 以下 1 格 */
    int r = ap.rssi;
    s_st.wifi_level = (r >= -55) ? 3 : ((r >= -68) ? 2 : 1);
}

/* ── 电量：ADC 或模拟 ─────────────────────────────── */
#if CONFIG_EMOPET_BATT_ADC_ENABLE
static void batt_adc_init(void)
{
    adc_oneshot_unit_init_cfg_t u = {
        .unit_id = ADC_UNIT_1,
        .ulp_mode = ADC_ULP_MODE_DISABLE,
    };
    if (adc_oneshot_new_unit(&u, &s_adc) != ESP_OK) {
        ESP_LOGW(TAG, "ADC 初始化失败，退回模拟电量");
        s_adc = NULL;
    }
    adc_oneshot_chan_cfg_t c = {
        .atten = ADC_ATTEN_DB_12,
        .bitwidth = ADC_BITWIDTH_12,
    };
    if (s_adc) {
        adc_oneshot_config_channel(s_adc, CONFIG_EMOPET_BATT_ADC_CHANNEL, &c);
    }
}

static int batt_read_mv(void)
{
    if (!s_adc) return -1;
    int raw = 0;
    if (adc_oneshot_read(s_adc, CONFIG_EMOPET_BATT_ADC_CHANNEL, &raw) != ESP_OK) return -1;
    /* raw(0..4095) → mV：ESP32-S3 12dB 衰减约 0..3100mV 量程 */
    int mv = (raw * 3100) / 4095;
    /* 若前端是 1:1 分压（如 100k/100k），实际电压要 ×2 */
    return mv * CONFIG_EMOPET_BATT_DIVIDER_NUM / CONFIG_EMOPET_BATT_DIVIDER_DEN;
}
#endif

/* 模拟电量：无 ADC 时缓慢下降，插 USB 时回充（用 VBUS 检测不可靠，这里按"运行中即缓慢耗电"处理）*/
static void batt_sim_tick(void)
{
    static int64_t last = 0;
    int64_t now = esp_timer_get_time();
    if (last == 0) { last = now; return; }
    /* 每 90 秒掉 1% —— 纯装饰，让你看到电量在动；接真实电量计后删掉 */
    if (now - last > 90LL * 1000LL * 1000LL) {
        last = now;
        if (!s_st.charging && s_st.battery_pct > 5) s_st.battery_pct--;
    }
}

static void batt_poll(void)
{
#if CONFIG_EMOPET_BATT_ADC_ENABLE
    int mv = batt_read_mv();
    if (mv > 0) {
        /* 锂电池 3.0V(0%) ~ 4.2V(100%)，按你的电池改这两个值 */
        const int min_mv = CONFIG_EMOPET_BATT_MIN_MV;
        const int max_mv = CONFIG_EMOPET_BATT_MAX_MV;
        int pct = (mv - min_mv) * 100 / (max_mv - min_mv);
        if (pct < 0) pct = 0;
        if (pct > 100) pct = 100;
        s_st.battery_pct = pct;
        /* 充电判定：电压接近满且缓慢上升；真机建议读充电 IC 的状态脚 */
        s_st.charging = (mv >= max_mv - 30);
        return;
    }
#endif
    batt_sim_tick();
}

/* ═══════════════════════════════════════════════════
 * 声波频段：RMS → 8 段包络
 * ═══════════════════════════════════════════════════ */
void overlay_push_rms(float rms)
{
    /* 整体能量：上升快、回落慢 —— 这一步决定动画耐不耐看 */
    static float smooth = 0.0f;
    smooth = (rms > smooth) ? (smooth * 0.35f + rms * 0.65f)
                            : (smooth * 0.88f + rms * 0.12f);
    s_energy = smooth * 8.0f;
    if (s_energy > 1.0f) s_energy = 1.0f;

    float tsec = (float)esp_timer_get_time() / 1000000.0f;   /* 秒 */
    for (int i = 0; i < WAVE_BANDS; i++) {
        /* 各频段的相位/频率差异 → 视觉上像真实频谱的起伏。
           注意用「秒」为单位：若用毫秒，抖动会快到变成噪点闪烁。 */
        float jit = 0.75f + 0.25f * sinf(tsec * (3.0f + (float)i * 1.5f) + (float)i);
        float v = rms * 8.0f * BAND_GAIN[i] * jit;
        if (v > 1.0f) v = 1.0f;
        s_band[i] = (v > s_band[i]) ? (s_band[i] + (v - s_band[i]) * BAND_ATK[i])
                                    : (s_band[i] + (v - s_band[i]) * BAND_REL[i]);
    }
}

void overlay_get_bands(float *out, int n)
{
    /* 8 段线性插值到 n 根条（n 通常 = 22）*/
    for (int i = 0; i < n; i++) {
        float p = (float)i / (float)(n - 1) * (float)(WAVE_BANDS - 1);
        int   i0 = (int)p;
        int   i1 = (i0 + 1 < WAVE_BANDS) ? (i0 + 1) : (WAVE_BANDS - 1);
        float f  = p - (float)i0;
        out[i] = s_band[i0] * (1.0f - f) + s_band[i1] * f;
    }
}

float overlay_get_energy(void) { return s_energy; }

/* ═══════════════════════════════════════════════════
 * 生命周期
 * ═══════════════════════════════════════════════════ */
void overlay_init(void)
{
    memset(s_band, 0, sizeof(s_band));
    time_init();
    wifi_init();
#if CONFIG_EMOPET_BATT_ADC_ENABLE
    batt_adc_init();
#endif
    ESP_LOGI(TAG, "overlay 就绪：SNTP=%d 电量ADC=%d",
             (int)CONFIG_EMOPET_SNTP_ENABLE,
             (int)CONFIG_EMOPET_BATT_ADC_ENABLE);
}

void overlay_update(void)
{
    time_tick();
    wifi_poll();
    batt_poll();
}

const overlay_state_t *overlay_get(void) { return &s_st; }

void overlay_set_battery(int pct, bool charging)
{
    if (pct < 0) pct = 0;
    if (pct > 100) pct = 100;
    s_st.battery_pct = pct;
    s_st.charging = charging;
}

void overlay_set_time(int hour, int minute)
{
    if (hour < 0 || hour > 23 || minute < 0 || minute > 59) return;
    s_st.hour = hour;
    s_st.minute = minute;
    s_st.time_valid = true;
}

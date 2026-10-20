/* ============================================================
 * main.c — EMOPET 风格机器人脸
 * 硬件：ESP32-S3 + 240x240 方形 IPS (ST7789) + 三键 + I2S 麦克风
 *
 * 按键语义（调试版，接真实对话后按需改）：
 *   BOOT 单击   → 说话（切换 SPEAK 表情）
 *   BOOT 双击   → 随机给一个"情绪"表情
 *   BOOT 长按   → 待机 / 配网二维码
 *   VOL+ / VOL- → 上/下一个表情（浏览表情库，调试用）
 *   VOL- 长按   → 换眼睛颜色
 * ============================================================ */
#include <string.h>
#include "esp_log.h"
#include "esp_random.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "nvs_flash.h"
#include "esp_system.h"
#include "esp_sleep.h"
#include "esp_lvgl_port.h"
#include "app_config.h"
#include "emopet_ui.h"
#include "overlay.h"

static const char *TAG = "emopet";

static uint8_t   s_emo = EMO_IDLE;
static uint32_t  s_state_ms = 0;
static bool      s_ready = false;
static bool      s_st_on = true;    /* 顶部状态 */
static bool      s_wv_on = true;    /* 底部声波 */
static bool      s_bk_on = true;    /* 自动眨眼 */
static bool      s_br_on = true;    /* 呼吸缩放 */

/* 眼睛配色预设（VOL- 长按轮换）*/
static const uint8_t PAL[][3] = {
    { 47, 216, 255 },   /* 冰蓝（EMOPET 默认）*/
    { 53, 240, 208 },   /* 青绿 */
    { 169, 123, 255 },  /* 紫   */
    { 255, 111, 181 },  /* 粉   */
    { 255, 162, 58 },   /* 琥珀 */
    { 107, 255, 142 },  /* 翠绿 */
};
static int s_pal = 0;

/* ── 渲染循环 30fps ────────────────────────────────── */
/* overlay 刷新较慢（1s 一次足够），单独一个 timer，不占渲染帧 */
static void overlay_timer(lv_timer_t *t)
{
    (void)t;
    overlay_update();
}

static void render_timer(lv_timer_t *t)
{
    (void)t;
    /* 眼睛跳动用整体能量；底部声波用 overlay 的频段（由 audio.c 推送）*/
    emopet_set_energy(overlay_get_energy());
    emopet_tick();

    /* 演示回路：说话 3 秒后自动回待机（接真实对话后删除）*/
    if (s_ready && s_emo == EMO_SPEAK) {
        if ((lv_tick_get() - s_state_ms) > 3000) {
            s_emo = EMO_IDLE;
            emopet_set_emotion(EMO_IDLE);
        }
    }
}

static void enter(emo_id_t id)
{
    s_emo = (uint8_t)id;
    s_state_ms = lv_tick_get();
    emopet_set_emotion(id);
}

static void on_key(key_event_t e)
{
    if (lvgl_port_lock(100) != ESP_OK) return;

    switch (e) {
    case KEY_EVT_BOOT_SINGLE:
        /* 接真实对话时：这里开始录音并上传 */
        enter((s_emo == EMO_LISTEN) ? EMO_THINK : EMO_LISTEN);
        break;

    case KEY_EVT_BOOT_DOUBLE:
        /* 双击：随机来一个情绪表情（演示）*/
        {
            static const emo_id_t pool[] = { EMO_HAPPY, EMO_LOVE, EMO_STAR,
                                             EMO_WINK, EMO_SHY, EMO_SURPRISE };
            enter(pool[esp_random() % 6]);
        }
        break;

    case KEY_EVT_BOOT_LONG:
        enter((s_emo == EMO_WIFI) ? EMO_IDLE : EMO_WIFI);
        break;

    case KEY_EVT_VOLUP_SINGLE:
        /* 上一个表情（调试浏览）*/
        s_emo = (s_emo == 0) ? (EMO_MAX - 1) : (s_emo - 1);
        enter((emo_id_t)s_emo);
        break;

    case KEY_EVT_VOLDN_SINGLE:
        s_emo = (s_emo + 1) % EMO_MAX;
        enter((emo_id_t)s_emo);
        break;

    /* ── 叠加元素开关（长按）────────────────────── */
    case KEY_EVT_VOLUP_LONG:
        s_st_on = !s_st_on;
        emopet_set_status_bar(s_st_on);
        ESP_LOGI(TAG, "顶部状态：%s", s_st_on ? "开" : "关");
        break;

    case KEY_EVT_BOTH_VOL:
        s_wv_on = !s_wv_on;
        emopet_set_wave(s_wv_on);
        ESP_LOGI(TAG, "底部声波：%s", s_wv_on ? "开" : "关");
        break;

    case KEY_EVT_VOLDN_LONG:
        s_pal = (s_pal + 1) % (int)(sizeof(PAL)/sizeof(PAL[0]));
        emopet_set_color(PAL[s_pal][0], PAL[s_pal][1], PAL[s_pal][2]);
        ESP_LOGI(TAG, "眼睛颜色 → %d", s_pal);
        break;

    default: break;
    }

    lvgl_port_unlock();
}

void app_main(void)
{
    ESP_LOGI(TAG, "EMOPET 风格机器人脸启动 (IDF %s)", esp_get_idf_version());
    ESP_ERROR_CHECK(nvs_flash_init());

    /* ── 1. 显示（内部：灭背光 → 清屏 → 开背光）────── */
    if (!display_init()) { ESP_LOGE(TAG, "显示初始化失败"); return; }

    /* ── 2. 脸（canvas 自绘）───────────────────────── */
    if (!emopet_canvas_create(lv_screen_active())) { ESP_LOGE(TAG, "canvas 创建失败"); return; }

    /* ── 3. 叠加元素数据源（时间 / Wi-Fi / 电量 / 频段）── */
    overlay_init();

    /* ── 4. 四个叠加元素：默认全开，运行时可用按键切换 ── */
    emopet_set_status_bar(s_st_on);
    emopet_set_wave(s_wv_on);
    emopet_set_auto_blink(s_bk_on);
    emopet_set_breathe(s_br_on);

    /* ── 4. 音频 ──────────────────────────────────── */
    audio_start();

    /* ── 5. 按键 ──────────────────────────────────── */
    keys_init(on_key);

    /* ── 6. 渲染循环 30fps + overlay 1s 刷新 ────────── */
    lv_timer_create(render_timer, 33, NULL);
    lv_timer_create(overlay_timer, 1000, NULL);

    /* ── 7. 开机：从黑屏里亮起来 ───────────────────── */
    emopet_set_emotion(EMO_BOOT);
    s_ready = true;
    /* 1.2s 后转入待机（真实项目可换成 NVS 判断是否首次开机 → 走配网）*/
    vTaskDelay(pdMS_TO_TICKS(1200));
    if (lvgl_port_lock(pdMS_TO_TICKS(200)) == ESP_OK) {
        enter(EMO_IDLE);
        lvgl_port_unlock();
    }

    ESP_LOGI(TAG, "就绪。BOOT=说话/双击情绪/长按配网  VOL±=浏览表情");
    ESP_LOGI(TAG, "      VOL+长按=顶部状态  双VOL同按=底部声波  VOL-长按=换眼色");
}

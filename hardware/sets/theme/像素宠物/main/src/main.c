/* ============================================================
 * main.c — 女友聊天机 · 方案 A（软萌像素宠物）
 * 硬件：ESP32-S3 + 240x240 方形 IPS (ST7789) + 三键 + I2S 麦克风
 * ============================================================ */
#include <string.h>
#include "esp_log.h"
#include "esp_random.h"
#include "nvs_flash.h"
#include "esp_sleep.h"
#include "esp_system.h"
#include "esp_lvgl_port.h"
#include "app_config.h"
#include "pet_ui.h"

static const char *TAG = "pet_chat";

static pet_skin_t  s_skin  = PET_SKIN_CAT;
static ui_state_t  s_state = UI_ST_IDLE;
static uint32_t    s_state_ms = 0;      /* 进入当前状态的时间戳 */
static bool        s_boot_done = false;

/* ── 每帧渲染：读进度 + 能量 + 皮肤，画到 canvas ───── */
static void render_timer(lv_timer_t *t)
{
    (void)t;

    /* 随机眨眼：不规律才像活的 */
    static int  next_blink = 60;
    static uint8_t blink_frames = 0;
    static bool blink = false;
    if (--next_blink <= 0) {
        blink = true;
        blink_frames = 4;                        /* 约 130ms @30fps */
        next_blink = 60 + (int)(esp_random() % 120);
    }
    if (blink_frames > 0 && --blink_frames == 0) blink = false;

    pet_canvas_render(boot_anim_prog(), audio_get_energy(), s_skin, blink);

    /* 演示回路：无网络时的状态流转（接真实对话后删除此段） */
    if (s_boot_done && s_state != UI_ST_MENU) {
        uint32_t now = lv_tick_get();
        if (s_state == UI_ST_LISTEN && now - s_state_ms > 2000) {
            ui_set_state(UI_ST_SPEAK);
            ui_show_bubble("我也很想你呀~");
            s_state_ms = now;
        } else if (s_state == UI_ST_SPEAK && now - s_state_ms > 3500) {
            ui_show_bubble(NULL);
            ui_set_state(UI_ST_IDLE);
            s_state_ms = now;
        }
    }
}

static void enter_state(ui_state_t st)
{
    s_state = st;
    s_state_ms = lv_tick_get();
    ui_set_state(st);
}

/* ── 按键 → 状态机 ────────────────────────────────── */
static void on_key(key_event_t e)
{
    if (lvgl_port_lock(100) != ESP_OK) return;   /* 拿不到锁就丢，避免卡死 keys 任务 */

    /* 开机动画期间：单击 BOOT 跳过（首开机未配网分支不响应）*/
    if (!boot_anim_is_done()) {
        if (e == KEY_EVT_BOOT_SINGLE) boot_anim_skip();
        lvgl_port_unlock();
        return;
    }

    switch (e) {
    case KEY_EVT_BOOT_SINGLE:
        if (s_state == UI_ST_MENU) {
            ui_menu_confirm();
        } else if (s_state == UI_ST_IDLE) {
            enter_state(UI_ST_LISTEN);
        } else if (s_state == UI_ST_LISTEN) {
            /* 结束录音并发送 —— 这里接你的语音上传逻辑 */
            enter_state(UI_ST_THINK);
        } else {
            ui_show_bubble(NULL);
            enter_state(UI_ST_IDLE);
        }
        break;

    case KEY_EVT_BOOT_DOUBLE:
        /* 发送预录语音「想你了」—— 建议用你自己录的声音 */
        ESP_LOGI(TAG, "双击：发送预录语音");
        enter_state(UI_ST_SPEAK);
        ui_show_bubble("想你了");
        break;

    case KEY_EVT_BOOT_LONG:
        if (s_state == UI_ST_MENU) enter_state(UI_ST_IDLE);
        else { enter_state(UI_ST_MENU); ui_menu_move(0); }
        break;

    case KEY_EVT_VOLUP_SINGLE:
        if (s_state == UI_ST_MENU) ui_menu_move(-1);
        else ui_set_volume(6);      /* 接你的音量逻辑 */
        break;

    case KEY_EVT_VOLDN_SINGLE:
        if (s_state == UI_ST_MENU) ui_menu_move(1);
        else ui_set_volume(5);
        break;

    case KEY_EVT_VOLUP_LONG:
        ESP_LOGI(TAG, "VOL+ 长按：亮度 +10%%");
        break;

    case KEY_EVT_VOLDN_LONG:
        s_skin = (pet_skin_t)((s_skin + 1) % PET_SKIN_MAX);   /* 换表情 */
        ESP_LOGI(TAG, "换表情 skin=%d", (int)s_skin);
        break;

    case KEY_EVT_BOTH_VOL:
        ESP_LOGI(TAG, "双键同按：夜间模式 / 静音");
        break;

    default: break;
    }

    lvgl_port_unlock();
}

/* ── 开机动画结束回调 ─────────────────────────────── */
static void on_boot_done(void)
{
    s_boot_done = true;
    ui_reveal_after_boot();
    ESP_LOGI(TAG, "进入待机：%s", boot_greeting());
}

void app_main(void)
{
    ESP_LOGI(TAG, "女友聊天机 · 方案 A 启动 (IDF %s)", esp_get_idf_version());

    ESP_ERROR_CHECK(nvs_flash_init());

    /* ── 1. 显示（内部已处理：灭背光 → 清屏 → 开背光）── */
    lv_display_t *disp = display_init();
    if (!disp) { ESP_LOGE(TAG, "显示初始化失败"); return; }

    /* ── 2. 宠物 canvas（自绘层）───────────────────── */
    if (!pet_canvas_create(lv_screen_active())) { ESP_LOGE(TAG, "canvas 创建失败"); return; }

    /* ── 3. 控件层 ────────────────────────────────── */
    ui_screens_init(NULL);

    /* ── 4. 音频 ──────────────────────────────────── */
    audio_start();

    /* ── 5. 按键 ──────────────────────────────────── */
    keys_init(on_key);

    /* ── 6. 渲染循环 30fps（LVGL 线程内，安全）─────── */
    lv_timer_create(render_timer, 33, NULL);

    /* ── 7. 开机动画 ──────────────────────────────── */
#if CONFIG_PET_BOOT_ANIM_ENABLE
    boot_branch_t br = BOOT_FULL;
    esp_sleep_wakeup_cause_t cause = esp_sleep_get_wakeup_cause();
    if (cause != ESP_SLEEP_WAKEUP_UNDEFINED) {
        br = BOOT_WAKE;                       /* 深度唤醒：0.6s 短版 */
    } else {
        /* 首开机（NVS 无标记）→ 走未配网分支，结尾显示二维码 */
        uint8_t booted = 0;
        nvs_handle_t h;
        if (nvs_open("pet", NVS_READONLY, &h) == ESP_OK) {
            nvs_get_u8(h, "booted", &booted);
            nvs_close(h);
        }
        if (!booted) {
            br = BOOT_WIFI;
            nvs_open("pet", NVS_READWRITE, &h);
            nvs_set_u8(h, "booted", 1);
            nvs_commit(h);
            nvs_close(h);
        }
    }
    boot_anim_start(br, on_boot_done);
#else
    on_boot_done();
#endif

    ESP_LOGI(TAG, "就绪。BOOT 单击=说话 / 长按=菜单；VOL±=音量；VOL- 长按=换表情");
}

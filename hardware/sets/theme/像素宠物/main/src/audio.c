/* ============================================================
 * audio.c — I2S 麦克风采集 + RMS 能量
 * ESP-IDF v6.1 已移除 legacy I2S，这里用 esp_driver_i2s 的 std API
 * ============================================================ */
#include <math.h>
#include <string.h>
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "esp_log.h"
#include "driver/i2s_std.h"
#include "driver/i2s_common.h"
#include "app_config.h"
#include "pet_ui.h"

static const char *TAG = "audio";

#define BUF_SAMPLES 256

static i2s_chan_handle_t s_rx = NULL;
static float s_energy = 0.0f;
static float s_smooth = 0.0f;

static void audio_task(void *arg)
{
    (void)arg;
    int32_t buf[BUF_SAMPLES];
    size_t  bytes_read = 0;

    while (1) {
        if (i2s_channel_read(s_rx, buf, sizeof(buf), &bytes_read, pdMS_TO_TICKS(100)) != ESP_OK) {
            vTaskDelay(pdMS_TO_TICKS(10));
            continue;
        }
        int n = (int)(bytes_read / sizeof(int32_t));
        if (n <= 0) continue;

        float sum = 0.0f;
        for (int i = 0; i < n; i++) {
            /* INMP441 输出 24bit in 32bit frame，取高 16 位即可 */
            float s = (float)(buf[i] >> 16) / 32768.0f;
            sum += s * s;
        }
        float rms = sqrtf(sum / (float)n);
        /* 上升快、回落慢 —— 这一步决定动画耐不耐看 */
        s_smooth = (rms > s_smooth) ? (s_smooth * 0.35f + rms * 0.65f)
                                    : (s_smooth * 0.88f + rms * 0.12f);
        s_energy = fminf(1.0f, s_smooth * 8.0f);

        vTaskDelay(pdMS_TO_TICKS(20));   /* 50Hz 更新 */
    }
}

static void fake_task(void *arg)
{
    (void)arg;
    /* 无麦克风时的模拟能量：1.2Hz 呼吸 + 噪声感，用于调试动画 */
    float t = 0.0f;
    while (1) {
        t += 0.02f;
        float v = 0.5f + 0.45f * sinf(t * 2.0f * 3.14159265f * 1.2f);
        s_energy = v;
        vTaskDelay(pdMS_TO_TICKS(20));
    }
}

float audio_get_energy(void) { return s_energy; }

void audio_start(void)
{
#if !CONFIG_MIC_ENABLE
    ESP_LOGW(TAG, "麦克风未启用，使用模拟能量");
    xTaskCreatePinnedToCore(fake_task, "audio_fake", 2048, NULL, 5, NULL, 1);
    return;
#endif
#if CONFIG_PET_FAKE_AUDIO
    ESP_LOGW(TAG, "PET_FAKE_AUDIO=y，使用模拟能量");
    xTaskCreatePinnedToCore(fake_task, "audio_fake", 2048, NULL, 5, NULL, 1);
    return;
#endif

    i2s_chan_config_t chan = I2S_CHANNEL_DEFAULT_CONFIG((i2s_port_t)CONFIG_MIC_I2S_NUM, I2S_ROLE_MASTER);
    chan.dma_desc_num = 6;
    chan.dma_frame_num = BUF_SAMPLES;
    ESP_ERROR_CHECK(i2s_new_channel(&chan, NULL, &s_rx));

    i2s_std_config_t std = {
        .clk_cfg  = I2S_STD_CLK_DEFAULT_CONFIG(CONFIG_MIC_SAMPLE_RATE),
        .slot_cfg = I2S_STD_PHILIPS_SLOT_DEFAULT_CONFIG(I2S_DATA_BIT_WIDTH_32BIT, I2S_SLOT_MODE_MONO),
        .gpio_cfg = {
            .mclk = GPIO_NUM_NC,
            .bclk = (gpio_num_t)CONFIG_MIC_PIN_BCLK,
            .ws   = (gpio_num_t)CONFIG_MIC_PIN_WS,
            .dout = GPIO_NUM_NC,
            .din  = (gpio_num_t)CONFIG_MIC_PIN_DIN,
            .invert_flags = { .mclk_inv = false, .bclk_inv = false, .ws_inv = false },
        },
    };
    ESP_ERROR_CHECK(i2s_channel_init_std_mode(s_rx, &std));
    ESP_ERROR_CHECK(i2s_channel_enable(s_rx));

    xTaskCreatePinnedToCore(audio_task, "audio", 4096, NULL, 6, NULL, 1);
    ESP_LOGI(TAG, "I2S mic ready: bclk=%d ws=%d din=%d",
             CONFIG_MIC_PIN_BCLK, CONFIG_MIC_PIN_WS, CONFIG_MIC_PIN_DIN);
}

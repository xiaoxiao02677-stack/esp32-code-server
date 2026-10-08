#include "wifi_board.h"
#include "codecs/no_audio_codec.h"
#include "display/lcd_display.h"
#include "application.h"
#include "button.h"
#include "config.h"
#include "round_screen_display.h"

#ifdef CONFIG_YH_PROTOCOL_ENABLED
#include "yh/yh_ws2812_led.h"
#endif

#include <esp_log.h>
#include <esp_lcd_panel_vendor.h>
#include <esp_lcd_panel_io.h>
#include <esp_lcd_panel_ops.h>
#include <driver/spi_common.h>
#include <esp_timer.h>

#define TAG "MyS3TftBoard"

class MyS3TftBoard : public WifiBoard {
private:
    Button boot_button_;
    RoundScreenDisplay* display_;
    esp_timer_handle_t tick_timer_ = nullptr;

    void InitializeSpi() {
        spi_bus_config_t buscfg = {};
        buscfg.mosi_io_num = DISPLAY_MOSI_PIN;
        buscfg.miso_io_num = GPIO_NUM_NC;
        buscfg.sclk_io_num = DISPLAY_CLK_PIN;
        buscfg.quadwp_io_num = GPIO_NUM_NC;
        buscfg.quadhd_io_num = GPIO_NUM_NC;
        buscfg.max_transfer_sz = DISPLAY_WIDTH * DISPLAY_HEIGHT * sizeof(uint16_t);
        ESP_ERROR_CHECK(spi_bus_initialize(SPI3_HOST, &buscfg, SPI_DMA_CH_AUTO));
    }

    void InitializeLcdDisplay() {
        esp_lcd_panel_io_handle_t panel_io = nullptr;
        esp_lcd_panel_handle_t panel = nullptr;

        esp_lcd_panel_io_spi_config_t io_config = {};
        io_config.cs_gpio_num = DISPLAY_CS_PIN;
        io_config.dc_gpio_num = DISPLAY_DC_PIN;
        io_config.spi_mode = DISPLAY_SPI_MODE;
        io_config.pclk_hz = 40 * 1000 * 1000;
        io_config.trans_queue_depth = 10;
        io_config.lcd_cmd_bits = 8;
        io_config.lcd_param_bits = 8;
        ESP_ERROR_CHECK(esp_lcd_new_panel_io_spi(SPI3_HOST, &io_config, &panel_io));

        esp_lcd_panel_dev_config_t panel_config = {};
        panel_config.reset_gpio_num = DISPLAY_RST_PIN;
        panel_config.rgb_ele_order = DISPLAY_RGB_ORDER;
        panel_config.bits_per_pixel = 16;
        ESP_ERROR_CHECK(esp_lcd_new_panel_st7789(panel_io, &panel_config, &panel));

        // A failed reset/init leaves a black screen with no other trace; abort
        // with a logged backtrace so the cause is visible after reboot.
        ESP_ERROR_CHECK(esp_lcd_panel_reset(panel));
        ESP_ERROR_CHECK(esp_lcd_panel_init(panel));
        esp_lcd_panel_invert_color(panel, DISPLAY_INVERT_COLOR);
        esp_lcd_panel_swap_xy(panel, DISPLAY_SWAP_XY);
        esp_lcd_panel_mirror(panel, DISPLAY_MIRROR_X, DISPLAY_MIRROR_Y);
        ESP_LOGI(TAG, "LCD ready (%dx%d)", DISPLAY_WIDTH, DISPLAY_HEIGHT);

        // 圆屏皮肤：240x240 安全区布局（时间/电量/表情/气泡/提示 + 深紫渐变）
        display_ = new RoundScreenDisplay(panel_io, panel,
                                          DISPLAY_WIDTH, DISPLAY_HEIGHT, DISPLAY_OFFSET_X,
                                          DISPLAY_OFFSET_Y, DISPLAY_MIRROR_X, DISPLAY_MIRROR_Y,
                                          DISPLAY_SWAP_XY);
    }

    // 单 BOOT 键三事件（需求交互表）：
    // - 短按：待机/说话 -> Application::ToggleChatState()（原逻辑不变，开/打断）
    // - 双击：待机 -> 表情彩蛋（RoundScreenDisplay::NextEasterEgg）
    // - 长按 1s：Starting -> 配网（原逻辑，见下方说明）
    //
    // ⚠️ 2026-10-08 修复：Button 构造默认 long_press_time=0 会回退到
    // iot_button 注册校验里被强制为 short_press_ticks(180ms)——普通短按即触发
    // 长按回调，而回调里的 EnterWifiConfigMode 在设备卡 Starting（配网后未连上
    // 服务器）时形成"按键即重配网"死循环。修复：显式 1000ms + 长按只在
    // Starting 早期（刚开机 30s 内）允许进配网。
    void InitializeButtons() {
        boot_button_.OnClick([this]() {
            auto& app = Application::GetInstance();
            if (app.GetDeviceState() == kDeviceStateStarting) {
                // 保留原逻辑：Starting 状态下短按进配网（首次开机场景）
                EnterWifiConfigMode();
                return;
            }
            app.ToggleChatState();
            display_->HandleKeyEvent(0);
        });
        boot_button_.OnDoubleClick([this]() {
            display_->HandleKeyEvent(1);
        });
        boot_button_.OnLongPress([this]() {
            auto& app = Application::GetInstance();
            auto state = app.GetDeviceState();
            ESP_LOGI(TAG, "BOOT long-press (state=%d)", static_cast<int>(state));
            if (state == kDeviceStateStarting) {
                // 仅开机前 30 秒允许长按配网；此后 Starting 中的长按视为误触忽略，
                // 避免服务器连接慢时"按键重进配网"循环
                int64_t uptime_ms = esp_timer_get_time() / 1000;
                if (uptime_ms < 30000) {
                    EnterWifiConfigMode();
                } else {
                    ESP_LOGW(TAG, "Long-press ignored in Starting (uptime %lldms > 30s)",
                              (long long)uptime_ms);
                }
                return;
            }
            if (state == kDeviceStateListening || state == kDeviceStateSpeaking) {
                // 聆听中：取消录音；说话中：打断 TTS —— 均经 ToggleChatState 返回待机
                app.ToggleChatState();
            } else if (state == kDeviceStateIdle) {
                // 待机长按：静音切换
                auto codec = Board::GetInstance().GetAudioCodec();
                int v = codec->output_volume();
                int nv = (v == 0) ? 70 : 0;
                codec->SetOutputVolume(nv);
                ESP_LOGI(TAG, "Long-press mute toggle: %d -> %d", v, nv);
            }
            display_->HandleKeyEvent(2);
        });
    }

    // 1 秒节拍：圆屏自动行为（夜间/早晨/低电量提醒 + 彩蛋超时恢复）
    void InitializeTickTimer() {
        esp_timer_create_args_t args = {
            .callback =
                [](void* arg) {
                    auto* disp = static_cast<RoundScreenDisplay*>(arg);
                    disp->Tick1s();
                },
            .arg = display_,
            .dispatch_method = ESP_TIMER_TASK,
            .name = "round_ui_tick",
            .skip_unhandled_events = true,
        };
        ESP_ERROR_CHECK(esp_timer_create(&args, &tick_timer_));
        ESP_ERROR_CHECK(esp_timer_start_periodic(tick_timer_, 1000000));  // 1s
    }

public:
    // 显式 long_press_time=1000ms：Button 构造默认 0 会回退到 iot_button
    // 注册校验强制值（= short_press_ticks 180ms），导致普通按压被误判为长按
    MyS3TftBoard() : boot_button_(BOOT_BUTTON_GPIO, false, 1000) {
        InitializeSpi();
        InitializeLcdDisplay();
        InitializeButtons();
        InitializeTickTimer();
        GetBacklight()->RestoreBrightness();

        // MAX98357A: VIN=3.3V, GAIN 接地 -> 实际增益 12dB (5V 供电才是 15dB)。
        // SD 接 3.3V 常使能(>1.4V 时输出左声道, 与 VIN 同网)。
        // 音量不在此处设置: 开机音量由 AudioCodec 从 NVS (audio/output_volume) 恢复,
        // 服务器连接后还会下发云端配置 (device_config) 覆盖本地值。

        ESP_LOGI(TAG, "Board init done (round-screen UI, audio in=%d Hz, out=%d Hz)",
                 AUDIO_INPUT_SAMPLE_RATE, AUDIO_OUTPUT_SAMPLE_RATE);
    }

    virtual AudioCodec* GetAudioCodec() override {
        static NoAudioCodecSimplex audio_codec(AUDIO_INPUT_SAMPLE_RATE, AUDIO_OUTPUT_SAMPLE_RATE,
            AUDIO_I2S_SPK_GPIO_BCLK, AUDIO_I2S_SPK_GPIO_LRCK, AUDIO_I2S_SPK_GPIO_DOUT, AUDIO_I2S_MIC_GPIO_SCK, AUDIO_I2S_MIC_GPIO_WS, AUDIO_I2S_MIC_GPIO_DIN);
        return &audio_codec;
    }

    virtual Display* GetDisplay() override {
        return display_;
    }

    virtual Backlight* GetBacklight() override {
        static PwmBacklight backlight(DISPLAY_BACKLIGHT_PIN, DISPLAY_BACKLIGHT_OUTPUT_INVERT);
        return &backlight;
    }

#ifdef CONFIG_YH_PROTOCOL_ENABLED
    // YH Device Protocol: 独立 WS2812 句柄（DevKitC-1 板载 RGB LED, GPIO48）
    virtual YhWs2812Led* GetWs2812Led() override {
        static YhWs2812Led yh_led(YH_WS2812_GPIO);
        return &yh_led;
    }
#endif
};

DECLARE_BOARD(MyS3TftBoard);

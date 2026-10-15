#include "wifi_board.h"
#include "codecs/no_audio_codec.h"
#include "display/lcd_display.h"
#include "display/oled_display.h"
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
#ifdef DISPLAY_FB_SSD1306_USE_SH1106
#include <esp_lcd_panel_sh1106.h>
#endif
#include <driver/spi_common.h>
#include <driver/i2c_master.h>
#include <esp_timer.h>

#define TAG "MyS3TftBoard"

class MyS3TftBoard : public WifiBoard {
private:
    Button boot_button_;
    Display* display_;  // 主屏=RoundScreenDisplay, 备用屏=OledDisplay(SSD1306)
    esp_timer_handle_t tick_timer_ = nullptr;
    bool use_fallback_ssd1306_ = false;

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

    // 备用屏方案: SSD1306 128x64 I2C OLED, 独立引脚 SCL=9/SDA=8,
    // 仅 VCC(3V3)/GND 供电. 探测到 0x3C 即采用, 否则返回 false 走主屏.
    bool TryInitializeFallbackSsd1306() {
        // 探测前先保护主屏: CS 拉高(不选中)、RST 拉高(不复位),
        // 避免上电初期主屏处于未定义状态
        gpio_set_direction(DISPLAY_CS_PIN, GPIO_MODE_OUTPUT);
        gpio_set_level(DISPLAY_CS_PIN, 1);
        gpio_set_direction(DISPLAY_RST_PIN, GPIO_MODE_OUTPUT);
        gpio_set_level(DISPLAY_RST_PIN, 1);

        i2c_master_bus_config_t bus_config = {};
        bus_config.i2c_port = (i2c_port_t)0;
        bus_config.sda_io_num = DISPLAY_FB_SSD1306_SDA_PIN;
        bus_config.scl_io_num = DISPLAY_FB_SSD1306_SCL_PIN;
        bus_config.clk_source = I2C_CLK_SRC_DEFAULT;
        bus_config.glitch_ignore_cnt = 7;
        bus_config.intr_priority = 0;
        bus_config.trans_queue_depth = 0;
        bus_config.flags.enable_internal_pullup = 1;

        i2c_master_bus_handle_t i2c_bus = nullptr;
        if (i2c_new_master_bus(&bus_config, &i2c_bus) != ESP_OK) {
            ESP_LOGW(TAG, "I2C master bus init failed, skip fallback display");
            gpio_reset_pin(DISPLAY_FB_SSD1306_SCL_PIN);
            gpio_reset_pin(DISPLAY_FB_SSD1306_SDA_PIN);
            return false;
        }

        // 连续 3 次 ACK 才认定备用屏存在, 避免悬空 SDA 偶发误 ACK 误入备用屏模式
        constexpr int kProbeTrials = 3;
        bool ssd1306_found = true;
        for (int i = 0; i < kProbeTrials; ++i) {
            if (i2c_master_probe(i2c_bus, DISPLAY_FB_SSD1306_ADDR, 100) != ESP_OK) {
                ssd1306_found = false;
                break;
            }
        }
        if (!ssd1306_found) {
            ESP_LOGI(TAG, "Fallback SSD1306 not found at 0x%02X, using primary ST7789",
                     DISPLAY_FB_SSD1306_ADDR);
            i2c_del_master_bus(i2c_bus);
            // i2c_del_master_bus 只撤销输出/开漏, 不复位引脚; 这里显式恢复
            // 9/8 为默认状态, 消除 I2C 残留(上拉等)
            gpio_reset_pin(DISPLAY_FB_SSD1306_SCL_PIN);
            gpio_reset_pin(DISPLAY_FB_SSD1306_SDA_PIN);
            return false;
        }
        ESP_LOGI(TAG, "Fallback SSD1306 detected at 0x%02X", DISPLAY_FB_SSD1306_ADDR);

        esp_lcd_panel_io_handle_t panel_io = nullptr;
        esp_lcd_panel_handle_t panel = nullptr;

        esp_lcd_panel_io_i2c_config_t io_config = {};
        io_config.dev_addr = DISPLAY_FB_SSD1306_ADDR;
        io_config.scl_speed_hz = 400 * 1000;
        io_config.control_phase_bytes = 1;
        io_config.dc_bit_offset = 6;
        io_config.lcd_cmd_bits = 8;
        io_config.lcd_param_bits = 8;
        if (esp_lcd_new_panel_io_i2c(i2c_bus, &io_config, &panel_io) != ESP_OK) {
            ESP_LOGW(TAG, "Fallback SSD1306 panel io init failed, using primary ST7789");
            i2c_del_master_bus(i2c_bus);
            gpio_reset_pin(DISPLAY_FB_SSD1306_SCL_PIN);
            gpio_reset_pin(DISPLAY_FB_SSD1306_SDA_PIN);
            return false;
        }

        esp_lcd_panel_dev_config_t panel_config = {};
        panel_config.reset_gpio_num = GPIO_NUM_NC;
        panel_config.bits_per_pixel = 1;
        esp_lcd_panel_ssd1306_config_t ssd1306_config = {
            .height = static_cast<uint8_t>(DISPLAY_FB_SSD1306_HEIGHT),
        };
        panel_config.vendor_config = &ssd1306_config;
#ifdef DISPLAY_FB_SSD1306_USE_SH1106
        esp_err_t panel_err = esp_lcd_new_panel_sh1106(panel_io, &panel_config, &panel);
#else
        esp_err_t panel_err = esp_lcd_new_panel_ssd1306(panel_io, &panel_config, &panel);
#endif
        if (panel_err != ESP_OK) {
            ESP_LOGW(TAG, "Fallback OLED driver install failed, using primary ST7789");
            esp_lcd_panel_io_del(panel_io);
            i2c_del_master_bus(i2c_bus);
            gpio_reset_pin(DISPLAY_FB_SSD1306_SCL_PIN);
            gpio_reset_pin(DISPLAY_FB_SSD1306_SDA_PIN);
            return false;
        }

        if (esp_lcd_panel_reset(panel) != ESP_OK ||
            esp_lcd_panel_init(panel) != ESP_OK) {
            ESP_LOGW(TAG, "Fallback SSD1306 init failed, using primary ST7789");
            esp_lcd_panel_del(panel);
            esp_lcd_panel_io_del(panel_io);
            i2c_del_master_bus(i2c_bus);
            gpio_reset_pin(DISPLAY_FB_SSD1306_SCL_PIN);
            gpio_reset_pin(DISPLAY_FB_SSD1306_SDA_PIN);
            return false;
        }
        esp_lcd_panel_disp_on_off(panel, true);
        esp_lcd_panel_mirror(panel, DISPLAY_FB_SSD1306_MIRROR_X, DISPLAY_FB_SSD1306_MIRROR_Y);

        use_fallback_ssd1306_ = true;
        display_ = new OledDisplay(panel_io, panel,
                                   DISPLAY_FB_SSD1306_WIDTH, DISPLAY_FB_SSD1306_HEIGHT,
                                   DISPLAY_FB_SSD1306_MIRROR_X, DISPLAY_FB_SSD1306_MIRROR_Y);
        ESP_LOGI(TAG, "Fallback SSD1306 ready (%dx%d)",
                 DISPLAY_FB_SSD1306_WIDTH, DISPLAY_FB_SSD1306_HEIGHT);
        return true;
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
            HandleKeyEvent(0);
        });
        boot_button_.OnDoubleClick([this]() {
            HandleKeyEvent(1);
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
            HandleKeyEvent(2);
        });
    }

    // 皮肤层按键增强反馈：主屏(圆屏皮肤)转发, 备用屏(OledDisplay)无此皮肤则跳过
    void HandleKeyEvent(int ev) {
        if (use_fallback_ssd1306_) {
            return;
        }
        static_cast<RoundScreenDisplay*>(display_)->HandleKeyEvent(ev);
    }

    // 1 秒节拍：圆屏自动行为（夜间/早晨/低电量提醒 + 彩蛋超时恢复）
    // 备用屏模式下跳过（皮肤层专属行为）
    void InitializeTickTimer() {
        if (use_fallback_ssd1306_) {
            return;
        }
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
        display_ = nullptr;
        // 屏幕兼容性: 先探测备用 I2C 屏 (SCL=9/SDA=8, 0x3C), 识别到则用
        // 备用方案; 识别不到回退原 ST7789 SPI 主屏 (CLK=21/MOSI=47)
        if (!TryInitializeFallbackSsd1306()) {
            InitializeSpi();
            InitializeLcdDisplay();
        }
        InitializeButtons();
        InitializeTickTimer();
        if (GetBacklight() != nullptr) {
            GetBacklight()->RestoreBrightness();
        }

        // MAX98357A: VIN=3.3V, GAIN 接地 -> 实际增益 12dB (5V 供电才是 15dB)。
        // SD 接 3.3V 常使能(>1.4V 时输出左声道, 与 VIN 同网)。
        // 音量不在此处设置: 开机音量由 AudioCodec 从 NVS (audio/output_volume) 恢复,
        // 服务器连接后还会下发云端配置 (device_config) 覆盖本地值。

        ESP_LOGI(TAG, "Board init done (display=%s, audio in=%d Hz, out=%d Hz)",
                 use_fallback_ssd1306_ ? "SSD1306-I2C" : "ST7789-SPI",
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

    // 备用 SSD1306 无背光引脚; 主屏走 PWM 背光 GPIO42
    virtual Backlight* GetBacklight() override {
        if (use_fallback_ssd1306_) {
            return nullptr;
        }
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

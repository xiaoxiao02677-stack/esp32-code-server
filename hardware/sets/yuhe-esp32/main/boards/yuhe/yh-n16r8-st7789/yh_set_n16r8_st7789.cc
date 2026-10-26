#include "wifi_board.h"
#include "codecs/no_audio_codec.h"
#include "display/lcd_display.h"
#include "application.h"
#include "button.h"
#include "config.h"
#include "power_save_timer.h"
#include "display/yh_skin/yh_skin_display.h"
#if CONFIG_YH_UI_THEME_PIXELPET
#include "display/pet_skin/pet_skin_display.h"
#elif CONFIG_YH_UI_THEME_EMOPET
#include "display/emo_skin/emo_skin_display.h"
#elif CONFIG_YH_UI_THEME_DENGYU
#include "display/DengYu_skin/dengyu_skin_display.h"
#elif CONFIG_YH_UI_THEME_FACE
#include "display/face_skin/face_skin_display.h"
#elif CONFIG_YH_UI_THEME_CAT
#include "display/cat_skin/cat_skin_display.h"
#endif

#include <esp_log.h>
#include <esp_lcd_panel_vendor.h>
#include <esp_lcd_panel_io.h>
#include <esp_lcd_panel_ops.h>
#include <driver/spi_common.h>
#include <esp_timer.h>

// 第一代小方块（ESP32-S3-N16R8 / ST7789 240x240）圆屏皮肤版
// 显示层用 main/display/yh_skin 的共享皮肤（视觉基准同 my-s3-tft 的 RoundScreenDisplay），
// 硬件引脚与旧版完全一致：
//   LCD SDA=47 SCL=21 RST=45 DC=40 CS=41 BL=42
//   INMP441 WS=4 SCK=5 DIN=6 / MAX98357A DOUT=7 BCLK=15 LRCK=16 / BOOT=GPIO0
#define TAG "YH_SET_N16R8_ST7789"

class YhSetN16R8Board : public WifiBoard {
private:
    Button boot_button_;
    YhSkinDisplay* display_ = nullptr;  // 共享「小柚」皮肤（240x240 圆屏、无电池）
    PowerSaveTimer* power_save_timer_ = nullptr;
    esp_timer_handle_t tick_timer_ = nullptr;
    esp_lcd_panel_io_handle_t panel_io_ = nullptr;
    esp_lcd_panel_handle_t panel_ = nullptr;

    void InitializePowerSaveTimer() {
        power_save_timer_ = new PowerSaveTimer(-1, 60, 300);
        power_save_timer_->OnEnterSleepMode([this]() {
            GetDisplay()->SetPowerSaveMode(true);
            GetBacklight()->SetBrightness(1);
        });
        power_save_timer_->OnExitSleepMode([this]() {
            GetDisplay()->SetPowerSaveMode(false);
            GetBacklight()->RestoreBrightness();
        });
        power_save_timer_->SetEnabled(true);
    }

    void InitializeSpi() {
        spi_bus_config_t buscfg = {};
        buscfg.mosi_io_num = DISPLAY_SDA;
        buscfg.miso_io_num = GPIO_NUM_NC;
        buscfg.sclk_io_num = DISPLAY_SCL;
        buscfg.quadwp_io_num = GPIO_NUM_NC;
        buscfg.quadhd_io_num = GPIO_NUM_NC;
        buscfg.max_transfer_sz = DISPLAY_WIDTH * DISPLAY_HEIGHT * sizeof(uint16_t);
        ESP_ERROR_CHECK(spi_bus_initialize(SPI3_HOST, &buscfg, SPI_DMA_CH_AUTO));
    }

    // 单 BOOT 键三事件（与 A 板 my_s3_tft_board.cc 逐项对齐）：
    // - 短按：待机/说话 -> Application::ToggleChatState()（原逻辑不变，开/打断）
    // - 双击：待机 -> 表情彩蛋（RoundScreenDisplay::NextEasterEgg）
    // - 长按 1s：Starting(开机 30s 内) -> 配网；聆听/说话 -> 取消；待机 -> 静音切换
    //
    // ⚠️ 2026-10-08 修复：Button 构造默认 long_press_time=0 会回退到
    // iot_button 注册校验里被强制为 short_press_ticks(180ms)——普通短按即触发
    // 长按回调，而回调里的 EnterWifiConfigMode 在设备卡 Starting（配网后未连上
    // 服务器）时形成"按键即重配网"死循环。修复：显式 1000ms + 长按只在
    // Starting 早期（刚开机 30s 内）允许进配网。
    void InitializeButtons() {
        boot_button_.OnClick([this]() {
            if (power_save_timer_ != nullptr) {
                power_save_timer_->WakeUp();
            }
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
            if (power_save_timer_ != nullptr) {
                power_save_timer_->WakeUp();
            }
            HandleKeyEvent(1);
        });
        boot_button_.OnLongPress([this]() {
            if (power_save_timer_ != nullptr) {
                power_save_timer_->WakeUp();
            }
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

    // 皮肤层按键增强反馈：统一转发给共享皮肤
    void HandleKeyEvent(int ev) {
        if (display_ != nullptr) {
            display_->HandleKeyEvent(ev);
        }
    }

    // 1 秒节拍：圆屏自动行为（夜间/早晨问候 + 彩蛋超时恢复）
    // esp_timer 周期 1s，回调里只做 UI 操作（DisplayLockGuard 保护）
    void InitializeTickTimer() {
        if (display_ == nullptr) {
            return;
        }
        esp_timer_create_args_t args = {
            .callback =
                [](void* arg) {
                    auto* disp = static_cast<YhSkinDisplay*>(arg);
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

    void InitializeSt7789Display() {
        ESP_LOGD(TAG, "Install panel IO");
        esp_lcd_panel_io_spi_config_t io_config = {};
        io_config.cs_gpio_num = DISPLAY_CS;
        io_config.dc_gpio_num = DISPLAY_DC;
        io_config.spi_mode = 3;
        io_config.pclk_hz = 80 * 1000 * 1000;
        io_config.trans_queue_depth = 10;
        io_config.lcd_cmd_bits = 8;
        io_config.lcd_param_bits = 8;
        ESP_ERROR_CHECK(esp_lcd_new_panel_io_spi(SPI3_HOST, &io_config, &panel_io_));

        ESP_LOGD(TAG, "Install LCD driver");
        esp_lcd_panel_dev_config_t panel_config = {};
        panel_config.reset_gpio_num = DISPLAY_RES;
        panel_config.rgb_ele_order = LCD_RGB_ELEMENT_ORDER_RGB;
        panel_config.bits_per_pixel = 16;
        ESP_ERROR_CHECK(esp_lcd_new_panel_st7789(panel_io_, &panel_config, &panel_));
        ESP_ERROR_CHECK(esp_lcd_panel_reset(panel_));
        ESP_ERROR_CHECK(esp_lcd_panel_init(panel_));
        ESP_ERROR_CHECK(esp_lcd_panel_swap_xy(panel_, DISPLAY_SWAP_XY));
        ESP_ERROR_CHECK(esp_lcd_panel_mirror(panel_, DISPLAY_MIRROR_X, DISPLAY_MIRROR_Y));
        ESP_ERROR_CHECK(esp_lcd_panel_invert_color(panel_, true));

        // 皮肤按编译期主题选择（build.py --theme）：xiaoyou=原圆屏皮肤，
        // pixel-pet=像素宠物，emopet=EMOpet 机器人眼，dengyu=灯语光萤
        //（同一构造签名，240 圆屏布局自动换算）
#if CONFIG_YH_UI_THEME_PIXELPET
        display_ = new PetSkinDisplay(panel_io_, panel_, DISPLAY_WIDTH, DISPLAY_HEIGHT,
                                     DISPLAY_OFFSET_X, DISPLAY_OFFSET_Y, DISPLAY_MIRROR_X,
                                     DISPLAY_MIRROR_Y, DISPLAY_SWAP_XY,
                                     YhSkinProfile::Round240(false));
#elif CONFIG_YH_UI_THEME_EMOPET
        display_ = new EmoSkinDisplay(panel_io_, panel_, DISPLAY_WIDTH, DISPLAY_HEIGHT,
                                     DISPLAY_OFFSET_X, DISPLAY_OFFSET_Y, DISPLAY_MIRROR_X,
                                     DISPLAY_MIRROR_Y, DISPLAY_SWAP_XY,
                                     YhSkinProfile::Round240(false));
#elif CONFIG_YH_UI_THEME_DENGYU
        display_ = new DengYuSkinDisplay(panel_io_, panel_, DISPLAY_WIDTH, DISPLAY_HEIGHT,
                                     DISPLAY_OFFSET_X, DISPLAY_OFFSET_Y, DISPLAY_MIRROR_X,
                                     DISPLAY_MIRROR_Y, DISPLAY_SWAP_XY,
                                     YhSkinProfile::Round240(false));
#elif CONFIG_YH_UI_THEME_FACE
        display_ = new FaceSkinDisplay(panel_io_, panel_, DISPLAY_WIDTH, DISPLAY_HEIGHT,
                                     DISPLAY_OFFSET_X, DISPLAY_OFFSET_Y, DISPLAY_MIRROR_X,
                                     DISPLAY_MIRROR_Y, DISPLAY_SWAP_XY,
                                     YhSkinProfile::Round240(false));
#elif CONFIG_YH_UI_THEME_CAT
        display_ = new CatSkinDisplay(panel_io_, panel_, DISPLAY_WIDTH, DISPLAY_HEIGHT,
                                      DISPLAY_OFFSET_X, DISPLAY_OFFSET_Y, DISPLAY_MIRROR_X,
                                      DISPLAY_MIRROR_Y, DISPLAY_SWAP_XY,
                                      YhSkinProfile::Round240(false));
#else
        display_ = new YhSkinDisplay(panel_io_, panel_, DISPLAY_WIDTH, DISPLAY_HEIGHT,
                                     DISPLAY_OFFSET_X, DISPLAY_OFFSET_Y, DISPLAY_MIRROR_X,
                                     DISPLAY_MIRROR_Y, DISPLAY_SWAP_XY,
                                     YhSkinProfile::Round240(false));
#endif
        ESP_LOGI(TAG, "LCD ready (%dx%d, YhSkinDisplay round)", DISPLAY_WIDTH, DISPLAY_HEIGHT);
    }

public:
    YhSetN16R8Board() : boot_button_(BOOT_BUTTON_GPIO, false, 1000) {
        // 先建屏再起省电定时器：OnEnterSleepMode 会解引用 GetDisplay()
        InitializeSpi();
        InitializeSt7789Display();
        InitializePowerSaveTimer();
        InitializeButtons();
        InitializeTickTimer();
        if (GetBacklight() != nullptr) {
            GetBacklight()->RestoreBrightness();
        }
    }

    // 获取音频编解码器（单工 I2S：MAX98357A 输出 + INMP441 输入）
    virtual AudioCodec* GetAudioCodec() override {
        static NoAudioCodecSimplex audio_codec(AUDIO_INPUT_SAMPLE_RATE, AUDIO_OUTPUT_SAMPLE_RATE,
            AUDIO_I2S_SPK_GPIO_BCLK, AUDIO_I2S_SPK_GPIO_LRCK, AUDIO_I2S_SPK_GPIO_DOUT, AUDIO_I2S_MIC_GPIO_SCK, AUDIO_I2S_MIC_GPIO_WS, AUDIO_I2S_MIC_GPIO_DIN);
        return &audio_codec;
    }

    virtual Display* GetDisplay() override {
        return display_;
    }

    // PWM 背光（GPIO42 走 LEDC），亮度可调、休眠可降到 1
    virtual Backlight* GetBacklight() override {
        static PwmBacklight backlight(DISPLAY_BACKLIGHT_PIN, DISPLAY_BACKLIGHT_OUTPUT_INVERT);
        return &backlight;
    }

    virtual void SetPowerSaveLevel(PowerSaveLevel level) override {
        if (level != PowerSaveLevel::LOW_POWER) {
            power_save_timer_->WakeUp();
        }
        WifiBoard::SetPowerSaveLevel(level);
    }
};

DECLARE_BOARD(YhSetN16R8Board);

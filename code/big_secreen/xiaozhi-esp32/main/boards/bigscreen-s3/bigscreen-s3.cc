#include <esp_lcd_panel_vendor.h>
#include <esp_lcd_panel_io.h>
#include <esp_lcd_panel_ops.h>

#include <wifi_station.h>
#include "wifi_board.h"
#include "codecs/es8311_audio_codec.h"
#include "codecs/no_audio_codec.h"
#include "display/lcd_display.h"
#include "application.h"
#include "button.h"
#include "config.h"
#include "system_reset.h"
#include "esp_lcd_ili9341.h"
#include "bigscreen_display.h"

#include <esp_log.h>
#include <driver/i2c_master.h>
#include <driver/spi_common.h>
#include <driver/sdmmc_host.h>
#include <driver/sdmmc_types.h>
#include <esp_vfs_fat.h>
#include <esp_timer.h>
#include <freertos/FreeRTOS.h>
#include <freertos/task.h>

#define TAG "BigscreenS3"

// 大屏幕板：ESP32-S3 + ES8311 音频 + ILI9341 2.8" SPI 屏（320x240 横屏）。
// 板卡鉴定为 Freenove ESP32-S3 Display 2.8"（或同布线套板），引脚按该板官方
// 原理图修正，见 config.h 顶部说明。无电池、无可用触摸（I2C 触摸 init 失败，暂不启用）。
// YH 心跳协议（sandyun.top:12399）与 OTA 经 config.json 的 sdkconfig_append 启用。
//
// 皮肤：BigscreenDisplay（big_screen.mp4 GIF 动画背景 + 左上时间 + 右上表情
// 徽章 + 中下气泡 + 底部提示）。单 BOOT 键三事件交互（短按/双击/长按）。
//
// 防重启循环：ES8311 的 I2C 探测失败（无 ACK）时不再走 ESP_ERROR_CHECK abort，
// 而是降级为 NoAudioCodecDuplex（纯 I2S 数字音频，无硬件 codec 控制），
// 设备仍能进配网/联网，串口会打印 "[WARN] ES8311 not detected" 便于排查。
class BigscreenS3Board : public WifiBoard {
private:
    Button boot_button_;
    BigscreenDisplay* display_;
    i2c_master_bus_handle_t codec_i2c_bus_ = nullptr;
    bool es8311_present_ = false;
    esp_timer_handle_t tick_timer_ = nullptr;

    void InitializeI2c() {
        i2c_master_bus_config_t i2c_bus_cfg = {
            .i2c_port = AUDIO_CODEC_I2C_NUM,
            .sda_io_num = AUDIO_CODEC_I2C_SDA_PIN,
            .scl_io_num = AUDIO_CODEC_I2C_SCL_PIN,
            .clk_source = I2C_CLK_SRC_DEFAULT,
            .glitch_ignore_cnt = 7,
            .intr_priority = 0,
            .trans_queue_depth = 0,
            .flags = {
                .enable_internal_pullup = 1,
            },
        };
        ESP_ERROR_CHECK(i2c_new_master_bus(&i2c_bus_cfg, &codec_i2c_bus_));
    }

    // 探测 ES8311 是否在总线上（地址 0x30/0x18 视 ADDR 引脚，默认 0x30）。
    bool ProbeEs8311() {
        i2c_master_dev_handle_t dev = nullptr;
        i2c_device_config_t cfg = {
            .device_address = AUDIO_CODEC_ES8311_ADDR >> 1,
            .scl_speed_hz = 100000,
            .scl_wait_us = 0,
        };
        if (i2c_master_bus_add_device(codec_i2c_bus_, &cfg, &dev) != ESP_OK) {
            return false;
        }
        uint8_t reg = 0x00;  // chip reset register (readable)
        uint8_t val = 0;
        bool ok = i2c_master_transmit_receive(dev, &reg, 1, &val, 1, 50) == ESP_OK;
        i2c_master_bus_rm_device(dev);
        return ok;
    }

    void InitializeSpi() {
        spi_bus_config_t buscfg = {};
        buscfg.mosi_io_num = DISPLAY_MOSI_PIN;
        buscfg.miso_io_num = DISPLAY_MISO_PIN;
        buscfg.sclk_io_num = DISPLAY_SCK_PIN;
        buscfg.quadwp_io_num = GPIO_NUM_NC;
        buscfg.quadhd_io_num = GPIO_NUM_NC;
        buscfg.max_transfer_sz = DISPLAY_WIDTH * DISPLAY_HEIGHT * sizeof(uint16_t);
        ESP_ERROR_CHECK(spi_bus_initialize(LCD_SPI_HOST, &buscfg, SPI_DMA_CH_AUTO));
    }

    // 单 BOOT 键三事件（适配提示词交互表 + my-s3-tft 验证过的防误触策略）：
    // - 短按：Starting -> 配网（原逻辑）；Idle/Speaking -> ToggleChatState（开聊/打断）
    // - 双击：待机 -> 表情彩蛋轮播（BigscreenDisplay::NextEasterEgg）
    // - 长按 1s：Starting 前 30s -> 配网；Listening/Speaking -> 取消/打断；
    //            Idle -> 静音切换
    //
    // Button 构造显式 long_press_time=1000ms：默认 0 会回退到 iot_button 注册
    // 校验强制值（= short_press_ticks 180ms），导致普通按压被误判为长按
    // （my-s3-tft 2026-10-08 同款教训）。
    void InitializeButtons() {
        boot_button_.OnClick([this]() {
            auto& app = Application::GetInstance();
            if (app.GetDeviceState() == kDeviceStateStarting) {
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

    // SD 卡初始化：挂载 /sdcard（FAT32）。后台任务执行——SDMMC 无卡时
    // 探测超时可达 1-2 秒，不能阻塞板构造（否则拖慢开机/配网时序）。
    // 失败仅打日志（设备无 SD 也必须能正常跑，UI 回退 Flash 内置背景）。
    // 挂载成功后通知 BigscreenDisplay 切换到 SD 大背景。
    void InitializeSdCard() {
        xTaskCreate(
            [](void* arg) {
                auto* self = static_cast<BigscreenS3Board*>(arg);
                sdmmc_host_t host = SDMMC_HOST_DEFAULT();
                host.slot = SDMMC_HOST_SLOT_1;
                host.max_freq_khz = SDMMC_FREQ_HIGHSPEED;

                sdmmc_slot_config_t slot = {};
                slot.clk = SD_MMC_GPIO_CLK;
                slot.cmd = SD_MMC_GPIO_CMD;
                slot.d0 = SD_MMC_GPIO_D0;
                slot.d1 = SD_MMC_GPIO_D1;
                slot.d2 = SD_MMC_GPIO_D2;
                slot.d3 = SD_MMC_GPIO_D3;
                slot.cd = SDMMC_SLOT_NO_CD;
                slot.wp = SDMMC_SLOT_NO_WP;
                slot.width = 4;

                esp_vfs_fat_sdmmc_mount_config_t mount_config = {};
                mount_config.format_if_mount_failed = false;
                mount_config.max_files = 2;
                mount_config.allocation_unit_size = 16 * 1024;

                sdmmc_card_t* card = nullptr;
                esp_err_t ret = esp_vfs_fat_sdmmc_mount(SD_CARD_MOUNT_POINT, &host, &slot,
                                                        &mount_config, &card);
                if (ret == ESP_OK) {
                    sdmmc_card_print_info(stdout, card);
                    ESP_LOGI(TAG, "SD card mounted at %s", SD_CARD_MOUNT_POINT);
                    if (self->display_ != nullptr) {
                        self->display_->OnSdCardMounted();
                    }
                } else {
                    // 无卡/非 FAT32/接触不良都走这里——正常降级路径
                    ESP_LOGW(TAG, "SD card not mounted (%s); UI keeps flash background",
                             esp_err_to_name(ret));
                }
                vTaskDelete(nullptr);
            },
            "sd_init", 4096, this, 5, nullptr);
    }

    void InitializeLcdDisplay() {
        esp_lcd_panel_io_handle_t panel_io = nullptr;
        esp_lcd_panel_handle_t panel = nullptr;

        ESP_LOGD(TAG, "Install panel IO");
        esp_lcd_panel_io_spi_config_t io_config = {};
        io_config.cs_gpio_num = DISPLAY_CS_PIN;
        io_config.dc_gpio_num = DISPLAY_DC_PIN;
        io_config.spi_mode = DISPLAY_SPI_MODE;
        io_config.pclk_hz = DISPLAY_SPI_SCLK_HZ;
        io_config.trans_queue_depth = 10;
        io_config.lcd_cmd_bits = 8;
        io_config.lcd_param_bits = 8;
        ESP_ERROR_CHECK(esp_lcd_new_panel_io_spi(LCD_SPI_HOST, &io_config, &panel_io));

        ESP_LOGD(TAG, "Install LCD driver ILI9341");
        esp_lcd_panel_dev_config_t panel_config = {};
        panel_config.reset_gpio_num = DISPLAY_RST_PIN;
        panel_config.rgb_ele_order = DISPLAY_RGB_ORDER;
        panel_config.bits_per_pixel = 16;
        ESP_ERROR_CHECK(esp_lcd_new_panel_ili9341(panel_io, &panel_config, &panel));
        esp_lcd_panel_reset(panel);
        esp_lcd_panel_init(panel);
        esp_lcd_panel_invert_color(panel, DISPLAY_INVERT_COLOR);
        esp_lcd_panel_swap_xy(panel, DISPLAY_SWAP_XY);
        esp_lcd_panel_mirror(panel, DISPLAY_MIRROR_X, DISPLAY_MIRROR_Y);

        // 大屏皮肤：GIF 动画背景 + 时间/表情徽章/气泡/提示
        display_ = new BigscreenDisplay(panel_io, panel,
            DISPLAY_WIDTH, DISPLAY_HEIGHT,
            DISPLAY_OFFSET_X, DISPLAY_OFFSET_Y,
            DISPLAY_MIRROR_X, DISPLAY_MIRROR_Y, DISPLAY_SWAP_XY);
    }

    // 1 秒节拍：彩蛋超时恢复 + 整分钟自动行为（夜间/早晨提醒）
    void InitializeTickTimer() {
        esp_timer_create_args_t args = {
            .callback =
                [](void* arg) {
                    auto* disp = static_cast<BigscreenDisplay*>(arg);
                    disp->Tick1s();
                },
            .arg = display_,
            .dispatch_method = ESP_TIMER_TASK,
            .name = "bigscreen_ui_tick",
            .skip_unhandled_events = true,
        };
        ESP_ERROR_CHECK(esp_timer_create(&args, &tick_timer_));
        ESP_ERROR_CHECK(esp_timer_start_periodic(tick_timer_, 1000000));  // 1s
    }

public:
    BigscreenS3Board(): boot_button_(BOOT_BUTTON_GPIO, false, 1000)
    {
        InitializeI2c();
        es8311_present_ = ProbeEs8311();
        if (!es8311_present_) {
            ESP_LOGW(TAG, "ES8311 not detected on I2C (SCL=%d SDA=%d addr=0x%02x); "
                          "audio falls back to raw I2S. Check wiring/config.h.",
                     AUDIO_CODEC_I2C_SCL_PIN, AUDIO_CODEC_I2C_SDA_PIN, AUDIO_CODEC_ES8311_ADDR);
        }
        InitializeSpi();
        InitializeLcdDisplay();
        InitializeButtons();
        InitializeTickTimer();
        InitializeSdCard();
        GetBacklight()->SetBrightness(100);
    }

    virtual AudioCodec* GetAudioCodec() override {
        if (es8311_present_) {
            static Es8311AudioCodec audio_codec(codec_i2c_bus_, AUDIO_CODEC_I2C_NUM,
                AUDIO_INPUT_SAMPLE_RATE, AUDIO_OUTPUT_SAMPLE_RATE, AUDIO_I2S_GPIO_MCLK, AUDIO_I2S_GPIO_BCLK,
                AUDIO_I2S_GPIO_WS, AUDIO_I2S_GPIO_DOUT, AUDIO_I2S_GPIO_DIN, AUDIO_CODEC_PA_PIN,
                AUDIO_CODEC_ES8311_ADDR, true, true);
            return &audio_codec;
        }
        // 降级：无硬件 codec 时仍提供数字 I2S 通道（输入/输出直通）。
        static NoAudioCodecDuplex audio_codec(AUDIO_INPUT_SAMPLE_RATE, AUDIO_OUTPUT_SAMPLE_RATE,
            AUDIO_I2S_GPIO_BCLK, AUDIO_I2S_GPIO_WS, AUDIO_I2S_GPIO_DOUT, AUDIO_I2S_GPIO_DIN);
        return &audio_codec;
    }

    virtual Display* GetDisplay() override { return display_; }

    virtual Backlight* GetBacklight() override {
        static PwmBacklight backlight(DISPLAY_BACKLIGHT_PIN, DISPLAY_BACKLIGHT_OUTPUT_INVERT);
        return &backlight;
    }
};

DECLARE_BOARD(BigscreenS3Board);

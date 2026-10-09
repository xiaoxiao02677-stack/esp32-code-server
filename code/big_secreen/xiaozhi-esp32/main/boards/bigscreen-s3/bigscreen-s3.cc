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

#include <esp_log.h>
#include <driver/i2c_master.h>
#include <driver/spi_common.h>
#include <freertos/FreeRTOS.h>
#include <freertos/task.h>

#define TAG "BigscreenS3"

// 大屏幕板：ESP32-S3 + ES8311 音频 + ILI9341 2.8" SPI 屏（320x240 横屏）。
// 板卡鉴定为 Freenove ESP32-S3 Display 2.8"（或同布线套板），引脚按该板官方
// 原理图修正，见 config.h 顶部说明。无电池、无可用触摸（I2C 触摸 init 失败，暂不启用）。
// YH 心跳协议（sandyun.top:12399）与 OTA 经 config.json 的 sdkconfig_append 启用。
//
// 防重启循环：ES8311 的 I2C 探测失败（无 ACK）时不再走 ESP_ERROR_CHECK abort，
// 而是降级为 NoAudioCodecDuplex（纯 I2S 数字音频，无硬件 codec 控制），
// 设备仍能进配网/联网，串口会打印 "[WARN] ES8311 not detected" 便于排查。
class BigscreenS3Board : public WifiBoard {
private:
    Button boot_button_;
    LcdDisplay *display_;
    i2c_master_bus_handle_t codec_i2c_bus_ = nullptr;
    bool es8311_present_ = false;

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

    void InitializeButtons() {
        boot_button_.OnClick([this]() {
            auto &app = Application::GetInstance();
            if (app.GetDeviceState() == kDeviceStateStarting) {
                EnterWifiConfigMode();
            }
            app.ToggleChatState();
        });
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
        display_ = new SpiLcdDisplay(panel_io, panel,
            DISPLAY_WIDTH, DISPLAY_HEIGHT,
            DISPLAY_OFFSET_X, DISPLAY_OFFSET_Y,
            DISPLAY_MIRROR_X, DISPLAY_MIRROR_Y, DISPLAY_SWAP_XY);
    }

public:
    BigscreenS3Board(): boot_button_(BOOT_BUTTON_GPIO)
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

    virtual Display *GetDisplay() override { return display_; }

    virtual Backlight *GetBacklight() override {
        static PwmBacklight backlight(DISPLAY_BACKLIGHT_PIN, DISPLAY_BACKLIGHT_OUTPUT_INVERT);
        return &backlight;
    }
};

DECLARE_BOARD(BigscreenS3Board);

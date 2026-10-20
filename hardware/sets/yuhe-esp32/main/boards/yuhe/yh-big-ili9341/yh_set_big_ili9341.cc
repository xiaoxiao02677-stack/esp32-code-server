// IDF / 组件的头文件必须排在 config.h 之前：config.h 里的
// SPI2_HOST / I2C_NUM_0 / LCD_RGB_ELEMENT_ORDER_BGR 等宏都依赖它们。
#include <esp_log.h>
#include <driver/gpio.h>
#include <driver/i2c_master.h>
#include <driver/spi_common.h>
#include <esp_lcd_panel_vendor.h>
#include <esp_lcd_panel_io.h>
#include <esp_lcd_panel_ops.h>
#include <esp_lcd_ili9341.h>

#include "wifi_board.h"
#include "codecs/es8311_audio_codec.h"
#include "codecs/no_audio_codec.h"
#include "display/lcd_display.h"
#include "display/yh_skin/yh_skin_display.h"
#if CONFIG_YH_UI_THEME_PIXELPET
#include "display/pet_skin/pet_skin_display.h"
#elif CONFIG_YH_UI_THEME_EMOPET
#include "display/emo_skin/emo_skin_display.h"
#endif
#include "application.h"
#include "button.h"
#include "mcp_server.h"
#include "config.h"

#define TAG "YhSetBigIli9341"

// 引脚来源：hardware/big_secreen/yuhe-esp32（原厂固件，实机验证）。
// 该板为 Freenove ESP32-S3 Display 2.8" 布线，详见同目录 config.h 头注释。
class YhSetBigIli9341Board : public WifiBoard {
private:
    Button boot_button_;
    LcdDisplay* display_ = nullptr;
    i2c_master_bus_handle_t codec_i2c_bus_ = nullptr;
    // ES8311 是否在 I2C 总线上应答（启动探测；失败降级哑编解码器）
    bool codec_i2c_ok_ = false;

    i2c_master_bus_handle_t MakeI2cBus(gpio_num_t sda, gpio_num_t scl) {
        i2c_master_bus_config_t i2c_bus_cfg = {
            .i2c_port = AUDIO_CODEC_I2C_NUM,
            .sda_io_num = sda,
            .scl_io_num = scl,
            .clk_source = I2C_CLK_SRC_DEFAULT,
            .glitch_ignore_cnt = 7,
            .intr_priority = 0,
            .trans_queue_depth = 0,
            .flags = {
                .enable_internal_pullup = 1,
            },
        };
        i2c_master_bus_handle_t bus = nullptr;
        ESP_ERROR_CHECK(i2c_new_master_bus(&i2c_bus_cfg, &bus));
        return bus;
    }

    void ScanI2cBus(i2c_master_bus_handle_t bus) {
        // 只发地址帧探测，对总线设备无副作用。全空说明这对引脚上没挂任何
        // I2C 器件——拿着这份日志对照原理图即可定位真实引脚。
        bool any = false;
        for (int addr = 0x08; addr <= 0x77; addr++) {
            if (i2c_master_probe(bus, addr, 10) == ESP_OK) {
                ESP_LOGW(TAG, "  I2C device at 0x%02x", addr);
                any = true;
            }
        }
        if (!any) {
            ESP_LOGW(TAG, "  (no I2C device on this pin pair)");
        }
    }

    void InitializeI2c() {
        // 引脚已按原厂固件（bigscreen-s3，实机验证）修正为 Freenove 官方
        // 布线 SCL=15/SDA=16。保留探测 + 降级：若 ES8311 仍无应答（套板
        // 布线差异等），扫总线打诊断日志并降级哑编解码器，绝不硬崩。
        // 注意 i2c_master_probe 要 7 位地址：ES8311 8 位写地址 0x30 >> 1 = 0x18。
        codec_i2c_bus_ = MakeI2cBus(AUDIO_CODEC_I2C_SDA_PIN, AUDIO_CODEC_I2C_SCL_PIN);
        if (i2c_master_probe(codec_i2c_bus_, AUDIO_CODEC_ES8311_ADDR >> 1, 30) == ESP_OK) {
            ESP_LOGI(TAG, "ES8311 probe OK: 7-bit addr 0x%02x on SDA=%d SCL=%d",
                     AUDIO_CODEC_ES8311_ADDR >> 1, AUDIO_CODEC_I2C_SDA_PIN,
                     AUDIO_CODEC_I2C_SCL_PIN);
            codec_i2c_ok_ = true;
            return;
        }
        ESP_LOGW(TAG, "ES8311 not responding on SDA=%d SCL=%d, scanning bus...",
                 AUDIO_CODEC_I2C_SDA_PIN, AUDIO_CODEC_I2C_SCL_PIN);
        ScanI2cBus(codec_i2c_bus_);
        // 探测失败：释放总线（引脚还原），音频降级哑编解码器。
        if (codec_i2c_bus_ != nullptr) {
            i2c_del_master_bus(codec_i2c_bus_);
            codec_i2c_bus_ = nullptr;
        }
        ESP_LOGW(TAG, "ES8311 not found; audio degraded to dummy codec "
                 "(screen/network still work). Check wiring and config.h.");
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

    void InitializeLcdDisplay() {
        esp_lcd_panel_io_handle_t panel_io = nullptr;
        esp_lcd_panel_handle_t panel = nullptr;

        ESP_LOGI(TAG, "Install ILI9341 panel IO (MOSI=%d SCK=%d CS=%d DC=%d RST=%d)",
                 DISPLAY_MOSI_PIN, DISPLAY_SCK_PIN, DISPLAY_CS_PIN, DISPLAY_DC_PIN, DISPLAY_RST_PIN);
        esp_lcd_panel_io_spi_config_t io_config = {};
        io_config.cs_gpio_num = DISPLAY_CS_PIN;
        io_config.dc_gpio_num = DISPLAY_DC_PIN;
        io_config.spi_mode = DISPLAY_SPI_MODE;
        io_config.pclk_hz = DISPLAY_SPI_SCLK_HZ;
        io_config.trans_queue_depth = 10;
        io_config.lcd_cmd_bits = 8;
        io_config.lcd_param_bits = 8;
        ESP_ERROR_CHECK(esp_lcd_new_panel_io_spi(LCD_SPI_HOST, &io_config, &panel_io));

        ESP_LOGI(TAG, "Install ILI9341 LCD driver");
        esp_lcd_panel_dev_config_t panel_config = {};
        panel_config.reset_gpio_num = DISPLAY_RST_PIN;
        panel_config.rgb_ele_order = DISPLAY_RGB_ORDER;
        panel_config.bits_per_pixel = 16;
        ESP_ERROR_CHECK(esp_lcd_new_panel_ili9341(panel_io, &panel_config, &panel));

        ESP_ERROR_CHECK(esp_lcd_panel_reset(panel));
        ESP_ERROR_CHECK(esp_lcd_panel_init(panel));
        ESP_ERROR_CHECK(esp_lcd_panel_invert_color(panel, DISPLAY_INVERT_COLOR));
        ESP_ERROR_CHECK(esp_lcd_panel_swap_xy(panel, DISPLAY_SWAP_XY));
        ESP_ERROR_CHECK(esp_lcd_panel_mirror(panel, DISPLAY_MIRROR_X, DISPLAY_MIRROR_Y));

        // 皮肤按编译期主题选择（build.py --theme）：320x240 横屏三套都支持
#if CONFIG_YH_UI_THEME_PIXELPET
        display_ = new PetSkinDisplay(panel_io, panel,
                                     DISPLAY_WIDTH, DISPLAY_HEIGHT,
                                     DISPLAY_OFFSET_X, DISPLAY_OFFSET_Y,
                                     DISPLAY_MIRROR_X, DISPLAY_MIRROR_Y,
                                     DISPLAY_SWAP_XY,
                                     YhSkinProfile::Wide320x240());
#elif CONFIG_YH_UI_THEME_EMOPET
        display_ = new EmoSkinDisplay(panel_io, panel,
                                     DISPLAY_WIDTH, DISPLAY_HEIGHT,
                                     DISPLAY_OFFSET_X, DISPLAY_OFFSET_Y,
                                     DISPLAY_MIRROR_X, DISPLAY_MIRROR_Y,
                                     DISPLAY_SWAP_XY,
                                     YhSkinProfile::Wide320x240());
#else
        display_ = new YhSkinDisplay(panel_io, panel,
                                     DISPLAY_WIDTH, DISPLAY_HEIGHT,
                                     DISPLAY_OFFSET_X, DISPLAY_OFFSET_Y,
                                     DISPLAY_MIRROR_X, DISPLAY_MIRROR_Y,
                                     DISPLAY_SWAP_XY,
                                     YhSkinProfile::Wide320x240());
#endif
    }

    void InitializeButtons() {
        boot_button_.OnClick([this]() {
            auto& app = Application::GetInstance();
            if (app.GetDeviceState() == kDeviceStateStarting) {
                EnterWifiConfigMode();
                return;
            }
            app.ToggleChatState();
        });

        boot_button_.OnLongPress([this]() {
            EnterWifiConfigMode();
        });
    }

public:
    YhSetBigIli9341Board() : boot_button_(BOOT_BUTTON_GPIO) {
        InitializeI2c();
        InitializeSpi();
        InitializeLcdDisplay();
        InitializeButtons();
        GetBacklight()->RestoreBrightness();
    }

    // 不覆写 GetLed：GPIO48 在 Freenove 板与 SD 卡 D2 共用（原厂固件同样
    // 不启用 LED），SingleLed 翻转会干扰 SD 通信。

    virtual AudioCodec* GetAudioCodec() override {
        if (!codec_i2c_ok_) {
            // ES8311 探测无应答：降级哑编解码器（只有 I2S 通道、无编解码
            // 控制）。设备可配网/显示，语音功能待排查接线后恢复。
            static NoAudioCodecDuplex dummy_codec(
                AUDIO_INPUT_SAMPLE_RATE, AUDIO_OUTPUT_SAMPLE_RATE,
                AUDIO_I2S_GPIO_BCLK, AUDIO_I2S_GPIO_WS,
                AUDIO_I2S_GPIO_DOUT, AUDIO_I2S_GPIO_DIN);
            return &dummy_codec;
        }
        static Es8311AudioCodec audio_codec(codec_i2c_bus_, AUDIO_CODEC_I2C_NUM,
            AUDIO_INPUT_SAMPLE_RATE, AUDIO_OUTPUT_SAMPLE_RATE,
            AUDIO_I2S_GPIO_MCLK, AUDIO_I2S_GPIO_BCLK, AUDIO_I2S_GPIO_WS,
            AUDIO_I2S_GPIO_DOUT, AUDIO_I2S_GPIO_DIN,
            AUDIO_CODEC_PA_PIN, AUDIO_CODEC_ES8311_ADDR, true, AUDIO_CODEC_PA_INVERTED);
        return &audio_codec;
    }

    virtual Display* GetDisplay() override {
        return display_;
    }

    virtual Backlight* GetBacklight() override {
        static PwmBacklight backlight(DISPLAY_BACKLIGHT_PIN, DISPLAY_BACKLIGHT_OUTPUT_INVERT);
        return &backlight;
    }
};

DECLARE_BOARD(YhSetBigIli9341Board);

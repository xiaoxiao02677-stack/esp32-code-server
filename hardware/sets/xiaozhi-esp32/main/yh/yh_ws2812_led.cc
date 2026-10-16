#include "yh_ws2812_led.h"

#include <esp_log.h>

#define TAG "YH_LED"

// 低亮度白色：足够可见且不刺眼（0-255 标度）
constexpr uint8_t kYhLedOnR = 16;
constexpr uint8_t kYhLedOnG = 16;
constexpr uint8_t kYhLedOnB = 16;

YhWs2812Led::YhWs2812Led(gpio_num_t gpio) {
    if (gpio == GPIO_NUM_NC) {
        ESP_LOGW(TAG, "YhWs2812Led: GPIO_NUM_NC, SET_LED will be a no-op");
        return;
    }

    led_strip_config_t strip_config = {};
    strip_config.strip_gpio_num = gpio;
    strip_config.max_leds = 1;
    strip_config.color_component_format = LED_STRIP_COLOR_COMPONENT_FMT_GRB;
    strip_config.led_model = LED_MODEL_WS2812;

    led_strip_rmt_config_t rmt_config = {};
    rmt_config.resolution_hz = 10 * 1000 * 1000;  // 10MHz，与 SingleLed 一致

    if (led_strip_new_rmt_device(&strip_config, &rmt_config, &strip_) != ESP_OK) {
        ESP_LOGE(TAG, "YhWs2812Led: led_strip_new_rmt_device failed on GPIO %d", gpio);
        strip_ = nullptr;
        return;
    }
    led_strip_clear(strip_);
    ESP_LOGI(TAG, "YhWs2812Led ready on GPIO %d", gpio);
}

YhWs2812Led::~YhWs2812Led() {
    if (strip_ != nullptr) {
        led_strip_del(strip_);
    }
}

bool YhWs2812Led::SetYhLed(bool on) {
    std::lock_guard<std::mutex> lock(mutex_);
    if (strip_ == nullptr) {
        return false;
    }
    if (on) {
        led_strip_set_pixel(strip_, 0, kYhLedOnR, kYhLedOnG, kYhLedOnB);
    } else {
        led_strip_clear(strip_);
    }
    if (led_strip_refresh(strip_) != ESP_OK) {
        ESP_LOGE(TAG, "led_strip_refresh failed");
        return false;
    }
    last_state_ = on;
    return true;
}

#ifndef YH_WS2812_LED_H
#define YH_WS2812_LED_H

#include <driver/gpio.h>
#include <led_strip.h>

#include <mutex>

// YH Device Protocol 专用 WS2812 单灯句柄。
//
// 与小智状态指示灯（Board::GetLed() -> SingleLed）完全独立：
// - SingleLed::OnStateChanged() 由设备状态机驱动（Idle 灭 / Speaking 绿...）
// - YhWs2812Led::SetYhLed() 仅由 YH SET_LED 命令驱动
// 两者各自持有独立的 led_strip 实例，互不干扰。
//
// 线程安全：SetYhLed 可从 YH TCP 接收任务调用，内部加锁。
class YhWs2812Led {
public:
    explicit YhWs2812Led(gpio_num_t gpio);
    ~YhWs2812Led();

    // YH SET_LED：on=true 点亮（白色低亮度），on=false 熄灭。
    // 返回是否真正操作了硬件（GPIO_NUM_NC 时返回 false）。
    bool SetYhLed(bool on);

    bool last_state() const { return last_state_; }

private:
    led_strip_handle_t strip_ = nullptr;
    mutable std::mutex mutex_;
    bool last_state_ = false;
};

#endif  // YH_WS2812_LED_H

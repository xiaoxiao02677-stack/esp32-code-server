#ifndef BOARD_H
#define BOARD_H

#include <cJSON.h>
#include <http.h>
#include <web_socket.h>
#include <mqtt.h>
#include <udp.h>
#include <string>
#include <functional>
#include <network_interface.h>

#include "led/led.h"
#include "backlight.h"
#include "camera.h"
#include "assets.h"

/**
 * Network events for unified callback
 */
enum class NetworkEvent {
    Scanning,              // Network is scanning (WiFi scanning, etc.)
    Connecting,            // Network is connecting (data: SSID/network name)
    Connected,             // Network connected successfully (data: SSID/network name)
    Disconnected,          // Network disconnected
    WifiConfigModeEnter,   // Entered WiFi configuration mode
    WifiConfigModeExit,    // Exited WiFi configuration mode
    // Cellular modem specific events
    ModemDetecting,        // Detecting modem (baud rate, module type)
    ModemErrorNoSim,       // No SIM card detected
    ModemErrorRegDenied,   // Network registration denied
    ModemErrorInitFailed,  // Modem initialization failed
    ModemErrorTimeout      // Operation timeout
};

// Power save level enumeration
enum class PowerSaveLevel {
    LOW_POWER,    // Maximum power saving (lowest power consumption)
    BALANCED,     // Medium power saving (balanced)
    PERFORMANCE,  // No power saving (maximum power consumption / full performance)
};

// Network event callback type (event, data)
// data contains additional info like SSID for Connecting/Connected events
using NetworkEventCallback = std::function<void(NetworkEvent event, const std::string& data)>;

void* create_board();
class AudioCodec;
class Display;
class YhWs2812Led;
class Board {
private:
    Board(const Board&) = delete; // 禁用拷贝构造函数
    Board& operator=(const Board&) = delete; // 禁用赋值操作

protected:
    Board();
    std::string GenerateUuid();

    // 软件生成的设备唯一标识
    std::string uuid_;

public:
    static Board& GetInstance() {
        static Board* instance = static_cast<Board*>(create_board());
        return *instance;
    }

    virtual ~Board() = default;
    virtual std::string GetBoardType() = 0;
    virtual std::string GetUuid() { return uuid_; }
    virtual Backlight* GetBacklight() { return nullptr; }
    virtual Led* GetLed();
    // YH Device Protocol 专用 WS2812 句柄（独立于小智状态指示灯，互不干扰）。
    // 默认 nullptr = 该板无 YH 可控 LED；my-s3-tft 等板覆写提供。
    virtual YhWs2812Led* GetWs2812Led() { return nullptr; }
    virtual AudioCodec* GetAudioCodec() = 0;
    virtual bool GetTemperature(float& esp32temp);
    virtual Display* GetDisplay();
    virtual Camera* GetCamera();
    virtual NetworkInterface* GetNetwork() = 0;
    virtual void StartNetwork() = 0;
    virtual void SetNetworkEventCallback(NetworkEventCallback callback) { (void)callback; }
    virtual const char* GetNetworkStateIcon() = 0;
    virtual bool GetBatteryLevel(int &level, bool& charging, bool& discharging);
    virtual std::string GetSystemInfoJson();
    virtual void SetPowerSaveLevel(PowerSaveLevel level) = 0;
    virtual std::string GetBoardJson() = 0;
    virtual std::string GetDeviceStatusJson() = 0;

    /**
     * Apply device configuration pushed from the server (e.g. volume/brightness
     * restored from the cloud on connect/reconnect).
     * Keys are managed by the cloud; only recognized keys are applied and only
     * when the value differs from the current one, so repeated pushes are
     * idempotent. Runs in the main task via Application::Schedule.
     */
    void ApplyDeviceConfig(const cJSON* payload);
};

#define DECLARE_BOARD(BOARD_CLASS_NAME) \
void* create_board() { \
    return new BOARD_CLASS_NAME(); \
}

#endif // BOARD_H

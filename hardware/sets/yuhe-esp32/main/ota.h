#ifndef _OTA_H
#define _OTA_H

#include <expected>
#include <functional>
#include <string>
#include <vector>

#include <esp_err.h>
#include "board.h"
#include "network_error.h"

class Ota {
public:
    Ota();
    ~Ota();

    NetworkResult<> CheckVersion();
    esp_err_t Activate();
    bool HasActivationChallenge() { return has_activation_challenge_; }
    bool HasNewVersion() { return has_new_version_; }
    bool HasMqttConfig() { return has_mqtt_config_; }
    bool HasWebsocketConfig() { return has_websocket_config_; }
    bool HasActivationCode() { return has_activation_code_; }
    bool HasServerTime() { return has_server_time_; }
    bool StartUpgrade(std::function<void(int progress, size_t speed)> callback);
    static bool Upgrade(const std::string& firmware_url, std::function<void(int progress, size_t speed)> callback);
    void MarkCurrentVersionValid();

    const std::string& GetFirmwareVersion() const { return firmware_version_; }
    const std::string& GetCurrentVersion() const { return current_version_; }
    const std::string& GetFirmwareUrl() const { return firmware_url_; }
    const std::string& GetActivationMessage() const { return activation_message_; }
    const std::string& GetActivationCode() const { return activation_code_; }
    std::string GetCheckVersionUrl();

    // 主 OTA URL 失败上报（供 CheckVersion 内部与外部调用方统计）：
    // 连续 kPrimaryFailThreshold 次失败后 GetCheckVersionUrl 返回兜底 URL。
    void ReportPrimaryResult(bool success);
    bool IsFallbackActive() const { return fallback_active_; }

    // 配置版本检查（与固件版本分离）
    std::expected<std::string, std::string> CheckConfigVersion();
    // 获取配置下载 URL
    const std::string& GetConfigDownloadUrl() const { return config_download_url_; }
    // 当前本地配置版本
    const std::string& GetLocalConfigVersion() const { return local_config_version_; }

private:
    std::string activation_message_;
    std::string activation_code_;
    bool has_new_version_ = false;
    bool has_mqtt_config_ = false;
    bool has_websocket_config_ = false;
    bool has_server_time_ = false;
    bool has_activation_code_ = false;
    bool has_serial_number_ = false;
    bool has_activation_challenge_ = false;
    std::string current_version_;
    std::string firmware_version_;
    std::string firmware_url_;
    std::string activation_challenge_;
    std::string serial_number_;
    int activation_timeout_ms_ = 30000;

    std::string config_version_;
    std::string config_download_url_;
    std::string local_config_version_;

    // 主/兜底 OTA URL 切换状态（sandyun.top 主 / yuhe.pro 兜底）
    static constexpr int kPrimaryFailThreshold = 3;
    int primary_fail_count_ = 0;
    bool fallback_active_ = false;

    std::function<void(int progress, size_t speed)> upgrade_callback_;
    std::expected<std::vector<int>, std::string> ParseVersion(const std::string& version);
    bool IsNewVersionAvailable(const std::string& currentVersion, const std::string& newVersion);
    std::string GetActivationPayload();
    std::unique_ptr<Http> SetupHttp();
};

#endif // _OTA_H

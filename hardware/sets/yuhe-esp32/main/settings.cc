#include "settings.h"

#include <esp_log.h>
#include <nvs_flash.h>

#define TAG "Settings"

Settings::Settings(const std::string& ns, bool read_write) : ns_(ns), read_write_(read_write) {
    // nvs_open 失败（分区满 / 命名空间超 15 字符 NVS_NS_NAME_MAX_SIZE 等）时不 abort：
    // 句柄留 0，后续 Get* 走默认值、Set* 打错误日志并跳过——设备保持可用，
    // 配置类写入失败不该把整台机器打崩（曾在 interrupt_config 上翻车）。
    esp_err_t err = nvs_open(ns.c_str(), read_write_ ? NVS_READWRITE : NVS_READONLY, &nvs_handle_);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "nvs_open(%s) failed: %s (handle left invalid, writes will be skipped)",
                 ns.c_str(), esp_err_to_name(err));
        nvs_handle_ = 0;
    }
}

Settings::~Settings() {
    if (nvs_handle_ != 0) {
        if (read_write_ && dirty_) {
            ESP_ERROR_CHECK(nvs_commit(nvs_handle_));
        }
        nvs_close(nvs_handle_);
    }
}

std::string Settings::GetString(const std::string& key, const std::string& default_value) {
    if (nvs_handle_ == 0) {
        return default_value;
    }

    size_t length = 0;
    if (nvs_get_str(nvs_handle_, key.c_str(), nullptr, &length) != ESP_OK) {
        return default_value;
    }

    std::string value;
    value.resize(length);
    ESP_ERROR_CHECK(nvs_get_str(nvs_handle_, key.c_str(), value.data(), &length));
    while (!value.empty() && value.back() == '\0') {
        value.pop_back();
    }
    return value;
}

void Settings::SetString(const std::string& key, const std::string& value) {
    if (nvs_handle_ == 0) {
        ESP_LOGE(TAG, "SetString(%s) skipped: namespace %s not open", key.c_str(), ns_.c_str());
        return;
    }
    if (read_write_) {
        ESP_ERROR_CHECK(nvs_set_str(nvs_handle_, key.c_str(), value.c_str()));
        dirty_ = true;
    } else {
        ESP_LOGW(TAG, "Namespace %s is not open for writing", ns_.c_str());
    }
}

int32_t Settings::GetInt(const std::string& key, int32_t default_value) {
    if (nvs_handle_ == 0) {
        return default_value;
    }

    int32_t value;
    if (nvs_get_i32(nvs_handle_, key.c_str(), &value) != ESP_OK) {
        return default_value;
    }
    return value;
}

void Settings::SetInt(const std::string& key, int32_t value) {
    // 判 0 必须在 read_write_ 之前：无效句柄 + READWRITE 会把
    // ESP_ERR_NVS_INVALID_HANDLE(0x1107) 直接 abort（2026-10-17 崩溃现场）
    if (nvs_handle_ == 0) {
        ESP_LOGE(TAG, "SetInt(%s) skipped: namespace %s not open", key.c_str(), ns_.c_str());
        return;
    }
    if (read_write_) {
        ESP_ERROR_CHECK(nvs_set_i32(nvs_handle_, key.c_str(), value));
        dirty_ = true;
    } else {
        ESP_LOGW(TAG, "Namespace %s is not open for writing", ns_.c_str());
    }
}

bool Settings::GetBool(const std::string& key, bool default_value) {
    if (nvs_handle_ == 0) {
        return default_value;
    }

    uint8_t value;
    if (nvs_get_u8(nvs_handle_, key.c_str(), &value) != ESP_OK) {
        return default_value;
    }
    return value != 0;
}

void Settings::SetBool(const std::string& key, bool value) {
    if (nvs_handle_ == 0) {
        ESP_LOGE(TAG, "SetBool(%s) skipped: namespace %s not open", key.c_str(), ns_.c_str());
        return;
    }
    if (read_write_) {
        ESP_ERROR_CHECK(nvs_set_u8(nvs_handle_, key.c_str(), value ? 1 : 0));
        dirty_ = true;
    } else {
        ESP_LOGW(TAG, "Namespace %s is not open for writing", ns_.c_str());
    }
}

void Settings::EraseKey(const std::string& key) {
    if (nvs_handle_ == 0) {
        ESP_LOGE(TAG, "EraseKey(%s) skipped: namespace %s not open", key.c_str(), ns_.c_str());
        return;
    }
    if (read_write_) {
        auto ret = nvs_erase_key(nvs_handle_, key.c_str());
        if (ret != ESP_ERR_NVS_NOT_FOUND) {
            ESP_ERROR_CHECK(ret);
            // 擦除也要置脏标记：析构时统一 commit，否则删除不落盘
            dirty_ = true;
        }
    } else {
        ESP_LOGW(TAG, "Namespace %s is not open for writing", ns_.c_str());
    }
}

void Settings::EraseAll() {
    if (nvs_handle_ == 0) {
        ESP_LOGE(TAG, "EraseAll() skipped: namespace %s not open", ns_.c_str());
        return;
    }
    if (read_write_) {
        ESP_ERROR_CHECK(nvs_erase_all(nvs_handle_));
        // 擦除也要置脏标记：析构时统一 commit，否则删除不落盘
        dirty_ = true;
    } else {
        ESP_LOGW(TAG, "Namespace %s is not open for writing", ns_.c_str());
    }
}

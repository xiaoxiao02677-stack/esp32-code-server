#include "board.h"
#include "assets/lang_config.h"
#include "audio_codec.h"
#include "display/display.h"
#include "settings.h"
#include "system_info.h"

#include <esp_chip_info.h>
#include <esp_log.h>
#include <esp_ota_ops.h>
#include <esp_random.h>

#include <cmath>

#define TAG "Board"

Board::Board() {
    Settings settings("board", true);
    uuid_ = settings.GetString("uuid");
    if (uuid_.empty()) {
        uuid_ = GenerateUuid();
        settings.SetString("uuid", uuid_);
    }
    ESP_LOGI(TAG, "UUID=%s SKU=%s", uuid_.c_str(), BOARD_NAME);
}

std::string Board::GenerateUuid() {
    // UUID v4 需要 16 字节的随机数据
    uint8_t uuid[16];

    // 使用 ESP32 的硬件随机数生成器
    esp_fill_random(uuid, sizeof(uuid));

    // 设置版本 (版本 4) 和变体位
    uuid[6] = (uuid[6] & 0x0F) | 0x40;  // 版本 4
    uuid[8] = (uuid[8] & 0x3F) | 0x80;  // 变体 1

    // 将字节转换为标准的 UUID 字符串格式
    char uuid_str[37];
    snprintf(uuid_str, sizeof(uuid_str),
             "%02x%02x%02x%02x-%02x%02x-%02x%02x-%02x%02x-%02x%02x%02x%02x%02x%02x", uuid[0],
             uuid[1], uuid[2], uuid[3], uuid[4], uuid[5], uuid[6], uuid[7], uuid[8], uuid[9],
             uuid[10], uuid[11], uuid[12], uuid[13], uuid[14], uuid[15]);

    return std::string(uuid_str);
}

bool Board::GetBatteryLevel(int& level, bool& charging, bool& discharging) { return false; }

bool Board::GetTemperature(float& esp32temp) { return false; }

Display* Board::GetDisplay() {
    static NoDisplay display;
    return &display;
}

Camera* Board::GetCamera() { return nullptr; }

Led* Board::GetLed() {
    static NoLed led;
    return &led;
}

void Board::ApplyDeviceConfig(const cJSON* payload) {
    if (!cJSON_IsObject(payload)) {
        ESP_LOGW(TAG, "Ignore invalid device_config payload: not an object");
        return;
    }

    bool changed = false;
    int applied_volume = -1;
    int applied_brightness = -1;

    auto volume = cJSON_GetObjectItem(payload, "volume");
    if (cJSON_IsNumber(volume)) {
        // Integrality + range check on valuedouble first: a fractional value
        // such as 100.5 must be rejected instead of truncated to 100 by valueint.
        double dv = volume->valuedouble;
        if (dv == std::floor(dv) && dv >= 0 && dv <= 100) {
            int v = volume->valueint;
            auto codec = GetAudioCodec();
            if (codec != nullptr && codec->output_volume() != v) {
                codec->SetOutputVolume(v);  // AudioCodec base class persists to NVS
                applied_volume = v;
                changed = true;
            }
        } else {
            ESP_LOGW(TAG, "Ignore fractional/out-of-range device_config volume: %.1f", dv);
        }
    } else if (volume != nullptr) {
        ESP_LOGW(TAG, "Ignore invalid device_config volume value");
    }

    auto brightness = cJSON_GetObjectItem(payload, "brightness");
    if (cJSON_IsNumber(brightness)) {
        double db = brightness->valuedouble;
        if (db == std::floor(db) && db >= 0 && db <= 100) {
            int b = brightness->valueint;
            auto backlight = GetBacklight();
            if (backlight != nullptr && backlight->brightness() != b) {
                // Only apply the final value; Backlight itself also compares and
                // persists to NVS (display/brightness) when permanent=true.
                backlight->SetBrightness(static_cast<uint8_t>(b), true);
                applied_brightness = b;
                changed = true;
            }
        } else {
            ESP_LOGW(TAG, "Ignore fractional/out-of-range device_config brightness: %.1f", db);
        }
    } else if (brightness != nullptr) {
        ESP_LOGW(TAG, "Ignore invalid device_config brightness value");
    }
    // Extension point: future cloud-managed keys (e.g. theme) get a new case here.

    if (changed) {
        ESP_LOGI(TAG, "应用云端配置 volume=%s brightness=%s",
                 applied_volume >= 0 ? std::to_string(applied_volume).c_str() : "keep",
                 applied_brightness >= 0 ? std::to_string(applied_brightness).c_str() : "keep");
    } else {
        ESP_LOGI(TAG, "Cloud device config matches local state, nothing to apply");
    }
}

std::string Board::GetSystemInfoJson() {
    /*
        {
            "version": 2,
            "flash_size": 4194304,
            "psram_size": 0,
            "minimum_free_heap_size": 123456,
            "mac_address": "00:00:00:00:00:00",
            "uuid": "00000000-0000-0000-0000-000000000000",
            "chip_model_name": "esp32s3",
            "chip_info": {
                "model": 1,
                "cores": 2,
                "revision": 0,
                "features": 0
            },
            "application": {
                "name": "my-app",
                "version": "1.0.0",
                "compile_time": "2021-01-01T00:00:00Z"
                "idf_version": "4.2-dev"
                "elf_sha256": ""
            },
            "partition_table": [
                "app": {
                    "label": "app",
                    "type": 1,
                    "subtype": 2,
                    "address": 0x10000,
                    "size": 0x100000
                }
            ],
            "ota": {
                "label": "ota_0"
            },
            "board": {
                ...
            }
        }
    */
    std::string json = R"({"version":2,"language":")" + std::string(Lang::CODE) + R"(",)";
    json += R"("flash_size":)" + std::to_string(SystemInfo::GetFlashSize()) + R"(,)";
    json += R"("minimum_free_heap_size":")" + std::to_string(SystemInfo::GetMinimumFreeHeapSize()) +
            R"(",)";
    json += R"("mac_address":")" + SystemInfo::GetMacAddress() + R"(",)";
    json += R"("uuid":")" + uuid_ + R"(",)";
    json += R"("chip_model_name":")" + SystemInfo::GetChipModelName() + R"(",)";

    esp_chip_info_t chip_info;
    esp_chip_info(&chip_info);
    json += R"("chip_info":{)";
    json += R"("model":)" + std::to_string(chip_info.model) + R"(,)";
    json += R"("cores":)" + std::to_string(chip_info.cores) + R"(,)";
    json += R"("revision":)" + std::to_string(chip_info.revision) + R"(,)";
    json += R"("features":)" + std::to_string(chip_info.features) + R"(},)";

    auto app_desc = esp_app_get_description();
    json += R"("application":{)";
    json += R"("name":")" + std::string(app_desc->project_name) + R"(",)";
    json += R"("version":")" + std::string(app_desc->version) + R"(",)";
    json += R"("compile_time":")" + std::string(app_desc->date) + R"(T)" +
            std::string(app_desc->time) + R"(Z",)";
    json += R"("idf_version":")" + std::string(app_desc->idf_ver) + R"(",)";
    char sha256_str[65];
    for (int i = 0; i < 32; i++) {
        snprintf(sha256_str + i * 2, sizeof(sha256_str) - i * 2, "%02x",
                 app_desc->app_elf_sha256[i]);
    }
    json += R"("elf_sha256":")" + std::string(sha256_str) + R"(")";
    json += R"(},)";

    json += R"("partition_table": [)";
    esp_partition_iterator_t it =
        esp_partition_find(ESP_PARTITION_TYPE_ANY, ESP_PARTITION_SUBTYPE_ANY, NULL);
    while (it) {
        const esp_partition_t* partition = esp_partition_get(it);
        json += R"({)";
        json += R"("label":")" + std::string(partition->label) + R"(",)";
        json += R"("type":)" + std::to_string(partition->type) + R"(,)";
        json += R"("subtype":)" + std::to_string(partition->subtype) + R"(,)";
        json += R"("address":)" + std::to_string(partition->address) + R"(,)";
        json += R"("size":)" + std::to_string(partition->size) + R"(},)";
        it = esp_partition_next(it);
    }
    json.pop_back();  // Remove the last comma
    json += R"(],)";

    json += R"("ota":{)";
    auto ota_partition = esp_ota_get_running_partition();
    json += R"("label":")" + std::string(ota_partition->label) + R"(")";
    json += R"(},)";

    // Append display info
    auto display = GetDisplay();
    if (display) {
        json += R"("display":{)";
        if (display->IsMonochrome()) {
            json += R"("monochrome":)" + std::string("true") + R"(,)";
        } else {
            json += R"("monochrome":)" + std::string("false") + R"(,)";
        }
        json += R"("width":)" + std::to_string(display->width()) + R"(,)";
        json += R"("height":)" + std::to_string(display->height()) + R"(,)";
        json.pop_back();  // Remove the last comma
    }
    json += R"(},)";

    json += R"("board":)" + GetBoardJson();

    // Close the JSON object
    json += R"(})";
    return json;
}

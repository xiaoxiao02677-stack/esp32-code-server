#include "board.h"
#include "assets/lang_config.h"
#include "audio_codec.h"
#include "display/display.h"
#include "settings.h"
#include "system_info.h"
#include "application.h"

#include <esp_chip_info.h>
#include <esp_log.h>
#include <esp_ota_ops.h>
#include <esp_random.h>

#include <cJSON.h>
#include <cmath>

#define TAG "Board"

// 汉字→拼音映射表（服务器下发中文唤醒词 → MultiNet 拼音命令）。
// 覆盖常见唤醒词用字；未收录的字会打 WARN 并跳过该词（该词不参与匹配，
// 其余词不受影响）。服务器也可直接下发拼音（跳过转换）。
static const struct { const char* han; const char* pinyin; } kWakeWordPinyinMap[] = {
    {"你", "ni3"}, {"好", "hao3"}, {"小", "xiao3"}, {"智", "zhi4"}, {"嗨", "hai1"},
    {"嘿", "hei1"}, {"乐", "le4"}, {"鑫", "xin1"}, {"爱", "ai4"}, {"同", "tong2"},
    {"学", "xue2"}, {"猫", "mao1"}, {"咪", "mi1"}, {"狗", "gou3"}, {"宝", "bao3"},
    {"贝", "bei4"}, {"阿", "a1"}, {"福", "fu2"}, {"安", "an1"}, {"妮", "ni2"},
    {"克", "ke4"}, {"丽", "li4"}, {"亚", "ya4"}, {"米", "mi3"}, {"娅", "ya4"},
    {"醒", "xing3"}, {"开", "kai1"}, {"始", "shi3"}, {"停", "ting2"}, {"休", "xiu1"},
    {"等", "deng3"}, {"待", "dai4"}, {"在", "zai4"}, {"吗", "ma5"}, {"吧", "ba5"},
    {"啊", "a5"}, {"呀", "ya5"}, {"哦", "o5"}, {"哈", "ha1"}, {"啦", "la5"},
    {"屿", "yu3"}, {"禾", "he2"}, {"工", "gong1"}, {"坊", "fang1"}, {"小禾", "xiao3 he2"},
    {"琳", "lin2"}, {"玲", "ling2"}, {"明", "ming2"}, {"敏", "min3"}, {"君", "jun1"},
    {"帅", "shuai4"}, {"哥", "ge1"}, {"姐", "jie3"}, {"美", "mei3"}, {"女", "nv3"},
    {"神", "shen2"}, {"仙", "xian1"}, {"侠", "xia2"}, {"客", "ke4"}, {"主", "zhu3"},
    {"人", "ren2"}, {"老", "lao3"}, {"板", "ban3"}, {"爸", "ba4"}, {"妈", "ma1"},
    {"爷", "ye2"}, {"奶", "nai3"}, {"叔", "shu1"}, {"姨", "yi2"}, {"哥", "ge1"},
    {"弟", "di4"}, {"妹", "mei4"}, {"朋", "peng2"}, {"友", "you3"}, {"同", "tong2"},
    {"事", "shi4"}, {"喂", "wei4"}, {"哈喽", "ha1 lou2"}, {"hello", "hello"},
};

// 汉字短语 → 拼音串（逐字查表，空格分隔；含未收录字符返回 false）
static bool HanziToPinyin(const std::string& hanzi, std::string& pinyin_out) {
    // 已经是纯 ASCII（服务器直接下发拼音，如 "ni3 hao3"）则原样使用
    bool all_ascii = true;
    for (unsigned char c : hanzi) {
        if (c > 127) { all_ascii = false; break; }
    }
    if (all_ascii) {
        pinyin_out = hanzi;
        return true;
    }
    pinyin_out.clear();
    size_t i = 0;
    bool ok = true;
    while (i < hanzi.size()) {
        // 多字词条优先匹配（如 "小禾"/"哈喽"）
        bool matched = false;
        for (const auto& kv : kWakeWordPinyinMap) {
            size_t len = strlen(kv.han);
            if (hanzi.compare(i, len, kv.han) == 0) {
                if (!pinyin_out.empty()) pinyin_out += " ";
                pinyin_out += kv.pinyin;
                i += len;
                matched = true;
                break;
            }
        }
        if (!matched) {
            // 跳过标点/空白继续（允许"你好!"这类带标点的下发值）
            if (hanzi[i] == ' ' || hanzi[i] == ';' || hanzi[i] == ',' ||
                hanzi[i] == '!' || hanzi[i] == '.' || (unsigned char)hanzi[i] == 0xEF) {
                i += 1;
                continue;
            }
            // 未知汉字：跳 3 字节（UTF-8 中文），标记失败
            ESP_LOGW(TAG, "Wake-word pinyin map miss: byte@%zu in '%s'", i, hanzi.c_str());
            ok = false;
            i += 3;
        }
    }
    return ok && !pinyin_out.empty();
}

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

    // 服务器下发动态唤醒词（MultiNet 引擎）：字符串或字符串数组，多词任意一个命中即唤醒
    auto wake_word = cJSON_GetObjectItem(payload, "wake_word");
    if (cJSON_IsString(wake_word) || cJSON_IsArray(wake_word)) {
        std::vector<std::string> hanzi_words;
        if (cJSON_IsString(wake_word)) {
            hanzi_words.push_back(wake_word->valuestring);
        } else {
            cJSON* item = nullptr;
            cJSON_ArrayForEach(item, wake_word) {
                if (cJSON_IsString(item) && item->valuestring[0] != '\0') {
                    hanzi_words.push_back(item->valuestring);
                }
            }
        }
        if (!hanzi_words.empty()) {
            auto& app = Application::GetInstance();
            auto& audio = app.GetAudioService();
            if (audio.SupportsDynamicWakeWords()) {
                std::vector<std::string> pinyins;
                std::vector<std::string> displays;
                for (const auto& w : hanzi_words) {
                    std::string py;
                    if (HanziToPinyin(w, py)) {
                        pinyins.push_back(py);
                        displays.push_back(w);
                    }
                }
                if (!pinyins.empty()) {
                    if (audio.UpdateWakeWordCommands(pinyins, displays)) {
                        changed = true;
                        ESP_LOGI(TAG, "应用云端唤醒词: %zu 个（首个: %s）",
                                 pinyins.size(), hanzi_words[0].c_str());
                    }
                } else {
                    ESP_LOGW(TAG, "云端唤醒词全部无法转换为拼音，忽略");
                }
            } else {
                ESP_LOGW(TAG, "当前音频引擎不支持动态唤醒词（需 MultiNet 模型），忽略 wake_word 配置");
            }
        }
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

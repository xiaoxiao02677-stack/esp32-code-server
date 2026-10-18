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
// 拼音须为 esp-sr 官方 multinet_pinyin.py 的不带调格式（lazy_pinyin 输出，
// 如 "打开空调"→"da kai kong tiao"）；带声调数字（"ni3 hao3"）MN7 无法匹配。
// 覆盖常见唤醒词用字；未收录的字会打 WARN 并跳过该词（该词不参与匹配，
// 其余词不受影响）。服务器也可直接下发拼音（跳过转换）。
// 匹配按表序逐条进行：多字词条必须排在单字前缀之前（先长后短），
// 否则"哈喽"会先命中单字"哈"，剩余"喽"未收录导致整词被丢弃。
static const struct { const char* han; const char* pinyin; } kWakeWordPinyinMap[] = {
    // 多字词条置顶：确保逐条匹配时先于单字前缀命中（先长后短，越长的越靠前）
    {"早上好", "zao shang hao"}, {"小禾", "xiao he"}, {"哈喽", "ha lou"},
    {"hello", "hello"},
    {"我们", "wo men"}, {"什么", "shen me"}, {"谢谢", "xie xie"},
    {"再见", "zai jian"}, {"你好", "ni hao"}, {"小爱", "xiao ai"},
    {"晚安", "wan an"}, {"早安", "zao an"}, {"早上", "zao shang"},
    {"音乐", "yin yue"}, {"播放", "bo fang"}, {"回答", "hui da"},
    {"天气", "tian qi"}, {"起床", "qi chuang"}, {"睡觉", "shui jiao"},
    {"开始", "kai shi"}, {"停止", "ting zhi"}, {"等待", "deng dai"},
    // 问候/称呼
    {"你", "ni"}, {"早", "zao"}, {"上", "shang"}, {"好", "hao"}, {"的", "de"}, {"我", "wo"},
    {"是", "shi"}, {"在", "zai"}, {"有", "you"}, {"不", "bu"}, {"了", "le"},
    {"他", "ta"}, {"她", "ta"}, {"它", "ta"}, {"们", "men"}, {"这", "zhe"},
    {"那", "na"}, {"里", "li"}, {"哪", "na"}, {"儿", "er"}, {"时", "shi"},
    {"间", "jian"}, {"会", "hui"}, {"到", "dao"}, {"说", "shuo"}, {"要", "yao"},
    {"去", "qu"}, {"来", "lai"}, {"看", "kan"}, {"想", "xiang"}, {"没", "mei"},
    {"做", "zuo"}, {"能", "neng"}, {"可", "ke"}, {"以", "yi"}, {"就", "jiu"},
    {"也", "ye"}, {"都", "dou"}, {"很", "hen"}, {"太", "tai"}, {"真", "zhen"},
    {"行", "xing"}, {"听", "ting"}, {"问", "wen"}, {"答", "da"}, {"叫", "jiao"},
    {"名", "ming"}, {"字", "zi"}, {"宝", "bao"}, {"贝", "bei"}, {"亲", "qin"},
    {"爱", "ai"}, {"哥", "ge"}, {"姐", "jie"}, {"弟", "di"}, {"妹", "mei"},
    {"爸", "ba"}, {"妈", "ma"}, {"爷", "ye"}, {"奶", "nai"}, {"叔", "shu"},
    {"阿", "a"}, {"姨", "yi"}, {"老", "lao"}, {"师", "shi"}, {"大", "da"},
    {"小", "xiao"}, {"多", "duo"}, {"少", "shao"}, {"请", "qing"}, {"谢", "xie"},
    {"再", "zai"}, {"见", "jian"}, {"回", "hui"},
    // 语气词
    {"吧", "ba"}, {"呢", "ne"}, {"嘛", "ma"}, {"吗", "ma"}, {"啊", "a"},
    {"呀", "ya"}, {"哦", "o"}, {"嗯", "en"}, {"喂", "wei"}, {"嗨", "hai"},
    {"嘿", "hei"}, {"哈", "ha"}, {"啦", "la"},
    // 天气/环境
    {"天", "tian"}, {"气", "qi"}, {"晴", "qing"}, {"雨", "yu"}, {"雪", "xue"},
    {"风", "feng"}, {"冷", "leng"}, {"热", "re"}, {"开", "kai"}, {"关", "guan"},
    {"灯", "deng"}, {"打", "da"}, {"音", "yin"}, {"乐", "le"}, {"歌", "ge"},
    {"曲", "qu"}, {"播", "bo"}, {"放", "fang"}, {"停", "ting"}, {"暂", "zhan"},
    // 数字
    {"一", "yi"}, {"二", "er"}, {"三", "san"}, {"四", "si"}, {"五", "wu"},
    {"六", "liu"}, {"七", "qi"}, {"八", "ba"}, {"九", "jiu"}, {"十", "shi"},
    {"百", "bai"}, {"千", "qian"}, {"万", "wan"}, {"点", "dian"}, {"半", "ban"},
    {"分", "fen"}, {"秒", "miao"},
    // 时间
    {"今", "jin"}, {"明", "ming"}, {"昨", "zuo"}, {"晚", "wan"}, {"醒", "xing"},
    {"起", "qi"}, {"床", "chuang"}, {"睡", "shui"}, {"觉", "jiao"},
    // 其他既有/常见名
    {"智", "zhi"}, {"鑫", "xin"}, {"同", "tong"}, {"学", "xue"}, {"猫", "mao"},
    {"咪", "mi"}, {"狗", "gou"}, {"福", "fu"}, {"安", "an"}, {"妮", "ni"},
    {"克", "ke"}, {"丽", "li"}, {"亚", "ya"}, {"米", "mi"}, {"娅", "ya"},
    {"始", "shi"}, {"休", "xiu"}, {"等", "deng"}, {"待", "dai"}, {"禾", "he"},
    {"工", "gong"}, {"坊", "fang"}, {"琳", "lin"}, {"玲", "ling"}, {"敏", "min"},
    {"君", "jun"}, {"帅", "shuai"}, {"美", "mei"}, {"女", "nv"}, {"神", "shen"},
    {"仙", "xian"}, {"侠", "xia"}, {"客", "ke"}, {"主", "zhu"}, {"人", "ren"},
    {"板", "ban"}, {"朋", "peng"}, {"友", "you"}, {"事", "shi"}, {"屿", "yu"},
    {"灵", "ling"},
};

// 汉字短语 → 拼音串（逐字查表，空格分隔；含未收录字符返回 false）
static bool HanziToPinyin(const std::string& hanzi, std::string& pinyin_out) {
    // 已经是纯 ASCII（服务器直接下发拼音，如 "ni hao"）则原样使用
    // 注意：若含声调数字（"ni3 hao3"）会被 NVS 自愈逻辑判为过时格式丢弃
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
            // 未知字符：逐字节跳过（兼容4字节UTF-8如emoji/罕见字）
            ESP_LOGW(TAG, "Wake-word pinyin map miss: byte@%zu in '%s'", i, hanzi.c_str());
            ok = false;
            i += 1;
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
            // 空字符串视为"清空"：不加入列表，走 hanzi_words.empty() 的清空分支
            if (wake_word->valuestring[0] != '\0') {
                hanzi_words.push_back(wake_word->valuestring);
            }
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
            // 不预查 SupportsDynamicWakeWords：引擎未初始化时 AudioService 内部会
            // 缓存（InitializeAudioEngine 成功后自动应用）；仅引擎就绪但不是
            // MultiNet（如纯 WakeNet 构建）时才真正丢弃。
            // UpdateWakeWordCommands 返回 false 有两种含义，用 SupportsDynamicWakeWords
            // 区分（仅影响日志，不影响行为）：引擎支持但命令表相同为幂等跳过，属正常；
            // 其余才是引擎真不支持。
            std::vector<std::string> pinyins;
            std::vector<std::string> displays;
            for (const auto& w : hanzi_words) {
                std::string py;
                if (HanziToPinyin(w, py)) {
                    pinyins.push_back(py);
                    displays.push_back(w);
                } else {
                    // 明示丢弃的词，避免误判为"未变化，跳过更新"
                    ESP_LOGW(TAG, "唤醒词 '%s' 含未收录字，无法转拼音，已丢弃该词", w.c_str());
                }
            }
            if (!pinyins.empty()) {
                if (audio.UpdateWakeWordCommands(pinyins, displays)) {
                    changed = true;
                    // 用户在串口一眼可见：唤醒词从此刻起喊了就能醒
                    // displays[0] 与实际生效的首条拼音命令一一对应
                    ESP_LOGI(TAG, "云端唤醒词已生效: %d 个 [%s]（开机即用，已存本地）",
                             static_cast<int>(pinyins.size()), displays[0].c_str());
                } else if (audio.SupportsDynamicWakeWords()) {
                    // MultiNet 命令表与当前完全一致，无需重建（幂等，正常现象）。
                    // 注意：不能笼统打"引擎不支持"——命令表相同时引擎也会返回 false
                    ESP_LOGI(TAG, "云端唤醒词未变化，跳过更新（%zu 个）", pinyins.size());
                } else {
                    ESP_LOGW(TAG, "当前音频引擎不支持动态唤醒词（需 MultiNet 模型），已忽略");
                }
            } else {
                ESP_LOGW(TAG, "云端唤醒词全部无法转换为拼音，忽略");
            }
        } else {
            // 空字符串/空数组语义：清空云端下发的唤醒词，恢复本地默认词
            // （index.json 或 Kconfig 中的"你好小禾"），并删除 NVS 缓存
            auto& app = Application::GetInstance();
            auto& audio = app.GetAudioService();
            if (audio.ClearWakeWordCommands()) {
                changed = true;
                ESP_LOGI(TAG, "已清空云端唤醒词，恢复默认");
            } else {
                // 引擎不支持/未就绪且无缓存：本机本就用默认词，视为已满足
                ESP_LOGI(TAG, "无需清空云端唤醒词（当前已是默认或引擎不支持）");
            }
        }
    }
    // Extension point: future cloud-managed keys (e.g. theme) get a new case here.

    // 唤醒词阈值动态调整（服务器下发）
    // 用户区间 0~100：0=最灵敏、100=最不灵敏（固件侧 0 夹取到 esp-sr 最低有效值 0.01）
    auto threshold = cJSON_GetObjectItem(payload, "wake_word_threshold");
    if (cJSON_IsNumber(threshold)) {
        int t = threshold->valueint;
        if (t >= 0 && t <= 100) {
            Settings settings("wake_word_config", true);
            settings.SetInt("threshold", t);
            auto& app = Application::GetInstance();
            auto& audio = app.GetAudioService();
            audio.SetWakeWordThreshold(t / 100.0f);
            changed = true;
            ESP_LOGI(TAG, "云端唤醒词阈值已更新: %d%%", t);
        }
    }
    // 唤醒词时长动态调整（服务器下发）
    auto duration = cJSON_GetObjectItem(payload, "wake_word_duration");
    if (cJSON_IsNumber(duration)) {
        int d = duration->valueint;
        if (d >= 500 && d <= 5000) {
            Settings settings("wake_word_config", true);
            settings.SetInt("duration", d);
            auto& app = Application::GetInstance();
            auto& audio = app.GetAudioService();
            audio.SetWakeWordDuration(d);
            changed = true;
            ESP_LOGI(TAG, "云端唤醒词时长已更新: %dms", d);
        }
    }

    // 实时打断灵敏度动态调整（服务器下发）：0~100，0=最灵敏、100=最难打断。
    // 映射到 VAD 人声确认窗 0~2000ms（AfeAudioEngine::SetInterruptThreshold）。
    auto interrupt = cJSON_GetObjectItem(payload, "interrupt_threshold");
    if (cJSON_IsNumber(interrupt)) {
        int it = interrupt->valueint;
        if (it >= 0 && it <= 100) {
            Settings settings("interrupt_config", true);
            settings.SetInt("threshold", it);
            auto& app = Application::GetInstance();
            auto& audio = app.GetAudioService();
            audio.SetInterruptThreshold(it);
            changed = true;
            ESP_LOGI(TAG, "云端实时打断阈值已更新: %d", it);
        }
    }

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

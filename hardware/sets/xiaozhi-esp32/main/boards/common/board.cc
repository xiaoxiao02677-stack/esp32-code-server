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
        // 服务端直接下发拼音：清洗成引擎唯一接受的形态。
        // esp_mn 只认小写音节，'Ni Hao' / 'ni  hao' 会被静默拒绝；'|' 是 NVS
        // 列表分隔符，混进命令词会把一条拆成两条；控制字符同理。
        std::string clean;
        clean.reserve(hanzi.size());
        bool last_space = true;  // 前导空格不放行
        for (unsigned char c : hanzi) {
            if (c == '|' || c < 0x20 || c == 0x7F) {
                continue;
            }
            char ch = static_cast<char>(c);
            if (ch == ' ') {
                if (!clean.empty() && !last_space) {
                    clean += ' ';
                    last_space = true;
                }
                continue;
            }
            if (ch >= 'A' && ch <= 'Z') {
                ch = static_cast<char>(ch - 'A' + 'a');
            }
            clean += ch;
            last_space = false;
        }
        if (!clean.empty() && clean.back() == ' ') {
            clean.pop_back();
        }
        if (clean.empty()) {
            ESP_LOGW(TAG, "Wake-word pinyin payload is empty after sanitizing");
            return false;
        }
        pinyin_out = clean;
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

    // 服务器下发动态唤醒词（MultiNet 引擎）：字符串或字符串数组，多词任意一个命中即唤醒。
    //   wake_word         —— 识别命令词：无调拼音（推荐，如 "ni hao xiao he"，任意中文词可用）；
    //                        也兼容汉字（旧数据，走内置字表转换，仅覆盖常见字）
    //   wake_word_display —— 展示原文（可选，如 "你好小禾"）：唤醒后作为 detect text 上报
    //                        给服务端（问候语/日志），不是待机屏文案。按索引与 wake_word
    //                        对齐；缺省或数量不匹配时回落用 wake_word 原值
    // 注意：下面这个 if 没有 else，唤醒词共有三种语义，本轮排查中已被多人读串，
    // 写代码/排查前务必分清（三者的设备侧后果完全不同）：
    //   1) 缺键（payload 里没有 wake_word）—— 不进 if，不 update 也不 clear，
    //      设备保留 NVS 里上一次成功生效的词；表现为"改了词但设备还认旧的"
    //   2) 空数组/空串（"wake_word": [] 或 [""]）—— 进 if 但 has_any_word 为 false，
    //      落到 else 分支调 ClearWakeWordCommands，清空并恢复本地默认词
    //   3) 有词但全部转不出拼音 —— 进 if 且 has_any_word 为 true，卡在转换环节
    //      只打 "云端唤醒词全部无法转换为拼音，忽略"、随后自然跳出 if；既不 update 也不 clear，
    //      设备同样保留旧表（和 1 的后果一样，但日志完全不同，别混）
    // 服务端超 5 项时整块 config 会被跳过 ⇒ 属于 1)；表外字导致整词丢弃 ⇒ 属于 3)。
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
                // 保留位置：空串也 push，保证与 wake_word_display 的下标严格对齐。
                // 这里若直接过滤空串，而 display 数组按原始下标填充，
                // 就会出现"喊 A 显示 B"（例：['a','','c'] + ['甲','乙','丙']
                // → 压缩成 ['a','c'] 却仍按 0/1 取 display，c 显示成"乙"）。
                // 空占位在下面的转拼音循环里按位置跳过。
                hanzi_words.push_back(cJSON_IsString(item) ? item->valuestring : "");
            }
        }

        // 展示文案：按索引与 hanzi_words 配对。少于命令词时缺位逐条回落原值
        // （Python 侧允许只给前几条 display）；多于时截断多余项（不能补齐，否则串位）
        std::vector<std::string> display_words;
        auto wake_word_display = cJSON_GetObjectItem(payload, "wake_word_display");
        if (cJSON_IsString(wake_word_display)) {
            const char* d = wake_word_display->valuestring;
            if (d[0] != '\0' && hanzi_words.size() == 1) {
                display_words.emplace_back(d);
            } else if (d[0] != '\0') {
                ESP_LOGW(TAG, "wake_word_display 为字符串但 wake_word 有 %zu 项，回落用 wake_word 作展示",
                         hanzi_words.size());
            }
        } else if (cJSON_IsArray(wake_word_display)) {
            cJSON* d = nullptr;
            cJSON_ArrayForEach(d, wake_word_display) {
                display_words.push_back(cJSON_IsString(d) ? d->valuestring : "");
            }
            if (display_words.size() > hanzi_words.size()) {
                ESP_LOGW(TAG, "wake_word_display 数量(%zu)多于 wake_word(%zu)，多余项忽略",
                         display_words.size(), hanzi_words.size());
                display_words.resize(hanzi_words.size());
            }
        } else if (wake_word_display != nullptr && !cJSON_IsNull(wake_word_display)) {
            ESP_LOGW(TAG, "wake_word_display 类型非法（仅支持字符串/字符串数组），回落用 wake_word 作展示");
        }

        // 全为空占位（如 [""]）等价于"清空"：必须落到 else 分支调 ClearWakeWordCommands，
        // 否则清空唤醒词的指令会被静默吞掉（改成保留占位后引入的回归）。
        bool has_any_word = false;
        for (const auto& w : hanzi_words) {
            if (!w.empty()) {
                has_any_word = true;
                break;
            }
        }
        if (has_any_word) {
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
            // 用原数组索引：转拼音失败的词被丢弃时，pinyins/displays 同步跳过，
            // 两边长度始终一致，不会出现命令词与展示文本错位
            for (size_t i = 0; i < hanzi_words.size(); ++i) {
                const std::string& w = hanzi_words[i];
                if (w.empty()) {
                    // 服务端下发的空占位：按位置跳过（display 同步不取），保持两数组对齐。
                    // 正常情况下不会出现——Python push_wake_words / push_device_config
                    // 已按下标成对剔除空项，此处纯防御。
                    continue;
                }
                std::string py;
                if (HanziToPinyin(w, py)) {
                    pinyins.push_back(py);
                    displays.push_back(i < display_words.size() && !display_words[i].empty()
                                           ? display_words[i]
                                           : w);
                } else {
                    // 明示丢弃的词，避免误判为"未变化，跳过更新"
                    ESP_LOGW(TAG, "唤醒词 '%s' 含未收录字，无法转拼音，已丢弃该词"
                                  "（服务端改发无调拼音 + wake_word_display 即可绕过内置表）",
                             w.c_str());
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
            // （index.json 或 Kconfig 中的"你好小禾"），并删除 NVS 缓存。
            // 注意：只有这里会清空。缺键和"全部转不出拼音"都不会走到这里，
            // 它们保留 NVS 旧表（详见上方 wake_word 取值前三类语义的注释）。
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
    // NVS 命名空间上限 15 字符（NVS_NS_NAME_MAX_SIZE=16 含 null），改名须 ≤15
    auto threshold = cJSON_GetObjectItem(payload, "wake_word_threshold");
    if (cJSON_IsNumber(threshold)) {
        int t = threshold->valueint;
        if (t >= 0 && t <= 100) {
            Settings settings("wake_word_cfg", true);
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
            Settings settings("wake_word_cfg", true);
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
    // 注意 "interrupt_config" 是 16 字符、超 NVS 命名空间上限（15），曾导致
    // nvs_open 静默失败 → SetInt 拿无效句柄 abort 重启；因此命名为 "interrupt_cfg"。
    auto interrupt = cJSON_GetObjectItem(payload, "interrupt_threshold");
    if (cJSON_IsNumber(interrupt)) {
        int it = interrupt->valueint;
        if (it >= 0 && it <= 100) {
            Settings settings("interrupt_cfg", true);
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

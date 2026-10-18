#include "custom_wake_word.h"
#include "audio_service.h"
#include "system_info.h"
#include "assets.h"
#include "settings.h"

#include <esp_log.h>
#include <esp_mn_iface.h>
#include <esp_mn_models.h>
#include <esp_mn_speech_commands.h>
#include <cJSON.h>
#include <sstream>

#define TAG "CustomWakeWord"

CustomWakeWord::CustomWakeWord()
    : wake_word_opus_() {
}

CustomWakeWord::~CustomWakeWord() {
    if (multinet_model_data_ != nullptr && multinet_ != nullptr) {
        multinet_->destroy(multinet_model_data_);
        multinet_model_data_ = nullptr;
    }

    if (wake_word_encode_task_stack_ != nullptr) {
        heap_caps_free(wake_word_encode_task_stack_);
    }

    if (wake_word_encode_task_buffer_ != nullptr) {
        heap_caps_free(wake_word_encode_task_buffer_);
    }

    if (owns_models_ && models_ != nullptr) {
        esp_srmodel_deinit(models_);
    }
}

void CustomWakeWord::ParseWakenetModelConfig() {
    // Read index.json
    auto& assets = Assets::GetInstance();
    void* ptr = nullptr;
    size_t size = 0;
    if (!assets.GetAssetData("index.json", ptr, size)) {
        ESP_LOGE(TAG, "Failed to read index.json");
        return;
    }
    cJSON* root = cJSON_ParseWithLength(static_cast<char*>(ptr), size);
    if (root == nullptr) {
        ESP_LOGE(TAG, "Failed to parse index.json");
        return;
    }
    cJSON* multinet_model = cJSON_GetObjectItem(root, "multinet_model");
    if (cJSON_IsObject(multinet_model)) {
        cJSON* language = cJSON_GetObjectItem(multinet_model, "language");
        cJSON* duration = cJSON_GetObjectItem(multinet_model, "duration");
        cJSON* threshold = cJSON_GetObjectItem(multinet_model, "threshold");
        cJSON* commands = cJSON_GetObjectItem(multinet_model, "commands");
        if (cJSON_IsString(language)) {
            language_ = language->valuestring;
        }
        if (cJSON_IsNumber(duration)) {
            duration_ = duration->valueint;
        }
        if (cJSON_IsNumber(threshold)) {
            threshold_ = threshold->valuedouble;
        }
        if (cJSON_IsArray(commands)) {
            for (int i = 0; i < cJSON_GetArraySize(commands); i++) {
                cJSON* command = cJSON_GetArrayItem(commands, i);
                if (cJSON_IsObject(command)) {
                    cJSON* command_name = cJSON_GetObjectItem(command, "command");
                    cJSON* text = cJSON_GetObjectItem(command, "text");
                    cJSON* action = cJSON_GetObjectItem(command, "action");
                    if (cJSON_IsString(command_name) && cJSON_IsString(text) && cJSON_IsString(action)) {
                        commands_.push_back({command_name->valuestring, text->valuestring, action->valuestring});
                        ESP_LOGI(TAG, "Command: %s, Text: %s, Action: %s", command_name->valuestring, text->valuestring, action->valuestring);
                    }
                }
            }
        }
    }
    cJSON_Delete(root);
}


bool CustomWakeWord::Initialize(AudioCodec* codec, srmodel_list_t* models_list) {
    codec_ = codec;
    commands_.clear();

    if (models_list == nullptr) {
        language_ = "cn";
        models_ = esp_srmodel_init("model");
        owns_models_ = models_ != nullptr;
#ifdef CONFIG_CUSTOM_WAKE_WORD
        threshold_ = CONFIG_CUSTOM_WAKE_WORD_THRESHOLD / 100.0f;
        commands_.push_back({CONFIG_CUSTOM_WAKE_WORD, CONFIG_CUSTOM_WAKE_WORD_DISPLAY, "wake"});
#endif
    } else {
        models_ = models_list;
        ParseWakenetModelConfig();
    }

    if (models_ == nullptr || models_->num == -1) {
        ESP_LOGE(TAG, "Failed to initialize wakenet model");
        return false;
    }

    // 初始化 multinet (命令词识别)
    mn_name_ = esp_srmodel_filter(models_, ESP_MN_PREFIX, language_.c_str());
    if (mn_name_ == nullptr) {
        ESP_LOGW(TAG, "Language '%s' multinet not found, falling back to any multinet model", language_.c_str());
        mn_name_ = esp_srmodel_filter(models_, ESP_MN_PREFIX, NULL);
    }
    if (mn_name_ == nullptr) {
        ESP_LOGE(TAG, "Failed to initialize multinet, mn_name is nullptr");
        ESP_LOGI(TAG, "Please refer to https://pcn7cs20v8cr.feishu.cn/wiki/CpQjwQsCJiQSWSkYEvrcxcbVnwh to add custom wake word");
        return false;
    }

    multinet_ = esp_mn_handle_from_name(mn_name_);
    multinet_model_data_ = multinet_->create(mn_name_, duration_);
    multinet_->set_det_threshold(multinet_model_data_, threshold_);
    input_buffer_.reserve(multinet_->get_samp_chunksize(multinet_model_data_));

    // 暂存默认命令表快照：此时 commands_ 尚未被 NVS 缓存覆盖，
    // 是 index.json 或 Kconfig CONFIG_CUSTOM_WAKE_WORD 的本地默认表，
    // 供 ClearWakeWordCommands() 清空云端唤醒词后恢复默认
    default_commands_ = commands_;

    // 服务器下发阈值/时长的 NVS 恢复：优先用上次云端下发的值
    // （board.cc ApplyDeviceConfig 收到 device_config 时写入 "wake_word_cfg"），
    // 无缓存时保持 index.json/Kconfig 默认。没有这段，重启后阈值会静默回退到
    // 编译期默认，用户在网页上改过的灵敏度"过一夜就失效"。
    // 恢复顺序：先 threshold 后 duration——SetDuration 重建模型时会以当前
    // threshold_ 重设阈值，顺序不会互相覆盖。
    // （曾用名 "wake_word_config" 16 字符超 NVS 命名空间上限 15，nvs_open 永远失败。）
    {
        Settings settings("wake_word_cfg", true);
        int saved_threshold = settings.GetInt("threshold", -1);
        if (saved_threshold >= 0 && saved_threshold <= 100) {
            SetThreshold(saved_threshold / 100.0f);
            ESP_LOGI(TAG, "Restored wake word threshold %d%% from NVS", saved_threshold);
        }
        int saved_duration = settings.GetInt("duration", -1);
        if (saved_duration >= 500 && saved_duration <= 5000) {
            SetDuration(saved_duration);
            ESP_LOGI(TAG, "Restored wake word duration %dms from NVS", saved_duration);
        }
    }

    // 服务器下发唤醒词的 NVS 恢复：优先用上次云端下发的命令表（脱机也可唤醒），
    // 没有缓存时才用本地默认命令（index.json 或 Kconfig CONFIG_CUSTOM_WAKE_WORD）。
    // NVS 格式：pinyin1|pinyin2|... 与 display1|display2|...（'|' 不会出现在拼音里）
    {
        Settings settings("wakeword", true);
        std::string saved_pinyins = settings.GetString("pinyins");
        std::string saved_displays = settings.GetString("displays");
        if (!saved_pinyins.empty()) {
            // 格式自愈：旧固件曾把带声调拼音（如 "ni3 hao3 xiao3 he2"，字母后跟
            // 数字 1-5）写入 NVS；MN7 命令表只认 esp-sr 不带调格式（lazy_pinyin），
            // 带调旧词恢复了也永远无法命中。检测到即视为过时缓存：跳过恢复、
            // 删除 NVS 键（同 ClearWakeWordCommands 的删除模式），回落本地默认表；
            // 服务器下次下发唤醒词时会以正确格式重新写入。
            bool legacy_toned = false;
            for (size_t i = 1; i < saved_pinyins.size(); ++i) {
                char prev = saved_pinyins[i - 1];
                char digit = saved_pinyins[i];
                if (prev >= 'a' && prev <= 'z' && digit >= '1' && digit <= '5') {
                    legacy_toned = true;
                    break;
                }
            }
            if (legacy_toned) {
                ESP_LOGW(TAG,
                         "Discarded legacy toned pinyin in NVS ('%.24s...'), "
                         "falling back to default wake words",
                         saved_pinyins.c_str());
                settings.EraseKey("pinyins");
                settings.EraseKey("displays");
            } else {
                std::vector<std::string> pinyins;
                std::vector<std::string> displays;
                std::stringstream ps(saved_pinyins), ds(saved_displays);
                std::string token;
                while (std::getline(ps, token, '|')) {
                    if (!token.empty()) pinyins.push_back(token);
                }
                while (std::getline(ds, token, '|')) {
                    displays.push_back(token);
                }
                if (!pinyins.empty()) {
                    if (displays.size() < pinyins.size()) {
                        displays.resize(pinyins.size());
                    }
                    commands_.clear();
                    for (size_t i = 0; i < pinyins.size(); ++i) {
                        const std::string& display =
                            displays[i].empty() ? pinyins[i] : displays[i];
                        commands_.push_back({pinyins[i], display, "wake"});
                    }
                    ESP_LOGI(TAG, "Restored %zu server wake-word command(s) from NVS",
                             commands_.size());
                }
            }
        }
    }

    esp_mn_commands_clear();
    for (int i = 0; i < commands_.size(); i++) {
        esp_err_t err = esp_mn_commands_add(i + 1, commands_[i].command.c_str());
        if (err != ESP_OK) {
            ESP_LOGE(TAG, "Add command %d failed (err=0x%x): '%s'",
                     i + 1, err, commands_[i].command.c_str());
        }
    }
    esp_mn_error_t *mn_err = esp_mn_commands_update();
    if (mn_err != NULL) {
        // MN7 无法解析的命令（如带声调拼音）会集中在此暴露：带调词被模型
        // 静默拒绝、待机喊不醒，此处打 ERROR 便于定位
        for (int i = 0; i < mn_err->num; ++i) {
            ESP_LOGE(TAG, "Command rejected by multinet (invalid pinyin?): '%s'",
                     mn_err->phrases[i]->string);
        }
    }
    
    multinet_->print_active_speech_commands(multinet_model_data_);
#if CONFIG_SEND_WAKE_WORD_DATA
    if (!wake_word_audio_cache_.Initialize(16000 * 2)) {
        ESP_LOGW(TAG, "Wake-word audio upload disabled: PSRAM cache allocation failed");
    }
#endif
    return true;
}

void CustomWakeWord::OnWakeWordDetected(std::function<void(const std::string& wake_word)> callback) {
    wake_word_detected_callback_ = callback;
}

bool CustomWakeWord::UpdateCommands(const std::vector<std::string>& pinyin_texts, const std::vector<std::string>& display_texts) {
    if (multinet_model_data_ == nullptr) {
        ESP_LOGW(TAG, "UpdateCommands ignored: multinet not initialized");
        return false;
    }
    if (pinyin_texts.empty()) {
        ESP_LOGW(TAG, "UpdateCommands ignored: empty pinyin list");
        return false;
    }
    // 长度对齐：display 可省略（用 pinyin 兜底展示）
    std::vector<Command> new_commands;
    new_commands.reserve(pinyin_texts.size());
    for (size_t i = 0; i < pinyin_texts.size(); ++i) {
        const std::string& pinyin = pinyin_texts[i];
        if (pinyin.empty()) {
            continue;
        }
        std::string display = i < display_texts.size() && !display_texts[i].empty()
                                  ? display_texts[i] : pinyin;
        new_commands.push_back({pinyin, display, "wake"});
    }
    if (new_commands.empty()) {
        ESP_LOGW(TAG, "UpdateCommands ignored: no valid pinyin entries");
        return false;
    }

    {
        // 与 Feed() 互斥：命令表替换与检测循环不会交错执行
        std::lock_guard<std::mutex> lock(input_buffer_mutex_);
        // 比对当前命令表，完全一致则跳过（避免无谓的模型重建）。
        // 必须同时比 command 和 text：服务端拼音化后常见"拼音不变、只改展示文案"
        // （例如把"你好小禾"改成"你好小柚子"但拼音恰好相同），只比 command
        // 会把这种更新静默吞掉，导致唤醒后上报的还是旧词。
        bool same = new_commands.size() == commands_.size();
        if (same) {
            for (size_t i = 0; i < new_commands.size(); ++i) {
                if (new_commands[i].command != commands_[i].command ||
                    new_commands[i].text != commands_[i].text) {
                    same = false;
                    break;
                }
            }
        }
        if (same) {
            return false;
        }
        commands_ = {new_commands.begin(), new_commands.end()};
        // MultiNet 命令表重建（esp_mn_commands_* 全局接口，需先 clear 再逐条 add + update）
        esp_mn_commands_clear();
        for (size_t i = 0; i < commands_.size(); ++i) {
            esp_err_t err = esp_mn_commands_add(static_cast<int>(i) + 1, commands_[i].command.c_str());
            if (err != ESP_OK) {
                ESP_LOGE(TAG, "Add command %zu failed (err=0x%x): '%s'",
                         i + 1, err, commands_[i].command.c_str());
            }
        }
        esp_mn_error_t *mn_err = esp_mn_commands_update();
        if (mn_err != NULL) {
            // MN7 无法解析的命令（如带声调拼音）会集中在此暴露：带调词被模型
            // 静默拒绝、待机喊不醒，此处打 ERROR 便于定位
            for (int i = 0; i < mn_err->num; ++i) {
                ESP_LOGE(TAG, "Command rejected by multinet (invalid pinyin?): '%s'",
                         mn_err->phrases[i]->string);
            }
        }
        // 持久化到 NVS：重启后脱机也能用云端下发的唤醒词
        {
            std::string pinyins, displays;
            for (size_t i = 0; i < commands_.size(); ++i) {
                if (i > 0) { pinyins += "|"; displays += "|"; }
                pinyins += commands_[i].command;
                displays += commands_[i].text;
            }
            Settings settings("wakeword", true);
            settings.SetString("pinyins", pinyins);
            settings.SetString("displays", displays);
        }
    }
    multinet_->print_active_speech_commands(multinet_model_data_);
    ESP_LOGI(TAG, "Wake word commands updated from server: %zu entr%s",
             commands_.size(), commands_.size() == 1 ? "y" : "ies");
    return true;
}

bool CustomWakeWord::ClearWakeWordCommands() {
    if (multinet_model_data_ == nullptr) {
        ESP_LOGW(TAG, "ClearWakeWordCommands ignored: multinet not initialized");
        return false;
    }
    if (default_commands_.empty()) {
        // 默认表缺失（assets 未解析且 Kconfig 未配置）时无从恢复，拒绝清空
        ESP_LOGW(TAG, "ClearWakeWordCommands ignored: no default commands to restore");
        return false;
    }

    {
        // 与 Feed()/UpdateCommands() 互斥：命令表替换与检测循环不会交错执行
        std::lock_guard<std::mutex> lock(input_buffer_mutex_);
        // 已是默认表则仅清理 NVS 缓存（避免无谓的模型重建）。
        // 同 UpdateCommands：必须同时比 command 和 text，否则"拼音相同、文案不同"
        // 的云端表会被误判成默认表，清空后展示文案错误
        bool already_default = default_commands_.size() == commands_.size();
        if (already_default) {
            for (size_t i = 0; i < default_commands_.size(); ++i) {
                if (default_commands_[i].command != commands_[i].command ||
                    default_commands_[i].text != commands_[i].text) {
                    already_default = false;
                    break;
                }
            }
        }
        if (!already_default) {
            // 恢复默认命令表并重建 MultiNet 命令表（同 UpdateCommands 模式）
            commands_ = default_commands_;
            esp_mn_commands_clear();
            for (size_t i = 0; i < commands_.size(); ++i) {
                esp_err_t err = esp_mn_commands_add(static_cast<int>(i) + 1, commands_[i].command.c_str());
                if (err != ESP_OK) {
                    ESP_LOGE(TAG, "Add command %zu failed (err=0x%x): '%s'",
                             i + 1, err, commands_[i].command.c_str());
                }
            }
            esp_mn_error_t *mn_err = esp_mn_commands_update();
            if (mn_err != NULL) {
                // MN7 无法解析的命令（如带声调拼音）会集中在此暴露：带调词被模型
                // 静默拒绝、待机喊不醒，此处打 ERROR 便于定位
                for (int i = 0; i < mn_err->num; ++i) {
                    ESP_LOGE(TAG, "Command rejected by multinet (invalid pinyin?): '%s'",
                             mn_err->phrases[i]->string);
                }
            }
        }
        // 删除 NVS 缓存：重启后不再用云端下发的唤醒词覆盖默认表
        Settings settings("wakeword", true);
        settings.EraseKey("pinyins");
        settings.EraseKey("displays");
    }
    multinet_->print_active_speech_commands(multinet_model_data_);
    ESP_LOGI(TAG, "Wake word commands cleared, restored %zu default command(s)",
             commands_.size());
    return true;
}

void CustomWakeWord::SetThreshold(float threshold) {
    if (threshold < 0.0f || threshold > 1.0f) {
        ESP_LOGW(TAG, "Invalid threshold value: %.2f (range 0.0-1.0)", threshold);
        return;
    }
    // 云端语义：0=最灵敏、100=最不灵敏（下发值 t/100）。esp-sr 可用的最低有效
    // 阈值为 0.01，故 0 夹取到 0.01（最灵敏端点），其余值原样生效
    threshold_ = threshold < 0.01f ? 0.01f : threshold;
    if (multinet_model_data_) {
        multinet_->set_det_threshold(multinet_model_data_, threshold_);
        ESP_LOGI(TAG, "Wake word threshold updated: %.2f", threshold);
    } else {
        ESP_LOGI(TAG, "Wake word threshold cached: %.2f (will apply on init)", threshold);
    }
}

void CustomWakeWord::SetDuration(int duration) {
    if (duration < 500 || duration > 5000) {
        ESP_LOGW(TAG, "Invalid duration value: %d (range 500-5000)", duration);
        return;
    }
    if (multinet_model_data_) {
        multinet_->destroy(multinet_model_data_);
        multinet_model_data_ = nullptr;
    }
    duration_ = duration;
    if (multinet_model_data_ == nullptr && multinet_ != nullptr) {
        multinet_model_data_ = multinet_->create(mn_name_, duration_);
        if (multinet_model_data_) {
            multinet_->set_det_threshold(multinet_model_data_, threshold_);
            ESP_LOGI(TAG, "Wake word duration updated: %dms, model rebuilt", duration);
        } else {
            ESP_LOGE(TAG, "Failed to rebuild multinet model with duration %d", duration);
        }
    } else {
        ESP_LOGI(TAG, "Wake word duration cached: %dms (will apply on init)", duration);
    }
}

std::vector<std::string> CustomWakeWord::GetCommandTexts() const {
    std::lock_guard<std::mutex> lock(input_buffer_mutex_);
    std::vector<std::string> texts;
    texts.reserve(commands_.size());
    for (const auto& c : commands_) {
        texts.push_back(c.text);
    }
    return texts;
}

void CustomWakeWord::Start() {
    running_ = true;
}

void CustomWakeWord::Stop() {
    running_ = false;

    std::lock_guard<std::mutex> lock(input_buffer_mutex_);
    input_buffer_.clear();
}

void CustomWakeWord::Feed(const std::vector<int16_t>& data) {
    FeedSamples(data.data(), data.size(), false);
}

void CustomWakeWord::FeedMono(const int16_t* data, size_t samples) {
    FeedSamples(data, samples, true);
}

void CustomWakeWord::FeedSamples(const int16_t* data, size_t samples, bool mono) {
    if (multinet_model_data_ == nullptr || data == nullptr || samples == 0) {
        return;
    }

    std::lock_guard<std::mutex> lock(input_buffer_mutex_);
    // Check running state inside lock to avoid TOCTOU race with Stop()
    if (!running_) {
        return;
    }

    // If input channels is 2, we need to fetch the left channel data
    if (!mono && codec_->input_channels() > 1) {
        for (size_t i = 0; i < samples; i += codec_->input_channels()) {
            input_buffer_.push_back(data[i]);
        }
    } else {
        input_buffer_.insert(input_buffer_.end(), data, data + samples);
    }
    
    int chunksize = multinet_->get_samp_chunksize(multinet_model_data_);
    while (input_buffer_.size() >= chunksize) {
#if CONFIG_SEND_WAKE_WORD_DATA
        wake_word_audio_cache_.Store(input_buffer_.data(), chunksize);
#endif

        esp_mn_state_t mn_state = multinet_->detect(multinet_model_data_, input_buffer_.data());
        
        if (mn_state == ESP_MN_STATE_DETECTED) {
            esp_mn_results_t *mn_result = multinet_->get_results(multinet_model_data_);
            for (int i = 0; i < mn_result->num && running_; i++) {
                ESP_LOGI(TAG, "Custom wake word detected: command_id=%d, string=%s, prob=%f", 
                        mn_result->command_id[i], mn_result->string, mn_result->prob[i]);
                auto& command = commands_[mn_result->command_id[i] - 1];
                if (command.action == "wake") {
                    last_detected_wake_word_ = command.text;
                    running_ = false;
                    input_buffer_.clear();
                    
                    if (wake_word_detected_callback_) {
                        wake_word_detected_callback_(last_detected_wake_word_);
                    }
                }
            }
            multinet_->clean(multinet_model_data_);
        } else if (mn_state == ESP_MN_STATE_TIMEOUT) {
            ESP_LOGD(TAG, "Command word detection timeout, cleaning state");
            multinet_->clean(multinet_model_data_);
        }
        
        if (!running_) {
            break;
        }
        input_buffer_.erase(input_buffer_.begin(), input_buffer_.begin() + chunksize);
    }
}

size_t CustomWakeWord::GetFeedSize() {
    if (multinet_model_data_ == nullptr) {
        return 0;
    }
    return multinet_->get_samp_chunksize(multinet_model_data_);
}

void CustomWakeWord::EncodeWakeWordData() {
    const size_t stack_size = 4096 * 7;
    wake_word_opus_.clear();
    if (wake_word_encode_task_stack_ == nullptr) {
        wake_word_encode_task_stack_ = (StackType_t*)heap_caps_malloc(stack_size, MALLOC_CAP_SPIRAM);
        assert(wake_word_encode_task_stack_ != nullptr);
    }
    if (wake_word_encode_task_buffer_ == nullptr) {
        wake_word_encode_task_buffer_ = (StaticTask_t*)heap_caps_malloc(sizeof(StaticTask_t), MALLOC_CAP_INTERNAL);
        assert(wake_word_encode_task_buffer_ != nullptr);
    }

    wake_word_encode_task_ = xTaskCreateStatic([](void* arg) {
        auto this_ = (CustomWakeWord*)arg;
        {
            auto start_time = esp_timer_get_time();
            // Create encoder
            esp_opus_enc_config_t opus_enc_cfg = AS_OPUS_ENC_CONFIG();
            void* encoder_handle = nullptr;
            auto ret = esp_opus_enc_open(&opus_enc_cfg, sizeof(esp_opus_enc_config_t), &encoder_handle);
            if (encoder_handle == nullptr) {
                ESP_LOGE(TAG, "Failed to create audio encoder, error code: %d", ret);
                this_->wake_word_audio_cache_.Clear();
                std::lock_guard<std::mutex> lock(this_->wake_word_mutex_);
                this_->wake_word_opus_.push_back(std::vector<uint8_t>());
                this_->wake_word_cv_.notify_all();
                vTaskDelete(nullptr);
                return;
            }
            // Get frame size
            int frame_size = 0;
            int outbuf_size = 0;
            esp_opus_enc_get_frame_size(encoder_handle, &frame_size, &outbuf_size);
            frame_size = frame_size / sizeof(int16_t);
            // Encode all PCM data
            int packets = 0;
            std::vector<int16_t> in_buffer(frame_size);
            esp_audio_enc_in_frame_t in = {};
            esp_audio_enc_out_frame_t out = {};
            const size_t cached_samples = this_->wake_word_audio_cache_.Size();
            for (size_t offset = 0;
                 offset + static_cast<size_t>(frame_size) <= cached_samples;
                 offset += frame_size) {
                if (this_->wake_word_audio_cache_.Read(
                        offset, in_buffer.data(), frame_size) != static_cast<size_t>(frame_size)) {
                    break;
                }
                std::vector<uint8_t> opus_buf(outbuf_size);
                in.buffer = reinterpret_cast<uint8_t*>(in_buffer.data());
                in.len = frame_size * sizeof(int16_t);
                out.buffer = opus_buf.data();
                out.len = outbuf_size;
                out.encoded_bytes = 0;
                ret = esp_opus_enc_process(encoder_handle, &in, &out);
                if (ret == ESP_AUDIO_ERR_OK) {
                    std::lock_guard<std::mutex> lock(this_->wake_word_mutex_);
                    this_->wake_word_opus_.emplace_back(opus_buf.data(), opus_buf.data() + out.encoded_bytes);
                    this_->wake_word_cv_.notify_all();
                    packets++;
                } else {
                    ESP_LOGE(TAG, "Failed to encode audio, error code: %d", ret);
                }
            }
            this_->wake_word_audio_cache_.Clear();
            // Close encoder
            esp_opus_enc_close(encoder_handle);
            auto end_time = esp_timer_get_time();
            ESP_LOGI(TAG, "Encode wake word opus %d packets in %ld ms", packets, (long)((end_time - start_time) / 1000));

            std::lock_guard<std::mutex> lock(this_->wake_word_mutex_);
            this_->wake_word_opus_.push_back(std::vector<uint8_t>());
            this_->wake_word_cv_.notify_all();
        }
        vTaskDelete(NULL);
    }, "encode_wake_word", stack_size, this, 2, wake_word_encode_task_stack_, wake_word_encode_task_buffer_);
}

bool CustomWakeWord::GetWakeWordOpus(std::vector<uint8_t>& opus) {
    std::unique_lock<std::mutex> lock(wake_word_mutex_);
    wake_word_cv_.wait(lock, [this]() {
        return !wake_word_opus_.empty();
    });
    opus.swap(wake_word_opus_.front());
    wake_word_opus_.pop_front();
    return !opus.empty();
}

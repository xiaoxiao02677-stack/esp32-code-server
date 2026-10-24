#include "application.h"
#include "assets.h"
#include "assets/lang_config.h"
#include "audio_codec.h"
#include "board.h"
#include "cjson_utils.h"
#include "display.h"
#include "mcp_server.h"
#include "mqtt_protocol.h"
#include "settings.h"
#include "system_info.h"
#include "text_glyph_payload.h"
#include "wallpaper/wallpaper_manager.h"
#include "websocket_protocol.h"

#ifdef CONFIG_YH_PROTOCOL_ENABLED
#include "yh_protocol.h"
#endif

#include <driver/gpio.h>
#include <esp_log.h>
#include <arpa/inet.h>
#include <cmath>
#include <cJSON.h>
#include <cstring>
#include <limits>

#define TAG "Application"

namespace {

// 壁纸字段解析：WS 的 {"type":"wallpaper",...} 与 device_config.payload.wallpaper 同构
WallpaperRequest ParseWallpaperRequest(const cJSON* object, bool from_config) {
    WallpaperRequest request;
    request.from_config = from_config;
    if (object == nullptr) {
        return request;
    }
    auto version = cJSON_GetObjectItem(object, "version");
    if (cJSON_IsString(version)) {
        request.version = version->valuestring;
    }
    auto url = cJSON_GetObjectItem(object, "url");
    if (cJSON_IsString(url)) {
        request.url = url->valuestring;
    }
    auto md5 = cJSON_GetObjectItem(object, "md5");
    if (cJSON_IsString(md5)) {
        request.md5 = md5->valuestring;
    }
    auto format = cJSON_GetObjectItem(object, "format");
    if (cJSON_IsString(format)) {
        request.format = format->valuestring;
    }
    auto size = cJSON_GetObjectItem(object, "size");
    if (cJSON_IsNumber(size)) {
        request.size = static_cast<int>(size->valuedouble);
    }
    auto width = cJSON_GetObjectItem(object, "width");
    if (cJSON_IsNumber(width)) {
        request.width = static_cast<int>(width->valuedouble);
    }
    auto height = cJSON_GetObjectItem(object, "height");
    if (cJSON_IsNumber(height)) {
        request.height = static_cast<int>(height->valuedouble);
    }
    // 槽位（可选）："boot" = 开机壁纸（splash 底图），缺省/"idle" = 待机壁纸。
    // 旧服务端不带此字段 → 恒 Idle，向后兼容。
    auto kind = cJSON_GetObjectItem(object, "kind");
    if (cJSON_IsString(kind)) {
        if (strcmp(kind->valuestring, "boot") == 0) {
            request.kind = WallpaperKind::Boot;
        } else {
            request.kind = WallpaperKind::Idle;
        }
    }
    return request;
}

// 回执里的字符串只允许来自服务端标识（version/reason），仍做最小转义防破坏 JSON
std::string EscapeJson(const std::string& value) {
    std::string out;
    out.reserve(value.size());
    for (char c : value) {
        if (c == '"' || c == '\\') {
            out.push_back('\\');
            out.push_back(c);
        } else if (static_cast<unsigned char>(c) >= 0x20) {
            out.push_back(c);
        }
    }
    return out;
}

}  // namespace

// 人声打断的播放起始保护窗（毫秒）。TTS 刚开始播放时 AEC 还没有收敛，codec 起停
// 也会产生瞬态，此时设备自己的声音会被 VAD 判成用户说话，导致播报被自己掐断
// （表现为播到一半一声提示音后中断）。这段时间内的 VAD 抬升一律忽略。
// 可通过 CONFIG_YH_INTERRUPT_GUARD_MS 调整（见 Kconfig "YH Voice Interrupt Tuning"）。
static constexpr int kSpeakingInterruptGuardMs = CONFIG_YH_INTERRUPT_GUARD_MS;

Application::Application() : notify_player_(audio_service_) {
    event_group_ = xEventGroupCreate();

#if CONFIG_USE_DEVICE_AEC && CONFIG_USE_SERVER_AEC
#error "CONFIG_USE_DEVICE_AEC and CONFIG_USE_SERVER_AEC cannot be enabled at the same time"
#elif CONFIG_USE_DEVICE_AEC
    aec_mode_ = kAecOnDeviceSide;
#elif CONFIG_USE_SERVER_AEC
    aec_mode_ = kAecOnServerSide;
#else
    aec_mode_ = kAecOff;
#endif

    esp_timer_create_args_t clock_timer_args = {.callback =
                                                    [](void* arg) {
                                                        Application* app = (Application*)arg;
                                                        xEventGroupSetBits(app->event_group_,
                                                                           MAIN_EVENT_CLOCK_TICK);
                                                    },
                                                .arg = this,
                                                .dispatch_method = ESP_TIMER_TASK,
                                                .name = "clock_timer",
                                                .skip_unhandled_events = true};
    esp_timer_create(&clock_timer_args, &clock_timer_handle_);

    // 超时保护：若设备未收到 device_config，30秒后强制显示待机文案
    esp_timer_create_args_t config_synced_timer_args = {
        .callback =
            [](void* arg) {
                Application* app = (Application*)arg;
                app->Schedule([app]() {
                    if (app->GetDeviceState() == kDeviceStateIdle &&
                        app->cloud_config_synced_) {
                        auto display = Board::GetInstance().GetDisplay();
                        display->SetStatus(Lang::Strings::STANDBY);
                    }
                    // 超时处理：无论是否收到device_config，都结束"配置同步中"状态
                    if (app->GetDeviceState() == kDeviceStateIdle &&
                        !app->last_error_message_.empty()) {
                        auto display = Board::GetInstance().GetDisplay();
                        display->SetStatus(Lang::Strings::STANDBY);
                    }
                });
            },
        .arg = this,
        .dispatch_method = ESP_TIMER_TASK,
        .name = "config_synced",
        .skip_unhandled_events = true};
    esp_timer_create(&config_synced_timer_args, &config_synced_timer_handle_);
}

Application::~Application() {
    notify_player_.Stop();
    if (clock_timer_handle_ != nullptr) {
        esp_timer_stop(clock_timer_handle_);
        esp_timer_delete(clock_timer_handle_);
    }
    if (config_synced_timer_handle_ != nullptr) {
        esp_timer_stop(config_synced_timer_handle_);
        esp_timer_delete(config_synced_timer_handle_);
    }
    if (notify_timer_handle_ != nullptr) {
        esp_timer_stop(notify_timer_handle_);
        esp_timer_delete(notify_timer_handle_);
    }
    vEventGroupDelete(event_group_);
}

bool Application::SetDeviceState(DeviceState state) { return state_machine_.TransitionTo(state); }

void Application::Initialize() {
    auto& board = Board::GetInstance();
    SetDeviceState(kDeviceStateStarting);

    // Setup the display
    auto display = board.GetDisplay();
    display->SetupUI();
    // Print board name/version info
    display->SetChatMessage("system", SystemInfo::GetUserAgent().c_str());

    // Setup the audio service
    auto codec = board.GetAudioCodec();
    audio_service_.Initialize(codec);
    audio_service_.Start();
    ESP_LOGI(TAG, "After board/audio init");
    SystemInfo::PrintHeapStats();

    // 开机提示音
    PlaySound(Lang::Sounds::OGG_SUCCESS);

    AudioServiceCallbacks callbacks;
    callbacks.on_send_queue_available = [this]() {
        xEventGroupSetBits(event_group_, MAIN_EVENT_SEND_AUDIO);
    };
    callbacks.on_wake_word_detected = [this](const std::string& wake_word) {
        xEventGroupSetBits(event_group_, MAIN_EVENT_WAKE_WORD_DETECTED);
    };
    callbacks.on_vad_change = [this](bool speaking) {
        xEventGroupSetBits(event_group_, MAIN_EVENT_VAD_CHANGE);
    };
    callbacks.on_playback_drained = [this]() {
        xEventGroupSetBits(event_group_, MAIN_EVENT_PLAYBACK_DRAINED);
    };
    callbacks.on_playback_progress = [this](uint32_t playback_id, uint32_t media_position_ms) {
        notify_player_.OnPlaybackProgress(playback_id, media_position_ms);
    };
    audio_service_.SetCallbacks(callbacks);

    // Add state change listeners
    state_machine_.AddStateChangeListener([this](DeviceState old_state, DeviceState new_state) {
        xEventGroupSetBits(event_group_, MAIN_EVENT_STATE_CHANGED);
    });

    // Start the clock timer to update the status bar
    esp_timer_start_periodic(clock_timer_handle_, 1000000);

    // Add MCP common tools (only once during initialization)
    auto& mcp_server = McpServer::GetInstance();
    mcp_server.AddCommonTools();
    mcp_server.AddUserOnlyTools();

    // Set network event callback for UI updates and network state handling
    board.SetNetworkEventCallback([this](NetworkEvent event, const std::string& data) {
        auto display = Board::GetInstance().GetDisplay();

        switch (event) {
            case NetworkEvent::Scanning:
                display->ShowNotification(Lang::Strings::SCANNING_WIFI, 30000);
                xEventGroupSetBits(event_group_, MAIN_EVENT_NETWORK_DISCONNECTED);
                break;
            case NetworkEvent::Connecting: {
                if (data.empty()) {
                    // Cellular network - registering without carrier info yet
                    display->SetStatus(Lang::Strings::REGISTERING_NETWORK);
                } else {
                    // WiFi or cellular with carrier info
                    std::string msg = Lang::Strings::CONNECT_TO;
                    msg += data;
                    msg += "...";
                    display->ShowNotification(msg.c_str(), 30000);
                }
                break;
            }
            case NetworkEvent::Connected: {
                std::string msg = Lang::Strings::CONNECTED_TO;
                msg += data;
                display->ShowNotification(msg.c_str(), 30000);
                xEventGroupSetBits(event_group_, MAIN_EVENT_NETWORK_CONNECTED);
#ifdef CONFIG_YH_PROTOCOL_ENABLED
                // 网络就绪后启动 YH 旁路通道（幂等；重连定时器在 YhProtocol 内部管理）
                YhProtocol::GetInstance().Start();
#endif
                break;
            }
            case NetworkEvent::Disconnected:
                xEventGroupSetBits(event_group_, MAIN_EVENT_NETWORK_DISCONNECTED);
#ifdef CONFIG_YH_PROTOCOL_ENABLED
                // 断网时停下 YH 重连定时器；网络恢复后由 Connected 事件重启
                YhProtocol::GetInstance().Stop();
#endif
                break;
            case NetworkEvent::WifiConfigModeEnter:
                // WiFi config mode enter is handled by WifiBoard internally
                break;
            case NetworkEvent::WifiConfigModeExit:
                // WiFi config mode exit is handled by WifiBoard internally
                break;
            // Cellular modem specific events
            case NetworkEvent::ModemDetecting:
                display->SetStatus(Lang::Strings::DETECTING_MODULE);
                break;
            case NetworkEvent::ModemErrorNoSim:
                Alert(Lang::Strings::ERROR, Lang::Strings::PIN_ERROR, "warning",
                      Lang::Sounds::OGG_ERR_PIN);
                break;
            case NetworkEvent::ModemErrorRegDenied:
                Alert(Lang::Strings::ERROR, Lang::Strings::REG_ERROR, "warning",
                      Lang::Sounds::OGG_ERR_REG);
                break;
            case NetworkEvent::ModemErrorInitFailed:
                Alert(Lang::Strings::ERROR, Lang::Strings::MODEM_INIT_ERROR, "warning",
                      Lang::Sounds::OGG_EXCLAMATION);
                break;
            case NetworkEvent::ModemErrorTimeout:
                display->SetStatus(Lang::Strings::REGISTERING_NETWORK);
                break;
        }
    });

    // Start network asynchronously
    board.StartNetwork();

    // Update the status bar immediately to show the network state
    display->UpdateStatusBar(true);
}

void Application::Run() {
    // Set the priority of the main task to 10
    vTaskPrioritySet(nullptr, 10);

    const EventBits_t ALL_EVENTS =
        MAIN_EVENT_SCHEDULE | MAIN_EVENT_SEND_AUDIO | MAIN_EVENT_WAKE_WORD_DETECTED |
        MAIN_EVENT_VAD_CHANGE | MAIN_EVENT_CLOCK_TICK | MAIN_EVENT_ERROR |
        MAIN_EVENT_NETWORK_CONNECTED | MAIN_EVENT_NETWORK_DISCONNECTED | MAIN_EVENT_TOGGLE_CHAT |
        MAIN_EVENT_START_LISTENING | MAIN_EVENT_STOP_LISTENING | MAIN_EVENT_ACTIVATION_DONE |
        MAIN_EVENT_STATE_CHANGED | MAIN_EVENT_PLAYBACK_DRAINED;

    while (true) {
        auto bits = xEventGroupWaitBits(event_group_, ALL_EVENTS, pdTRUE, pdFALSE, portMAX_DELAY);

        if (bits & MAIN_EVENT_ERROR) {
            if (GetDeviceState() == kDeviceStateNotifying) {
                StopNotification();
            }
            SetDeviceState(kDeviceStateIdle);
            // 兜底：网络错误不再弹阻塞式 Alert（cancel 图标 + 警告音），
            // 自动重连由 OnNetworkError 里的 StartAutoReconnect 负责。
            // 状态只显示在气泡/状态行，不打断用户。
            if (!last_error_message_.empty()) {
                auto display = Board::GetInstance().GetDisplay();
                display->SetStatus(Lang::Strings::ERROR);
                display->SetChatMessage("system", last_error_message_.c_str());
            }
        }

        if (bits & MAIN_EVENT_NETWORK_CONNECTED) {
            HandleNetworkConnectedEvent();
        }

        if (bits & MAIN_EVENT_NETWORK_DISCONNECTED) {
            HandleNetworkDisconnectedEvent();
        }

        if (bits & MAIN_EVENT_ACTIVATION_DONE) {
            HandleActivationDoneEvent();
        }

        if (bits & MAIN_EVENT_STATE_CHANGED) {
            HandleStateChangedEvent();
        }

        if (bits & MAIN_EVENT_PLAYBACK_DRAINED) {
            if (audio_service_.IsPlaybackIdle()) {
                ESP_LOGI(TAG, "Playback drained");
                notify_player_.OnPlaybackDrained();
            }
            // TTS stop 挂起收割：音频已真正放完，现在才切 Listening
            // （tts stop 到达时队列未排空被挂起，见 stop 分支注释）
            if (pending_tts_stop_ && GetDeviceState() == kDeviceStateSpeaking &&
                audio_service_.IsPlaybackIdle()) {
                pending_tts_stop_ = false;
                if (listening_mode_ == kListeningModeManualStop) {
                    SetDeviceState(kDeviceStateIdle);
                } else {
                    SetDeviceState(kDeviceStateListening);
                }
            }
            // Deferred listening start (auto mode): the playback queue has
            // drained, so it is now safe to enable voice processing.
            if (pending_listening_start_ && GetDeviceState() == kDeviceStateListening &&
                audio_service_.IsPlaybackIdle()) {
                pending_listening_start_ = false;
                StartListeningAudio();
            }
        }

        if (bits & MAIN_EVENT_TOGGLE_CHAT) {
            HandleToggleChatEvent();
        }

        if (bits & MAIN_EVENT_START_LISTENING) {
            HandleStartListeningEvent();
        }

        if (bits & MAIN_EVENT_STOP_LISTENING) {
            HandleStopListeningEvent();
        }

        if (bits & MAIN_EVENT_SEND_AUDIO) {
            while (auto packet = audio_service_.PopPacketFromSendQueue()) {
                if (protocol_ && !protocol_->SendAudio(std::move(packet))) {
                    ESP_LOGE(TAG, "SendAudio failed, dropping queued audio frames");
                    // Drop the remaining packets. Leaving them in the queue would
                    // stall the Opus codec task (it waits for queue space), which in
                    // turn deadlocks the whole audio input pipeline, as no new
                    // MAIN_EVENT_SEND_AUDIO event would ever be triggered again.
                    while (audio_service_.PopPacketFromSendQueue())
                        ;
                    break;
                }
            }
        }

        if (bits & MAIN_EVENT_WAKE_WORD_DETECTED) {
            HandleWakeWordDetectedEvent();
        }

        if (bits & MAIN_EVENT_VAD_CHANGE) {
            if (GetDeviceState() == kDeviceStateListening) {
                auto led = Board::GetInstance().GetLed();
                led->OnStateChanged();
            } else if (GetDeviceState() == kDeviceStateSpeaking) {
#if !CONFIG_YH_REALTIME_INTERRUPT
                // 实时打断总开关（YH_REALTIME_INTERRUPT，默认 n）：播报中
                // 彻底不做设备侧打断，播报完整播完。为 Realtime API 接入
                // 预留——届时由服务端统一做打断决策，设备侧保持静默。
                ESP_LOGD(TAG, "Ignore VAD change: realtime interrupt disabled");
#else
                if (aec_mode_ != kAecOnDeviceSide) {
                    // 服务端 AEC / 关闭态：打断判断交给服务器（receiveAudioHandle 的
                    // client_aec 分支），本地 VAD 事件只用于状态展示，不做打断决策
                    // ——单工板开着本地 VAD 必然被自己的播报声触发。
                } else if (!IsVoiceDetected()) {
                    // VAD 是双向上报的：语音结束（下降沿）同样会置 MAIN_EVENT_VAD_CHANGE。
                    // 只有真正"检测到人声"才允许打断，否则用户一说完话就会把自己
                    // 的播报掐掉 —— 这是误打断的一个主要来源。
                    ESP_LOGD(TAG, "Ignore VAD change: falling edge, no voice detected");
                } else {
                    // 播放起始保护窗：这段时间内 AEC 未收敛 / 播放起停瞬态的残留回声
                    // 极易被 VAD 误判成人声，忽略打断，避免 TTS 被自己掐断。
                    const int32_t playback_ms = audio_service_.GetPlaybackElapsedMs();
                    if (playback_ms < 0 || playback_ms < kSpeakingInterruptGuardMs) {
                        ESP_LOGW(TAG, "Ignore voice interrupt in playback guard window (%d ms)",
                                 playback_ms);
                    } else {
                        // 人声打断：用户说话时中断当前 TTS 播报
                        ESP_LOGI(TAG, "Voice interrupt after %d ms of playback", playback_ms);
                        AbortSpeaking(kAbortReasonNone);  // 协议层暂无独立枚举，此处用 None 表示语音打断
                        // 清空发送队列，防止残留数据被发送到服务器
                        while (audio_service_.PopPacketFromSendQueue())
                            ;
                        SetDeviceState(kDeviceStateListening);
                        protocol_->SendStartListening(GetDefaultListeningMode());
                        audio_service_.ResetDecoder();
                        // 打断不再播放提示音（原 OGG_POPUP"滴"声）：静默打断，
                        // 反馈交给屏幕状态与 LED，避免播报被掐断后又补一声噪声。
                    }
                }
#endif
            }
        }

        if (bits & MAIN_EVENT_SCHEDULE) {
            std::unique_lock<std::mutex> lock(mutex_);
            auto tasks = std::move(main_tasks_);
            lock.unlock();
            for (auto& task : tasks) {
                task();
            }
        }

        if (bits & MAIN_EVENT_CLOCK_TICK) {
            clock_ticks_++;
            auto display = Board::GetInstance().GetDisplay();
            display->UpdateStatusBar();

            // TTS stop 挂起兜底：正常情况下缓冲音频数百毫秒内放完即触发
            // PLAYBACK_DRAINED 收割；若 drained 事件因音频任务异常永远不来，
            // 设备会卡死在 Speaking——3 秒后强制按 stop 语义切状态。
            if (pending_tts_stop_ && GetDeviceState() == kDeviceStateSpeaking) {
                if (audio_service_.IsPlaybackIdle()) {
                    // 队列已空但 drained 事件丢失（错过窗口）：直接收割
                    pending_tts_stop_ = false;
                    if (listening_mode_ == kListeningModeManualStop) {
                        SetDeviceState(kDeviceStateIdle);
                    } else {
                        SetDeviceState(kDeviceStateListening);
                    }
                } else if (clock_ticks_ - tts_stop_tick_ >= 3) {
                    ESP_LOGW(TAG, "TTS stop deferred too long, forcing state change");
                    audio_service_.ResetDecoder();  // 清掉卡住的队列（会触发 drained）
                }
            }

            // Print debug info every 10 seconds
            if (clock_ticks_ % 10 == 0) {
                SystemInfo::PrintHeapStats();
                // SystemInfo::PrintTaskList();
                // SystemInfo::PrintTaskCpuUsage(pdMS_TO_TICKS(1000));
            }
        }
    }
}

void Application::HandleNetworkConnectedEvent() {
    ESP_LOGI(TAG, "Network connected");
    // 壁纸持久化恢复（FR-2.16）：异步重拉，失败静默，不影响启动/连接流程。
    WallpaperManager::GetInstance().RestoreFromNvsAsync();
    auto state = GetDeviceState();

    if (state == kDeviceStateStarting || state == kDeviceStateWifiConfiguring) {
        // Network is ready, start activation
        SetDeviceState(kDeviceStateActivating);
        if (activation_task_handle_ != nullptr) {
            ESP_LOGW(TAG, "Activation task already running");
            return;
        }

        xTaskCreate(
            [](void* arg) {
                Application* app = static_cast<Application*>(arg);
                app->ActivationTask();
                app->activation_task_handle_ = nullptr;
                vTaskDelete(NULL);
            },
            "activation", 4096 * 2, this, 2, &activation_task_handle_);
    }

    // Update the status bar immediately to show the network state
    auto display = Board::GetInstance().GetDisplay();
    display->UpdateStatusBar(true);
}

void Application::HandleNetworkDisconnectedEvent() {
    // Close current conversation when network disconnected
    auto state = GetDeviceState();
    if (state == kDeviceStateNotifying) {
        StopNotification();
    }
    // 关闭音频通道（protocol_ 可能为 nullptr，在激活阶段之前触发网络断开事件时）
    if (protocol_) {
        ESP_LOGI(TAG, "Closing audio channel due to network disconnection");
        protocol_->CloseAudioChannel();
    }

    // Update the status bar immediately to show the network state
    auto display = Board::GetInstance().GetDisplay();
    display->UpdateStatusBar(true);
}

void Application::HandleActivationDoneEvent() {
    ESP_LOGI(TAG, "Activation done");

    SystemInfo::PrintHeapStats();
    SetDeviceState(kDeviceStateIdle);

    has_server_time_ = ota_->HasServerTime();

    // Protocol start may have already raised MAIN_EVENT_ERROR. Do not replace
    // that alert with the "ready" UI/sound — the main loop can process both
    // events back-to-back because the activation task is lower priority.
    const bool has_error = !last_error_message_.empty();
    if (!has_error) {
        auto display = Board::GetInstance().GetDisplay();
        std::string message = std::string(Lang::Strings::VERSION) + ota_->GetCurrentVersion();
        display->ShowNotification(message.c_str());
        display->SetChatMessage("system", "");
    }

    // Release OTA object after activation is complete
    ota_.reset();
    auto& board = Board::GetInstance();
    board.SetPowerSaveLevel(PowerSaveLevel::LOW_POWER);

    if (!has_error) {
        Schedule([this]() {
            // Play the success sound to indicate the device is ready
            audio_service_.PlaySound(Lang::Sounds::OGG_SUCCESS);
        });
    }
}

void Application::ActivationTask() {
    // Create OTA object for activation process
    ota_ = std::make_unique<Ota>();

    // 检查配置版本（不阻塞启动，失败也继续）
    auto config_ver = ota_->CheckConfigVersion();
    if (config_ver) {
        std::string server_ver = *config_ver;
        if (!server_ver.empty() && server_ver != ota_->GetLocalConfigVersion()) {
            ESP_LOGI(TAG, "Config version mismatch: server=%s local=%s, will update",
                     server_ver.c_str(), ota_->GetLocalConfigVersion().c_str());
            // 配置版本不同，设置标记供后续使用
            // 实际下载可在协议连接成功后进行
        }
    } else {
        ESP_LOGW(TAG, "Config version check failed: %s", config_ver.error().c_str());
    }

    // Check for new assets version
    CheckAssetsVersion();

    // Check for new firmware version
    CheckNewVersion();

    // Initialize the protocol
    InitializeProtocol();

    // Signal completion to main loop
    xEventGroupSetBits(event_group_, MAIN_EVENT_ACTIVATION_DONE);
}

void Application::CheckAssetsVersion() {
    // Only allow CheckAssetsVersion to be called once
    if (assets_version_checked_) {
        return;
    }
    assets_version_checked_ = true;

    auto& board = Board::GetInstance();
    auto display = board.GetDisplay();
    auto& assets = Assets::GetInstance();

    if (!assets.partition_valid()) {
        ESP_LOGW(TAG, "Assets partition is disabled for board %s", BOARD_NAME);
        return;
    }

    Settings settings("assets", true);
    // Check if there is a new assets need to be downloaded
    std::string download_url = settings.GetString("download_url");

    if (!download_url.empty()) {
        settings.EraseKey("download_url");

        char message[256];
        snprintf(message, sizeof(message), Lang::Strings::FOUND_NEW_ASSETS, download_url.c_str());
        Alert(Lang::Strings::LOADING_ASSETS, message, "cloud_download", Lang::Sounds::OGG_UPGRADE);

        // Wait for the audio service to be idle for 3 seconds
        vTaskDelay(pdMS_TO_TICKS(3000));
        SetDeviceState(kDeviceStateUpgrading);
        board.SetPowerSaveLevel(PowerSaveLevel::PERFORMANCE);
        display->SetChatMessage("system", Lang::Strings::PLEASE_WAIT);

        bool success =
            assets.Download(download_url, [this, display](int progress, size_t speed) -> void {
                char buffer[32];
                snprintf(buffer, sizeof(buffer), "%d%% %uKB/s", progress, speed / 1024);
                Schedule([display, message = std::string(buffer)]() {
                    display->SetChatMessage("system", message.c_str());
                });
            });

        board.SetPowerSaveLevel(PowerSaveLevel::LOW_POWER);
        vTaskDelay(pdMS_TO_TICKS(1000));

        if (!success) {
            Alert(Lang::Strings::ERROR, Lang::Strings::DOWNLOAD_ASSETS_FAILED, "cancel",
                  Lang::Sounds::OGG_EXCLAMATION);
            vTaskDelay(pdMS_TO_TICKS(2000));
            SetDeviceState(kDeviceStateActivating);
            return;
        }
    }

    // Apply assets
    assets.Apply();
    display->SetChatMessage("system", "");
    display->SetEmotion("robot_2");
}

void Application::CheckNewVersion() {
    const int MAX_RETRY = 10;
    int retry_count = 0;
    int retry_delay = 10;  // Initial retry delay in seconds

    auto& board = Board::GetInstance();
    while (true) {
        auto display = board.GetDisplay();
        display->SetStatus(Lang::Strings::CHECKING_NEW_VERSION);

        auto check = ota_->CheckVersion();
        if (!check) {
            retry_count++;
            if (retry_count >= MAX_RETRY) {
                ESP_LOGE(TAG, "Too many retries, exit version check");
                return;
            }

            const auto& err = check.error();
            char error_message[160];
            int error_message_length =
                snprintf(error_message, sizeof(error_message), "%s", err.ToString().c_str());
            if (error_message_length < 0 ||
                error_message_length >= static_cast<int>(sizeof(error_message))) {
                snprintf(error_message, sizeof(error_message), "%s", err.Message());
            }

            char buffer[320];
            int alert_message_length =
                snprintf(buffer, sizeof(buffer), Lang::Strings::CHECK_NEW_VERSION_FAILED,
                         retry_delay, error_message);
            if (alert_message_length < 0 ||
                alert_message_length >= static_cast<int>(sizeof(buffer))) {
                snprintf(buffer, sizeof(buffer), "%s", err.Message());
            }
            Alert(Lang::Strings::ERROR, buffer, "cloud_off", Lang::Sounds::OGG_EXCLAMATION);

            ESP_LOGW(TAG, "Check new version failed, retry in %d seconds (%d/%d)", retry_delay,
                     retry_count, MAX_RETRY);
            for (int i = 0; i < retry_delay; i++) {
                vTaskDelay(pdMS_TO_TICKS(1000));
                if (GetDeviceState() == kDeviceStateIdle) {
                    break;
                }
            }
            retry_delay *= 2;  // Double the retry delay
            continue;
        }
        retry_count = 0;
        retry_delay = 10;  // Reset retry delay

        if (ota_->HasNewVersion()) {
            if (UpgradeFirmware(ota_->GetFirmwareUrl(), ota_->GetFirmwareVersion())) {
                return;  // This line will never be reached after reboot
            }
            // If upgrade failed, continue to normal operation
        }

        // No new version, mark the current version as valid
        ota_->MarkCurrentVersionValid();
        if (!ota_->HasActivationCode() && !ota_->HasActivationChallenge()) {
            // Exit the loop if done checking new version
            break;
        }

        display->SetStatus(Lang::Strings::ACTIVATION);
        // Activation code is shown to the user and waiting for the user to input
        if (ota_->HasActivationCode()) {
            ShowActivationCode(ota_->GetActivationCode(), ota_->GetActivationMessage());
        }

        // This will block the loop until the activation is done or timeout
        for (int i = 0; i < 10; ++i) {
            ESP_LOGI(TAG, "Activating... %d/%d", i + 1, 10);
            esp_err_t err = ota_->Activate();
            if (err == ESP_OK) {
                break;
            } else if (err == ESP_ERR_TIMEOUT) {
                vTaskDelay(pdMS_TO_TICKS(3000));
            } else {
                vTaskDelay(pdMS_TO_TICKS(10000));
            }
            if (GetDeviceState() == kDeviceStateIdle) {
                break;
            }
        }
    }
}

void Application::InitializeProtocol() {
    auto& board = Board::GetInstance();
    auto display = board.GetDisplay();
    auto codec = board.GetAudioCodec();

    display->SetStatus(Lang::Strings::LOADING_PROTOCOL);

    if (ota_->HasMqttConfig()) {
        protocol_ = std::make_unique<MqttProtocol>();
    } else if (ota_->HasWebsocketConfig()) {
        protocol_ = std::make_unique<WebsocketProtocol>();
    } else {
        ESP_LOGW(TAG, "No protocol specified in the OTA config, using MQTT");
        protocol_ = std::make_unique<MqttProtocol>();
    }

    protocol_->OnConnected([this]() {
        DismissAlert();
        StopAutoReconnect();  // 兜底重连成功收手
    });

    protocol_->OnNetworkError([this](const std::string& message) {
        last_error_message_ = message;
        xEventGroupSetBits(event_group_, MAIN_EVENT_ERROR);
        // 兜底：静默自动重连（2026-10-08）。不再依赖用户按键，
        // 连接失败后按指数退避自动重试；成功连上时 StopAutoReconnect。
        StartAutoReconnect();
    });

    protocol_->OnIncomingAudio([this](std::unique_ptr<AudioStreamPacket> packet) {
        if (GetDeviceState() == kDeviceStateSpeaking) {
            if (!audio_service_.PushPacketToDecodeQueue(std::move(packet))) {
                // Last silent drop point on the downlink; a full decode queue
                // (~1.2s buffer) means the opus task is starved or stalled.
                ESP_LOGW(TAG, "Decode queue is full, dropping incoming audio packet");
            }
        }
    });

    protocol_->OnAudioChannelOpened([this, codec, &board]() {
        board.SetPowerSaveLevel(PowerSaveLevel::PERFORMANCE);
        if (protocol_->server_sample_rate() != codec->output_sample_rate()) {
            ESP_LOGW(TAG,
                     "Server sample rate %d does not match device output sample rate %d, "
                     "resampling may cause distortion",
                     protocol_->server_sample_rate(), codec->output_sample_rate());
        }
    });

    protocol_->OnAudioChannelClosed([this, &board]() {
        board.SetPowerSaveLevel(PowerSaveLevel::LOW_POWER);
        Schedule([this]() {
            auto display = Board::GetInstance().GetDisplay();
            display->SetChatMessage("system", "");
            SetDeviceState(kDeviceStateIdle);
        });
    });

    protocol_->OnIncomingJson([this, display](const cJSON* root) {
        // Parse JSON data
        auto type = cJSON_GetObjectItem(root, "type");
        if (!cJSON_IsString(type)) {
            ESP_LOGW(TAG, "Incoming JSON message has no type");
            return;
        }
        if (strcmp(type->valuestring, "notify") == 0) {
            auto audio_url = cJSON_GetObjectItem(root, "audio_url");
            if (!cJSON_IsString(audio_url) || audio_url->valuestring[0] == '\0') {
                ESP_LOGW(TAG, "Notify message requires audio_url");
                return;
            }

            // 解析推送优先级
            auto push_type = cJSON_GetObjectItem(root, "push_type");
            NotifyPriority priority = NotifyPriority::kNotifyPriorityNormal;
            if (cJSON_IsString(push_type)) {
                if (strcmp(push_type->valuestring, "urgent") == 0) {
                    priority = NotifyPriority::kNotifyPriorityUrgent;
                } else if (strcmp(push_type->valuestring, "random") == 0) {
                    priority = NotifyPriority::kNotifyPriorityLow;
                }
            }

            std::vector<NotifySubtitle> subtitles;
            auto subtitles_json = cJSON_GetObjectItem(root, "subtitles");
            if (subtitles_json != nullptr && !cJSON_IsArray(subtitles_json)) {
                ESP_LOGW(TAG, "Notify subtitles must be an array");
                return;
            }
            if (cJSON_IsArray(subtitles_json)) {
                cJSON* item = nullptr;
                cJSON_ArrayForEach (item, subtitles_json) {
                    auto start_ms = cJSON_GetObjectItem(item, "start_ms");
                    auto text = cJSON_GetObjectItem(item, "text");
                    if (!cJSON_IsNumber(start_ms) || start_ms->valuedouble < 0 ||
                        start_ms->valuedouble > std::numeric_limits<uint32_t>::max() ||
                        !cJSON_IsString(text)) {
                        ESP_LOGW(TAG, "Ignoring invalid notify subtitle");
                        continue;
                    }
                    subtitles.push_back({.start_ms = static_cast<uint32_t>(start_ms->valuedouble),
                                         .text = text->valuestring});
                }
            }

            Schedule([this, url = std::string(audio_url->valuestring),
                      subtitles = std::move(subtitles), priority]() mutable {
                StartNotification(std::move(url), std::move(subtitles), priority);
            });
        } else if (strcmp(type->valuestring, "wallpaper") == 0) {
            // 壁纸即时下发（FR-2.11）。下载在 WallpaperManager 的后台任务里执行，
            // 此回调只做参数解析与投递，不阻塞协议接收线程。
            auto action = cJSON_GetObjectItem(root, "action");
            if (!cJSON_IsString(action)) {
                ESP_LOGW(TAG, "Wallpaper message requires action");
                return;
            }
            if (strcmp(action->valuestring, "clear") == 0) {
                // kind 可选：{"kind":"boot"} 清开机壁纸，缺省/“idle" 清待机壁纸
                WallpaperRequest probe = ParseWallpaperRequest(root, false);
                const WallpaperKind clear_kind = probe.kind;
                WallpaperManager::GetInstance().HandleClear(
                    clear_kind, [this, clear_kind](bool ok, const std::string& reason) {
                        Schedule([this, clear_kind, ok, reason]() {
                            SendWallpaperAck("", ok, reason, clear_kind);
                        });
                    });
            } else if (strcmp(action->valuestring, "set") == 0) {
                WallpaperRequest request = ParseWallpaperRequest(root, false);
                const std::string version = request.version;
                const WallpaperKind set_kind = request.kind;
                if (request.url.empty() || request.md5.empty()) {
                    ESP_LOGW(TAG, "Wallpaper set requires url and md5");
                    Schedule([this, version, set_kind]() {
                        SendWallpaperAck(version, false, "bad_format", set_kind);
                    });
                    return;
                }
                WallpaperManager::GetInstance().HandleSet(
                    request, [this, version, set_kind](bool ok, const std::string& reason) {
                        Schedule([this, version, set_kind, ok, reason]() {
                            SendWallpaperAck(version, ok, reason, set_kind);
                        });
                    });
            } else {
                ESP_LOGW(TAG, "Unknown wallpaper action: %s", action->valuestring);
            }
        } else if (strcmp(type->valuestring, "tts") == 0) {
            auto state = cJSON_GetObjectItem(root, "state");
            if (!cJSON_IsString(state)) {
                return;
            }
            if (strcmp(state->valuestring, "start") == 0) {
                tts_start_time_ = std::chrono::steady_clock::now();
                tts_sentence_count_ = 0;
                ESP_LOGI(TAG, "TTS start");
                Schedule([this]() {
                    aborted_ = false;
                    // 新一轮播报开始，上一轮挂起的 stop（若有残留）作废
                    pending_tts_stop_ = false;
                    SetDeviceState(kDeviceStateSpeaking);
                });
            } else if (strcmp(state->valuestring, "stop") == 0) {
                const auto tts_duration_ms = std::chrono::duration_cast<std::chrono::milliseconds>(
                                                 std::chrono::steady_clock::now() - tts_start_time_)
                                                 .count();
                ESP_LOGI(TAG, "TTS session done (sentences=%u, duration=%ld ms)",
                         (unsigned)tts_sentence_count_, (long)tts_duration_ms);
                Schedule([this]() {
                    if (GetDeviceState() == kDeviceStateSpeaking) {
                        if (listening_mode_ == kListeningModeManualStop) {
                            SetDeviceState(kDeviceStateIdle);
                        } else {
                            // 播放队列还有未放完的音频时（服务端在最后一包音频
                            // 发出后立即下发 stop，解码/播放缓冲里通常还压着
                            // 数百毫秒），立即切 Listening 会经 StartListeningAudio
                            // → EnableVoiceProcessing → ResetDecoder 清空播放
                            // 队列，把播报尾巴掐掉（用户听到"还没说完就断了"）。
                            // 挂起等 PLAYBACK_DRAINED（音频真正放完）再切状态；
                            // 队列已空则直接切。
                            if (!audio_service_.IsPlaybackIdle()) {
                                ESP_LOGI(TAG, "TTS stop deferred: waiting for playback to drain");
                                pending_tts_stop_ = true;
                                tts_stop_tick_ = clock_ticks_;
                            } else {
                                SetDeviceState(kDeviceStateListening);
                            }
                        }
                    }
                });
            } else if (strcmp(state->valuestring, "sentence_start") == 0) {
                auto text = cJSON_GetObjectItem(root, "text");
                if (cJSON_IsString(text)) {
                    tts_sentence_count_++;
                    std::vector<TextGlyph> glyphs;
                    uint8_t bpp = 0;
                    if (!TextGlyphPayload::Parse(root, glyphs, bpp)) {
                        glyphs.clear();
                    }
                    ESP_LOGI(TAG, "<< %s", text->valuestring);
                    Schedule([display, message = std::string(text->valuestring),
                              glyphs = std::move(glyphs), bpp]() {
                        display->AddTextGlyphs(glyphs, bpp);
                        display->SetChatMessage("assistant", message.c_str());
                    });
                }
            }
        } else if (strcmp(type->valuestring, "stt") == 0) {
            auto text = cJSON_GetObjectItem(root, "text");
            if (cJSON_IsString(text)) {
                // Internal tool directives from the server (e.g. "% get_weather")
                // must not overwrite the user subtitle; log them instead.
                if (strncmp(text->valuestring, "% ", 2) == 0) {
                    ESP_LOGI(TAG, "Tool call: %s", text->valuestring);
                    return;
                }
                std::vector<TextGlyph> glyphs;
                uint8_t bpp = 0;
                if (!TextGlyphPayload::Parse(root, glyphs, bpp)) {
                    glyphs.clear();
                }
                ESP_LOGI(TAG, ">> %s", text->valuestring);
                Schedule([display, message = std::string(text->valuestring),
                          glyphs = std::move(glyphs), bpp]() {
                    display->AddTextGlyphs(glyphs, bpp);
                    display->SetChatMessage("user", message.c_str());
                });
            }
        } else if (strcmp(type->valuestring, "llm") == 0) {
            auto emotion = cJSON_GetObjectItem(root, "emotion");
            if (cJSON_IsString(emotion)) {
                ESP_LOGD(TAG, "LLM emotion: %s", emotion->valuestring);
                Schedule([display, emotion_str = std::string(emotion->valuestring)]() {
                    display->SetEmotion(emotion_str.c_str());
                });
            }
        } else if (strcmp(type->valuestring, "mcp") == 0) {
            auto payload = cJSON_GetObjectItem(root, "payload");
            if (cJSON_IsObject(payload)) {
                McpServer::GetInstance().ParseMessage(payload);
            }
        } else if (strcmp(type->valuestring, "device_config") == 0) {
            // Cloud-persisted device config pushed by the server on connect.
            // The callback owns `root` only until it returns (both transports
            // cJSON_Delete it afterwards), so serialize the payload and parse
            // it again inside the scheduled closure.
            auto payload = cJSON_GetObjectItem(root, "payload");
            if (cJSON_IsObject(payload)) {
                CJsonStringUniquePtr payload_json(cJSON_PrintUnformatted(payload));
                if (payload_json != nullptr) {
                    ESP_LOGI(TAG, "Received device_config: %s", payload_json.get());
                    Schedule([this, payload_str = std::string(payload_json.get())]() {
                        CJsonUniquePtr payload(cJSON_Parse(payload_str.c_str()));
                        if (payload == nullptr) {
                            ESP_LOGE(TAG, "Failed to parse device_config payload");
                            return;
                        }
                        Board::GetInstance().ApplyDeviceConfig(payload.get());
                        // 壁纸（FR-2.16）：与唤醒词同一条 device_config 路径下发；
                        // 来自云端配置不回执，幂等由 WallpaperManager 保证。
                        auto wallpaper = cJSON_GetObjectItem(payload.get(), "wallpaper");
                        if (cJSON_IsObject(wallpaper)) {
                            WallpaperRequest wallpaper_request =
                                ParseWallpaperRequest(wallpaper, true);
                            if (!wallpaper_request.url.empty() &&
                                !wallpaper_request.md5.empty()) {
                                WallpaperManager::GetInstance().HandleSet(wallpaper_request,
                                                                           nullptr);
                            } else {
                                ESP_LOGW(TAG, "Ignore device_config wallpaper without url/md5");
                            }
                        }
                        // 开机壁纸（boot 槽）：与 wallpaper 同一条 device_config 路径，
                        // 只是键名不同。kind 在这里写死为 Boot，不依赖服务端字段。
                        auto boot_wallpaper = cJSON_GetObjectItem(payload.get(), "boot_wallpaper");
                        if (cJSON_IsObject(boot_wallpaper)) {
                            WallpaperRequest boot_request =
                                ParseWallpaperRequest(boot_wallpaper, true);
                            boot_request.kind = WallpaperKind::Boot;
                            if (!boot_request.url.empty() && !boot_request.md5.empty()) {
                                WallpaperManager::GetInstance().HandleSet(boot_request, nullptr);
                            } else {
                                ESP_LOGW(TAG,
                                         "Ignore device_config boot_wallpaper without url/md5");
                            }
                        }
                        // 首次云端配置处理完毕（含唤醒词）：仅在日志输出，屏幕直接显示待机
                        // 语音引擎未就绪时词会被缓存并随后生效（见 AudioService）
                        if (!cloud_config_synced_) {
                            cloud_config_synced_ = true;
                            pending_config_synced_ = false;
                            ESP_LOGI(TAG, "云端配置同步完成（唤醒词已生效/已缓存待引擎就绪）");
                            if (GetDeviceState() == kDeviceStateIdle) {
                                // 仅在日志输出，不在屏幕显示"唤醒词就绪"
                                auto display = Board::GetInstance().GetDisplay();
                                display->SetStatus(Lang::Strings::STANDBY);
                            } else {
                                // 设备不在Idle状态，缓存标志，等转入Idle后再触发
                                pending_config_synced_ = true;
                                ESP_LOGI(TAG, "云端配置已收到但设备未处于Idle状态，等待状态转换");
                            }
                        }
                    });
                } else {
                    ESP_LOGE(TAG, "Failed to serialize device_config payload");
                }
            } else {
                ESP_LOGW(TAG, "Invalid device_config message: missing payload object");
            }
        } else if (strcmp(type->valuestring, "system") == 0) {
            auto command = cJSON_GetObjectItem(root, "command");
            if (cJSON_IsString(command)) {
                ESP_LOGI(TAG, "System command: %s", command->valuestring);
                if (strcmp(command->valuestring, "reboot") == 0) {
                    // Do a reboot if user requests a OTA update
                    Schedule([this]() { Reboot(); });
                } else {
                    ESP_LOGW(TAG, "Unknown system command: %s", command->valuestring);
                }
            }
        } else if (strcmp(type->valuestring, "alert") == 0) {
            auto status = cJSON_GetObjectItem(root, "status");
            auto message = cJSON_GetObjectItem(root, "message");
            auto emotion = cJSON_GetObjectItem(root, "emotion");
            if (cJSON_IsString(status) && cJSON_IsString(message) && cJSON_IsString(emotion)) {
                Alert(status->valuestring, message->valuestring, emotion->valuestring,
                      Lang::Sounds::OGG_VIBRATION);
            } else {
                ESP_LOGW(TAG, "Alert command requires status, message and emotion");
            }
#if CONFIG_RECEIVE_CUSTOM_MESSAGE
        } else if (strcmp(type->valuestring, "custom") == 0) {
            auto payload = cJSON_GetObjectItem(root, "payload");
            CJsonStringUniquePtr root_json(cJSON_PrintUnformatted(root));
            ESP_LOGI(TAG, "Received custom message: %s", root_json ? root_json.get() : "");
            if (cJSON_IsObject(payload)) {
                CJsonStringUniquePtr payload_json(cJSON_PrintUnformatted(payload));
                if (payload_json) {
                    Schedule(
                        [this, display, payload_str = std::string(payload_json.get())]() {
                            display->SetChatMessage("system", payload_str.c_str());
                        });
                }
            } else {
                ESP_LOGW(TAG, "Invalid custom message format: missing payload");
            }
#endif
        } else if (strcmp(type->valuestring, "goodbye") == 0) {
            auto session_id = cJSON_GetObjectItem(root, "session_id");
            ESP_LOGI(TAG, "Received goodbye message, session_id: %s",
                     cJSON_IsString(session_id) ? session_id->valuestring : "null");
            if (cJSON_IsString(session_id) && protocol_->session_id() == session_id->valuestring) {
                // Server initiated goodbye; don't send goodbye back to avoid ping-pong.
                Schedule([this]() {
                    if (protocol_ && protocol_->IsAudioChannelOpened()) {
                        protocol_->CloseAudioChannel(false);
                    }
                });
            }
        } else {
            ESP_LOGW(TAG, "Unknown message type: %s", type->valuestring);
        }
    });

    protocol_->Start();
}

void Application::ShowActivationCode(const std::string& code, const std::string& message) {
    struct digit_sound {
        char digit;
        const std::string_view& sound;
    };
    static const std::array<digit_sound, 10> digit_sounds{
        {digit_sound{'0', Lang::Sounds::OGG_0}, digit_sound{'1', Lang::Sounds::OGG_1},
         digit_sound{'2', Lang::Sounds::OGG_2}, digit_sound{'3', Lang::Sounds::OGG_3},
         digit_sound{'4', Lang::Sounds::OGG_4}, digit_sound{'5', Lang::Sounds::OGG_5},
         digit_sound{'6', Lang::Sounds::OGG_6}, digit_sound{'7', Lang::Sounds::OGG_7},
         digit_sound{'8', Lang::Sounds::OGG_8}, digit_sound{'9', Lang::Sounds::OGG_9}}};

    // This sentence uses 9KB of SRAM, so we need to wait for it to finish
    Alert(Lang::Strings::ACTIVATION, message.c_str(), "link", Lang::Sounds::OGG_ACTIVATION);

    for (const auto& digit : code) {
        auto it = std::find_if(digit_sounds.begin(), digit_sounds.end(),
                               [digit](const digit_sound& ds) { return ds.digit == digit; });
        if (it != digit_sounds.end()) {
            audio_service_.PlaySound(it->sound);
        }
    }
}

void Application::Alert(const char* status, const char* message, const char* emotion,
                        const std::string_view& sound) {
    ESP_LOGW(TAG, "Alert [%s] %s: %s", emotion, status, message);
    auto display = Board::GetInstance().GetDisplay();
    display->SetStatus(status);
    display->SetEmotion(emotion);
    display->SetChatMessage("system", message);
    if (!sound.empty()) {
        audio_service_.PlaySound(sound);
    }
}

void Application::DismissAlert() {
    last_error_message_.clear();
    if (GetDeviceState() == kDeviceStateIdle) {
        auto display = Board::GetInstance().GetDisplay();
        ESP_LOGI(TAG, "device_config%s", cloud_config_synced_ ? "synced" : "not yet received");
        display->SetStatus(Lang::Strings::STANDBY);
        display->SetEmotion("neutral");
        display->SetChatMessage("system", "");
    }
}

void Application::ToggleChatState() { xEventGroupSetBits(event_group_, MAIN_EVENT_TOGGLE_CHAT); }

// ---------------- 兜底自动重连（2026-10-08）----------------
// 背景设备在线时仍出现 ws://sandyun.top:8001/yuhe/v1/ 连接失败并弹
// 阻塞 Alert。此兜底：任何网络错误 -> 静默指数退避重连（2s 起步，x1.5，
// 封顶 60s，无限次），连上即停。错误只在屏幕气泡轻提示，不播音效不锁状态。
void Application::StartAutoReconnect() {
    if (reconnect_timer_handle_ == nullptr) {
        esp_timer_create_args_t args = {
            .callback =
                [](void* arg) {
                    auto* app = static_cast<Application*>(arg);
                    ESP_LOGI(TAG, "AutoReconnect tick (attempt %d)", app->reconnect_attempt_);
                    app->Schedule([app]() {
                        // 已连上则收手
                        if (app->protocol_ && app->protocol_->IsAudioChannelOpened()) {
                            app->StopAutoReconnect();
                            return;
                        }
                        // 静默重连：直接调 OpenAudioChannel，失败会再次触发
                        // OnNetworkError -> StartAutoReconnect（幂等续期）
                        if (!app->protocol_->OpenAudioChannel()) {
                            ESP_LOGW(TAG, "AutoReconnect attempt failed");
                        }
                    });
                },
            .arg = this,
            .dispatch_method = ESP_TIMER_TASK,
            .name = "auto_reconnect",
            .skip_unhandled_events = true,
        };
        ESP_ERROR_CHECK(esp_timer_create(&args, &reconnect_timer_handle_));
    }
    // 指数退避：2s, 3s, 4.5s, 7s ... 封顶 60s
    int64_t delay_us;
    if (reconnect_attempt_ == 0) {
        delay_us = 2000000;
    } else {
        double d = 2000000.0 * pow(1.5, reconnect_attempt_);
        delay_us = (int64_t)(d > 60000000.0 ? 60000000.0 : d);
    }
    reconnect_attempt_++;
    esp_timer_stop(reconnect_timer_handle_);  // 幂等：覆盖旧周期
    esp_timer_start_once(reconnect_timer_handle_, delay_us);
    ESP_LOGI(TAG, "AutoReconnect scheduled in %lld ms (attempt %d)",
             (long long)(delay_us / 1000), reconnect_attempt_);
}

void Application::StopAutoReconnect() {
    reconnect_attempt_ = 0;
    if (reconnect_timer_handle_ != nullptr) {
        esp_timer_stop(reconnect_timer_handle_);
    }
    ESP_LOGI(TAG, "AutoReconnect stopped (connected)");
}

void Application::StartListening() { xEventGroupSetBits(event_group_, MAIN_EVENT_START_LISTENING); }

void Application::StopListening() { xEventGroupSetBits(event_group_, MAIN_EVENT_STOP_LISTENING); }

void Application::HandleToggleChatEvent() {
    auto state = GetDeviceState();

    if (state == kDeviceStateNotifying) {
        StopNotification();
        state = kDeviceStateIdle;
    }

    if (state == kDeviceStateActivating) {
        SetDeviceState(kDeviceStateIdle);
        return;
    } else if (state == kDeviceStateWifiConfiguring) {
        audio_service_.EnableAudioTesting(true);
        SetDeviceState(kDeviceStateAudioTesting);
        return;
    } else if (state == kDeviceStateAudioTesting) {
        audio_service_.EnableAudioTesting(false);
        SetDeviceState(kDeviceStateWifiConfiguring);
        return;
    }

    if (!protocol_) {
        ESP_LOGE(TAG, "Protocol not initialized");
        return;
    }

    if (state == kDeviceStateIdle) {
        ListeningMode mode = GetDefaultListeningMode();
        if (!protocol_->IsAudioChannelOpened()) {
            SetDeviceState(kDeviceStateConnecting);
            // Schedule to let the state change be processed first (UI update)
            Schedule([this, mode]() { ContinueOpenAudioChannel(mode); });
            return;
        }
        SetListeningMode(mode);
    } else if (state == kDeviceStateSpeaking) {
        AbortSpeaking(kAbortReasonNone);
    } else if (state == kDeviceStateListening) {
        protocol_->CloseAudioChannel();
    }
}

void Application::ContinueOpenAudioChannel(ListeningMode mode) {
    // Check state again in case it was changed during scheduling
    if (GetDeviceState() != kDeviceStateConnecting) {
        return;
    }

    // Switch to performance mode before connecting to reduce latency
    auto& board = Board::GetInstance();
    board.SetPowerSaveLevel(PowerSaveLevel::PERFORMANCE);

    if (!protocol_->IsAudioChannelOpened()) {
        if (!protocol_->OpenAudioChannel()) {
            ESP_LOGE(TAG, "OpenAudioChannel failed (toggle chat)");
            // Return to idle so the device is not stuck in the connecting
            // state (not every failure path reports a network error)
            SetDeviceState(kDeviceStateIdle);
            return;
        }
    }

    SetListeningMode(mode);
}

void Application::HandleStartListeningEvent() {
    auto state = GetDeviceState();

    if (state == kDeviceStateNotifying) {
        StopNotification();
        state = kDeviceStateIdle;
    }

    if (state == kDeviceStateActivating) {
        SetDeviceState(kDeviceStateIdle);
        return;
    } else if (state == kDeviceStateWifiConfiguring) {
        audio_service_.EnableAudioTesting(true);
        SetDeviceState(kDeviceStateAudioTesting);
        return;
    }

    if (!protocol_) {
        ESP_LOGE(TAG, "Protocol not initialized");
        return;
    }

    if (state == kDeviceStateIdle) {
        if (!protocol_->IsAudioChannelOpened()) {
            SetDeviceState(kDeviceStateConnecting);
            // Schedule to let the state change be processed first (UI update)
            Schedule([this]() { ContinueOpenAudioChannel(kListeningModeManualStop); });
            return;
        }
        SetListeningMode(kListeningModeManualStop);
    } else if (state == kDeviceStateSpeaking) {
        AbortSpeaking(kAbortReasonNone);
        SetListeningMode(kListeningModeManualStop);
    }
}

void Application::HandleStopListeningEvent() {
    auto state = GetDeviceState();

    if (state == kDeviceStateNotifying) {
        StopNotification();
    } else if (state == kDeviceStateAudioTesting) {
        audio_service_.EnableAudioTesting(false);
        SetDeviceState(kDeviceStateWifiConfiguring);
        return;
    } else if (state == kDeviceStateListening) {
        if (protocol_) {
            protocol_->SendStopListening();
        }
        SetDeviceState(kDeviceStateIdle);
    }
}

void Application::HandleWakeWordDetectedEvent() {
    if (!protocol_) {
        return;
    }

    auto state = GetDeviceState();
    auto wake_word = audio_service_.GetLastWakeWord();
    ESP_LOGI(TAG, "Wake word detected: %s (state: %d)", wake_word.c_str(), (int)state);

    if (state == kDeviceStateIdle) {
        BeginWakeWordInvoke(wake_word);
    } else if (state == kDeviceStateNotifying) {
        StopNotification();
        BeginWakeWordInvoke(wake_word);
    } else if (state == kDeviceStateSpeaking || state == kDeviceStateListening) {
#if !CONFIG_YH_REALTIME_INTERRUPT
        if (state == kDeviceStateSpeaking) {
            // 实时打断总开关关闭：播报中唤醒词不打断（回声误触发防护 +
            // Realtime API 预留）。Listening 态的唤醒词处理不受影响。
            ESP_LOGI(TAG, "Ignore wake word in speaking: realtime interrupt disabled");
            return;
        }
#endif
        AbortSpeaking(kAbortReasonWakeWordDetected);
        // Clear send queue to avoid sending residues to server
        while (audio_service_.PopPacketFromSendQueue())
            ;

        if (state == kDeviceStateListening) {
            protocol_->SendStartListening(GetDefaultListeningMode());
            audio_service_.ResetDecoder();
            audio_service_.PlaySound(Lang::Sounds::OGG_POPUP);
            // Re-enable wake word detection as it was stopped by the detection itself
            audio_service_.EnableWakeWordDetection(true);
        } else {
            // Speaking 态被唤醒词打断（真实用户唤醒或回声误触发），转听音时
            // 不再补播 OGG_POPUP"滴"声：误触发场景下它是凭空噪声且掐断了
            // 播报，真实唤醒场景的反馈交给屏幕状态与 LED（对齐 410 行语音
            // 打断的静默化原则）。
            SetListeningMode(GetDefaultListeningMode());
        }
    } else if (state == kDeviceStateActivating) {
        // Restart the activation check if the wake word is detected during activation
        SetDeviceState(kDeviceStateIdle);
    }
}

void Application::BeginWakeWordInvoke(const std::string& wake_word) {
    // Must run in the main task with the device in idle state
    audio_service_.EncodeWakeWord();

    // Always pass through the connecting state, even if the audio channel is
    // already opened. ContinueWakeWordInvoke() rejects any other state, so
    // skipping this transition would silently drop the wake word invocation.
    if (!SetDeviceState(kDeviceStateConnecting)) {
        // Wake word detection was stopped by the detection itself; restore it
        // so the device does not become unresponsive to wake words.
        audio_service_.EnableWakeWordDetection(true);
        return;
    }

    if (!protocol_->IsAudioChannelOpened()) {
        // Schedule to let the state change be processed first (UI update),
        // then continue with OpenAudioChannel which may block for ~1 second
        Schedule([this, wake_word]() { ContinueWakeWordInvoke(wake_word); });
        return;
    }
    // Channel already opened, continue directly
    ContinueWakeWordInvoke(wake_word);
}

void Application::ContinueWakeWordInvoke(const std::string& wake_word) {
    // Check state again in case it was changed during scheduling
    if (GetDeviceState() != kDeviceStateConnecting) {
        return;
    }

    // Switch to performance mode before connecting to reduce latency
    auto& board = Board::GetInstance();
    board.SetPowerSaveLevel(PowerSaveLevel::PERFORMANCE);

    if (!protocol_->IsAudioChannelOpened()) {
        if (!protocol_->OpenAudioChannel()) {
            ESP_LOGE(TAG, "OpenAudioChannel failed (wake word invoke)");
            // Return to idle so the device is not stuck in the connecting
            // state (not every failure path reports a network error), and
            // wake word detection is re-enabled by the idle state handler.
            SetDeviceState(kDeviceStateIdle);
            return;
        }
    }

    ESP_LOGI(TAG, "Wake word detected: %s", wake_word.c_str());
#if CONFIG_SEND_WAKE_WORD_DATA
    // Encode and send the wake word data to the server
    while (auto packet = audio_service_.PopWakeWordPacket()) {
        protocol_->SendAudio(std::move(packet));
    }
    // Set the chat state to wake word detected
    protocol_->SendWakeWordDetected(wake_word);
    SetListeningMode(GetDefaultListeningMode());
#else
    // Set flag to play popup sound after state changes to listening
    // (PlaySound here would be cleared by ResetDecoder in EnableVoiceProcessing)
    play_popup_on_listening_ = true;
    SetListeningMode(GetDefaultListeningMode());
#endif
}

void Application::HandleStateChangedEvent() {
    DeviceState new_state = state_machine_.GetState();
    clock_ticks_ = 0;
    // Any state change invalidates a pending deferred listening start;
    // the Listening case below re-arms it when needed.
    // pending_tts_stop_ 只在 Speaking 态有意义（等 drained 切 Listening），
    // 任何其他状态切换都意味着它已过期（打断/新会话/空闲），一并失效。
    // 若本次切换正是 drained 收割触发的，标志已在切换前清掉，不受影响。
    if (new_state != kDeviceStateSpeaking) {
        pending_tts_stop_ = false;
    }
    pending_listening_start_ = false;

    auto& board = Board::GetInstance();
    auto display = board.GetDisplay();
    auto led = board.GetLed();
    led->OnStateChanged();

    switch (new_state) {
        case kDeviceStateUnknown:
        case kDeviceStateIdle:
            // Keep a just-raised network error visible. SetDeviceState(idle)
            // queues STATE_CHANGED after Alert(), and the idle handler would
            // otherwise wipe the status, emotion, and chat message.
            if (last_error_message_.empty()) {
                // 云端 device_config 尚未到达：仅在日志中记录，不在屏幕上显示"配置同步中"
                ESP_LOGI(TAG, "device_config%s", cloud_config_synced_ ? "synced" : "not yet received");
                display->ClearChatMessages();  // Clear messages first
                display->SetStatus(Lang::Strings::STANDBY);
                display->SetEmotion(
                    "neutral");  // Then set emotion (wechat mode checks child count)

                // 若device_config已到达但设备不在Idle时未处理，现在补发UI更新
                if (pending_config_synced_ && cloud_config_synced_) {
                    pending_config_synced_ = false;
                    // 仅在日志输出，不在屏幕显示"唤醒词就绪"
                    ESP_LOGI(TAG, "云端配置同步完成（补发UI更新）");
                    display->SetStatus(Lang::Strings::STANDBY);
                } else if (!cloud_config_synced_ && config_synced_timer_handle_ == nullptr) {
                    // 超时保护：30秒内未收到device_config则强制显示待机
                    esp_timer_create_args_t timeout_args = {
                        .callback =
                            [](void* arg) {
                                Application* app = (Application*)arg;
                                app->Schedule([app]() {
                                    if (app->GetDeviceState() == kDeviceStateIdle &&
                                        !app->cloud_config_synced_) {
                                        auto display = Board::GetInstance().GetDisplay();
                                        display->SetStatus(Lang::Strings::STANDBY);
                                        ESP_LOGW(TAG, "device_config超时30秒，强制显示待机");
                                    }
                                });
                            },
                        .arg = this,
                        .dispatch_method = ESP_TIMER_TASK,
                        .name = "config_timeout",
                        .skip_unhandled_events = true};
                    esp_timer_handle_t timeout_handle = nullptr;
                    esp_timer_create(&timeout_args, &timeout_handle);
                    if (timeout_handle != nullptr) {
                        esp_timer_start_once(timeout_handle, 30 * 1000000ULL);
                    }
                }
            }
            audio_service_.EnableVoiceProcessing(false);
            audio_service_.EnableWakeWordDetection(true);
            break;
        case kDeviceStateConnecting:
            display->SetStatus(Lang::Strings::CONNECTING);
            display->SetEmotion("neutral");
            display->SetChatMessage("system", "");
            break;
        case kDeviceStateListening:
            display->SetStatus(Lang::Strings::LISTENING);
            display->SetEmotion("neutral");

            // Make sure the audio processor is running
            if (play_popup_on_listening_ || !audio_service_.IsAudioProcessorRunning()) {
                // For auto mode, wait for the playback queue to drain before enabling
                // voice processing. This prevents audio truncation when STOP arrives
                // late due to network jitter. Instead of blocking the main loop here,
                // defer the start until MAIN_EVENT_PLAYBACK_DRAINED arrives.
                if (listening_mode_ == kListeningModeAutoStop && !audio_service_.IsPlaybackIdle()) {
                    pending_listening_start_ = true;
                } else {
                    StartListeningAudio();
                }
            } else {
                ConfigureWakeWordForListening();
            }
            break;
        case kDeviceStateSpeaking:
            display->SetStatus(Lang::Strings::SPEAKING);

            // Speaking 态的"边播边听"分三种情况（与 GetDefaultListeningMode 的
            // aec_mode_ 判定一一对应）：
            //   1. 服务端 AEC（CONFIG_USE_SERVER_AEC）：麦克风持续推流给服务器，
            //      回声消除与打断判断都在服务端做（receiveAudioHandle:
            //      client_aec && have_voice && client_is_speaking → abort）。
            //      本地 VAD 必须关——单工板没有回采通道，开着必然被自己打断。
            //   2. 设备侧 AEC 真正生效（有回采通道）：本地 VAD + 服务器双路并行。
            //   3. 都没有：关语音处理，只剩唤醒词打断（application.cc:1266）。
#if !CONFIG_YH_REALTIME_INTERRUPT
            // 实时打断总开关关闭：播报期不向服务器推麦克风流（服务端 ASR 打断
            // 的数据源头），也关本地 VAD——设备侧彻底静默，播报完整播完。
            // 播报结束回 Listening 时 StartListeningAudio 会重新开嗓+推流。
            // 播报期唤醒词检测按无 AEC 板的原生策略保留（AFE 检测），
            // 触发后由 HandleWakeWordDetectedEvent 的开关分支静默忽略。
            audio_service_.EnableVoiceProcessing(false);
            audio_service_.EnableWakeWordDetection(audio_service_.IsAfeWakeWord());
#else
            if (listening_mode_ == kListeningModeRealtime &&
                audio_service_.IsDeviceAecEffective()) {
                // 设备侧 AEC 生效：保持 VAD（本地打断 + 推流都开）
            } else if (aec_mode_ == kAecOnServerSide) {
                // 服务端 AEC：麦克风持续推流给服务器（服务器做回声消除与打断
                // 判断），本地 VAD 必须关——单工板没有回采通道，开着必然被
                // 自己的播报声触发。唤醒词检测同样必须关：播报声经 AEC 残留
                // 回声仍会偶发触发 AFE 唤醒模型（实测"播到一半滴一声被打断"，
                // 即 HandleWakeWordDetectedEvent 在 Speaking 态误触发 →
                // AbortSpeaking + 进 Listening 补播 OGG_POPUP）。播报期打断
                // 完全交给服务器人声确认窗（interrupt_confirm_ms）；播报结束
                // 回 Idle/Listening 时会重新开启唤醒词检测。
                audio_service_.EnableVoiceProcessing(true);
                audio_service_.EnableWakeWordDetection(false);
            } else {
                audio_service_.EnableVoiceProcessing(false);
                // Only AFE wake word can be detected in speaking mode
                audio_service_.EnableWakeWordDetection(audio_service_.IsAfeWakeWord());
            }
#endif
            audio_service_.ResetDecoder();
            break;
        case kDeviceStateNotifying:
            display->SetStatus(Lang::Strings::SPEAKING);
            audio_service_.EnableVoiceProcessing(false);
            audio_service_.EnableWakeWordDetection(audio_service_.IsAfeWakeWord());
            break;
        case kDeviceStateWifiConfiguring:
            audio_service_.EnableVoiceProcessing(false);
            audio_service_.EnableWakeWordDetection(false);
            break;
        default:
            // Do nothing
            break;
    }
}

void Application::StartListeningAudio() {
    // Runs in the main loop, either directly from HandleStateChangedEvent or
    // deferred via MAIN_EVENT_PLAYBACK_DRAINED once the playback queue drains.
    if (GetDeviceState() != kDeviceStateListening) {
        return;
    }

    // Send the start listening command
    protocol_->SendStartListening(listening_mode_);
    audio_service_.EnableVoiceProcessing(true);

    ConfigureWakeWordForListening();

    // Play popup sound after ResetDecoder (in EnableVoiceProcessing) has been called
    if (play_popup_on_listening_) {
        play_popup_on_listening_ = false;
        audio_service_.PlaySound(Lang::Sounds::OGG_POPUP);
    }
}

void Application::ConfigureWakeWordForListening() {
#ifdef CONFIG_WAKE_WORD_DETECTION_IN_LISTENING
    // Enable wake word detection in listening mode (configured via Kconfig)
    audio_service_.EnableWakeWordDetection(audio_service_.IsAfeWakeWord());
#else
    // Disable wake word detection in listening mode
    audio_service_.EnableWakeWordDetection(false);
#endif
}

void Application::StartNotification(std::string audio_url, std::vector<NotifySubtitle> subtitles, NotifyPriority priority) {
    if (GetDeviceState() != kDeviceStateIdle || notify_player_.IsBusy()) {
        ESP_LOGW(TAG, "Ignoring notify message while device is busy");
        return;
    }

    auto& board = Board::GetInstance();
    board.SetPowerSaveLevel(PowerSaveLevel::PERFORMANCE);
    audio_service_.EnableVoiceProcessing(false);
    audio_service_.EnableWakeWordDetection(audio_service_.IsAfeWakeWord());
    audio_service_.ReleaseWakeWordResources();
    while (audio_service_.PopPacketFromSendQueue()) {
        // Discard microphone audio left over from a previous conversation.
    }

    if (!SetDeviceState(kDeviceStateNotifying)) {
        board.SetPowerSaveLevel(PowerSaveLevel::LOW_POWER);
        return;
    }

    audio_service_.ResetDecoder();
    uint32_t playback_id = ++notification_playback_id_;
    if (playback_id == 0) {
        playback_id = ++notification_playback_id_;
    }
    audio_service_.PlaySound(Lang::Sounds::OGG_POPUP);

    bool started = notify_player_.Start(
        std::move(audio_url), std::move(subtitles), playback_id,
        [this](uint32_t id, const std::string& text) {
            Schedule([this, id, text]() {
                if (GetDeviceState() == kDeviceStateNotifying && notification_playback_id_ == id) {
                    Board::GetInstance().GetDisplay()->SetChatMessage("assistant", text.c_str());
                }
            });
        },
        [this](uint32_t id, bool success) {
            Schedule([this, id, success]() { HandleNotificationFinished(id, success); });
        });

    if (!started) {
        ESP_LOGE(TAG, "Failed to start notification playback");
        StopNotification();
    }
}

void Application::StopNotification() {
    notify_player_.Stop();
    audio_service_.ResetDecoder();
    auto& board = Board::GetInstance();
    board.GetDisplay()->SetChatMessage("assistant", "");
    board.SetPowerSaveLevel(PowerSaveLevel::LOW_POWER);
    if (GetDeviceState() == kDeviceStateNotifying) {
        SetDeviceState(kDeviceStateIdle);
    }
}

void Application::HandleNotificationFinished(uint32_t playback_id, bool success) {
    if (GetDeviceState() != kDeviceStateNotifying || notification_playback_id_ != playback_id) {
        return;
    }
    ESP_LOGI(TAG, "Notification playback %lu %s", static_cast<unsigned long>(playback_id),
             success ? "completed" : "failed");
    StopNotification();
}

void Application::Schedule(std::function<void()>&& callback) {
    {
        std::lock_guard<std::mutex> lock(mutex_);
        main_tasks_.push_back(std::move(callback));
    }
    xEventGroupSetBits(event_group_, MAIN_EVENT_SCHEDULE);
}

void Application::AbortSpeaking(AbortReason reason) {
    ESP_LOGI(TAG, "Abort speaking");
    aborted_ = true;
    if (protocol_) {
        protocol_->SendAbortSpeaking(reason);
    }
}

void Application::NotifyTimerCallback(void* arg) {
    Application* app = static_cast<Application*>(arg);
    app->Schedule([app]() {
        if (!app->pending_notify_active_) {
            return;
        }
        std::string url = app->pending_notify_url_;
        std::string text = app->pending_notify_text_;
        app->pending_notify_active_ = false;
        if (app->GetDeviceState() == kDeviceStateIdle) {
            std::vector<NotifySubtitle> subtitles;
            if (!text.empty()) {
                NotifySubtitle sub;
                sub.text = text;
                subtitles.push_back(sub);
            }
            app->StartNotification(url, std::move(subtitles));
        } else {
            ESP_LOGW(TAG, "ScheduleNotify: device not idle (state=%d), dropping notification",
                     (int)app->GetDeviceState());
        }
    });
}

void Application::ScheduleNotify(const std::string& audio_url, const std::string& text) {
    pending_notify_url_ = audio_url;
    pending_notify_text_ = text;
    pending_notify_active_ = true;
    if (notify_timer_handle_ == nullptr) {
        esp_timer_create_args_t timer_args = {
            .callback = NotifyTimerCallback,
            .arg = this,
            .dispatch_method = ESP_TIMER_TASK,
            .name = "notify_timer",
            .skip_unhandled_events = true};
        esp_timer_create(&timer_args, &notify_timer_handle_);
    }
    esp_timer_start_once(notify_timer_handle_, 500 * 1000ULL);  // 500ms 后触发
    ESP_LOGI(TAG, "ScheduleNotify: url=%s text=%s", audio_url.c_str(), text.c_str());
}

void Application::SetListeningMode(ListeningMode mode) {
    listening_mode_ = mode;
    SetDeviceState(kDeviceStateListening);
}

ListeningMode Application::GetDefaultListeningMode() const {
    return aec_mode_ == kAecOff ? kListeningModeAutoStop : kListeningModeRealtime;
}

void Application::Reboot() {
    ESP_LOGI(TAG, "Rebooting...");
    if (GetDeviceState() == kDeviceStateNotifying) {
        StopNotification();
    }
    // Disconnect the audio channel
    if (protocol_ && protocol_->IsAudioChannelOpened()) {
        protocol_->CloseAudioChannel();
    }
    protocol_.reset();
    audio_service_.Stop();

    vTaskDelay(pdMS_TO_TICKS(1000));
    esp_restart();
}

bool Application::UpgradeFirmware(const std::string& url, const std::string& version) {
    auto& board = Board::GetInstance();
    auto display = board.GetDisplay();

    std::string upgrade_url = url;
    std::string version_info = version.empty() ? "(Manual upgrade)" : version;

    if (GetDeviceState() == kDeviceStateNotifying) {
        StopNotification();
    }

    // Close audio channel if it's open
    if (protocol_ && protocol_->IsAudioChannelOpened()) {
        ESP_LOGI(TAG, "Closing audio channel before firmware upgrade");
        protocol_->CloseAudioChannel();
    }
    ESP_LOGI(TAG, "Starting firmware upgrade from URL: %s", upgrade_url.c_str());

#ifdef CONFIG_YH_PROTOCOL_ENABLED
    // OTA 升级期间断开 YH 旁路通道，避免 reboot 瞬间服务器残留半开连接
    YhProtocol::GetInstance().Stop();
#endif

    Alert(Lang::Strings::OTA_UPGRADE, Lang::Strings::UPGRADING, "download",
          Lang::Sounds::OGG_UPGRADE);
    vTaskDelay(pdMS_TO_TICKS(3000));

    SetDeviceState(kDeviceStateUpgrading);

    std::string message = std::string(Lang::Strings::NEW_VERSION) + version_info;
    display->SetChatMessage("system", message.c_str());

    board.SetPowerSaveLevel(PowerSaveLevel::PERFORMANCE);
    audio_service_.Stop();
    vTaskDelay(pdMS_TO_TICKS(1000));

    bool upgrade_success = Ota::Upgrade(upgrade_url, [this, display](int progress, size_t speed) {
        char buffer[32];
        snprintf(buffer, sizeof(buffer), "%d%% %uKB/s", progress, speed / 1024);
        Schedule([display, message = std::string(buffer)]() {
            display->SetChatMessage("system", message.c_str());
        });
    });

    if (!upgrade_success) {
        // Upgrade failed, restart audio service and continue running
        ESP_LOGE(TAG,
                 "Firmware upgrade failed, restarting audio service and continuing operation...");
        audio_service_.Start();                              // Restart audio service
        board.SetPowerSaveLevel(PowerSaveLevel::LOW_POWER);  // Restore power save level
        Alert(Lang::Strings::ERROR, Lang::Strings::UPGRADE_FAILED, "cancel",
              Lang::Sounds::OGG_EXCLAMATION);
        vTaskDelay(pdMS_TO_TICKS(3000));
        return false;
    } else {
        // Upgrade success, reboot immediately
        ESP_LOGI(TAG, "Firmware upgrade successful, rebooting...");
        display->SetChatMessage("system", "Upgrade successful, rebooting...");
        vTaskDelay(pdMS_TO_TICKS(1000));  // Brief pause to show message
        Reboot();
        return true;
    }
}

void Application::WakeWordInvoke(const std::string& wake_word) {
    if (!protocol_) {
        return;
    }

    auto state = GetDeviceState();

    if (state == kDeviceStateIdle) {
        // May be called from outside the main task (e.g. board button
        // callbacks), so schedule the invocation instead of running it here
        Schedule([this, wake_word]() {
            if (GetDeviceState() == kDeviceStateIdle) {
                BeginWakeWordInvoke(wake_word);
            }
        });
    } else if (state == kDeviceStateNotifying) {
        Schedule([this, wake_word]() {
            if (GetDeviceState() == kDeviceStateNotifying) {
                StopNotification();
                BeginWakeWordInvoke(wake_word);
            }
        });
    } else if (state == kDeviceStateSpeaking) {
#if !CONFIG_YH_REALTIME_INTERRUPT
        // 实时打断总开关关闭：播报中外部唤醒调用（板级按钮/自定义唤醒词）
        // 不打断播报，静默忽略。
        ESP_LOGI(TAG, "Ignore wake word invoke in speaking: realtime interrupt disabled");
#else
        Schedule([this]() { AbortSpeaking(kAbortReasonNone); });
#endif
    } else if (state == kDeviceStateListening) {
        Schedule([this]() {
            if (protocol_) {
                protocol_->CloseAudioChannel();
            }
        });
    }
}

bool Application::CanEnterSleepMode() {
    if (GetDeviceState() != kDeviceStateIdle) {
        return false;
    }

    if (protocol_ && protocol_->IsAudioChannelOpened()) {
        return false;
    }

    if (!audio_service_.IsIdle()) {
        return false;
    }

    // Now it is safe to enter sleep mode
    return true;
}

void Application::RegisterMcpBroadcastCallback(std::function<void(const std::string&)> callback) {
    mcp_broadcast_callback_ = std::move(callback);
}

void Application::SendMcpMessage(const std::string& payload) {
    // Always schedule to run in main task for thread safety
    Schedule([this, payload]() {
        if (protocol_) {
            protocol_->SendMcpMessage(payload);
        }
        if (mcp_broadcast_callback_) {
            mcp_broadcast_callback_(payload);
        }
    });
}

void Application::SendWallpaperAck(const std::string& version, bool ok,
                                   const std::string& reason, WallpaperKind kind) {
    // 运行在主任务（调用方已 Schedule），protocol_ 生命周期安全
    if (protocol_ == nullptr) {
        ESP_LOGW(TAG, "Drop wallpaper ack: protocol is not ready");
        return;
    }
    std::string message = "{\"type\":\"wallpaper\",\"action\":\"result\",\"version\":\"";
    message += EscapeJson(version);
    message += "\",\"status\":\"";
    message += ok ? "ok" : "fail";
    message += "\",\"kind\":\"";
    // boot 槽才带 kind 字段；idle 保持最小字段集，与旧服务端完全兼容
    // （旧版 Python 端解析不认识的字段会被忽略，但省字段更稳妥）
    message += (kind == WallpaperKind::Boot) ? "boot" : "idle";
    message += "\"";
    if (!ok) {
        // reason 只在失败回执里出现（成功回执保持最小字段集）
        message += ",\"reason\":\"";
        message += EscapeJson(reason);
        message += "\"";
    }
    message += "}";
    protocol_->SendJsonText(message);
    ESP_LOGI(TAG, "wallpaper ack: kind=%s version=%s status=%s reason=%s",
             kind == WallpaperKind::Boot ? "boot" : "idle", version.c_str(),
             ok ? "ok" : "fail", reason.c_str());
}

void Application::SendDeviceConfigReport(const std::string& key, int value) {
    // 运行上下文：物理键回调（button task）或 MCP 工具线程 → Schedule 到主任务
    // 再发（protocol_ 生命周期安全，与 SendWallpaperAck 同一纪律）
    Schedule([this, key, value]() {
        if (protocol_ == nullptr) {
            ESP_LOGW(TAG, "Drop device_config_report: protocol is not ready");
            return;
        }
        std::string message = "{\"type\":\"device_config_report\",\"config\":{\"";
        message += key;
        message += "\":";
        message += std::to_string(value);
        message += "}}";
        protocol_->SendJsonText(message);
        ESP_LOGI(TAG, "device_config_report: %s=%d", key.c_str(), value);
    });
}


void Application::SetAecMode(AecMode mode) {
    aec_mode_ = mode;
    Schedule([this]() {
        auto& board = Board::GetInstance();
        auto display = board.GetDisplay();
        switch (aec_mode_) {
            case kAecOff:
                audio_service_.EnableDeviceAec(false);
                display->ShowNotification(Lang::Strings::RTC_MODE_OFF);
                break;
            case kAecOnServerSide:
                audio_service_.EnableDeviceAec(false);
                display->ShowNotification(Lang::Strings::RTC_MODE_ON);
                break;
            case kAecOnDeviceSide:
                audio_service_.EnableDeviceAec(true);
                display->ShowNotification(Lang::Strings::RTC_MODE_ON);
                break;
        }

        // If the AEC mode is changed, close the audio channel
        if (protocol_ && protocol_->IsAudioChannelOpened()) {
            protocol_->CloseAudioChannel();
        }
    });
}

void Application::PlaySound(const std::string_view& sound) { audio_service_.PlaySound(sound); }

void Application::ResetProtocol() {
    Schedule([this]() {
        if (GetDeviceState() == kDeviceStateNotifying) {
            StopNotification();
        }
        // Close audio channel if opened
        if (protocol_ && protocol_->IsAudioChannelOpened()) {
            protocol_->CloseAudioChannel();
        }
        // Reset protocol
        protocol_.reset();
    });
}

void Application::SetConfigUpdatedCallback(std::function<void(bool success)> callback) {
    config_updated_callback_ = std::move(callback);
}

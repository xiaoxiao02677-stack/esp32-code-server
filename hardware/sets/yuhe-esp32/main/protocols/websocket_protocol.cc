#include "websocket_protocol.h"
#include "application.h"
#include "board.h"
#include "settings.h"
#include "system_info.h"

#include <esp_log.h>
#include <arpa/inet.h>
#include <esp_timer.h>
#include <cJSON.h>
#include <chrono>
#include <cstring>
#include "assets/lang_config.h"

#define TAG "WS"

WebsocketProtocol::WebsocketProtocol() { event_group_handle_ = xEventGroupCreate(); }

WebsocketProtocol::~WebsocketProtocol() { vEventGroupDelete(event_group_handle_); }

bool WebsocketProtocol::Start() {
    // Only connect to server when audio channel is needed
    return true;
}

bool WebsocketProtocol::SendAudio(std::unique_ptr<AudioStreamPacket> packet) {
    if (websocket_ == nullptr || !websocket_->IsConnected()) {
        return false;
    }

    bool sent = false;
    if (version_ == 2) {
        std::string serialized;
        serialized.resize(sizeof(BinaryProtocol2) + packet->payload.size());
        auto bp2 = (BinaryProtocol2*)serialized.data();
        bp2->version = htons(version_);
        bp2->type = 0;
        bp2->reserved = 0;
        bp2->timestamp = htonl(packet->timestamp);
        bp2->payload_size = htonl(packet->payload.size());
        memcpy(bp2->payload, packet->payload.data(), packet->payload.size());

        sent = websocket_->Send(serialized.data(), serialized.size(), true);
    } else if (version_ == 3) {
        std::string serialized;
        serialized.resize(sizeof(BinaryProtocol3) + packet->payload.size());
        auto bp3 = (BinaryProtocol3*)serialized.data();
        bp3->type = 0;
        bp3->reserved = 0;
        bp3->payload_size = htons(packet->payload.size());
        memcpy(bp3->payload, packet->payload.data(), packet->payload.size());

        sent = websocket_->Send(serialized.data(), serialized.size(), true);
    } else {
        sent = websocket_->Send(packet->payload.data(), packet->payload.size(), true);
    }

    if (!sent) {
        // The send path runs at frame rate (~16 Hz); only log state transitions
        // to avoid flooding the log when the link is down.
        if (!send_audio_error_state_) {
            ESP_LOGW(TAG, "SendAudio failed (audio link error)");
            send_audio_error_state_ = true;
        }
        send_audio_drop_count_++;
    } else if (send_audio_error_state_) {
        ESP_LOGI(TAG, "SendAudio recovered, %lu frames dropped",
                 (unsigned long)send_audio_drop_count_);
        send_audio_error_state_ = false;
        send_audio_drop_count_ = 0;
    }
    return sent;
}

bool WebsocketProtocol::SendText(const std::string& text) {
    if (websocket_ == nullptr || !websocket_->IsConnected()) {
        return false;
    }

    if (!websocket_->Send(text)) {
        // Truncate long payloads (e.g. tool call payloads) to keep the log line short.
        ESP_LOGE(TAG, "Failed to send text (len=%zu): %.128s", text.size(), text.c_str());
        SetError(Lang::Strings::SERVER_ERROR);
        return false;
    }

    return true;
}

bool WebsocketProtocol::IsAudioChannelOpened() const {
    return websocket_ != nullptr && websocket_->IsConnected() && !error_occurred_ && !IsTimeout();
}

void WebsocketProtocol::CloseAudioChannel(bool send_goodbye) {
    (void)send_goodbye;  // Websocket doesn't need to send goodbye message
    ESP_LOGI(TAG, "Closing audio channel");
    CloseUdpChannel();
    websocket_.reset();
}

bool WebsocketProtocol::OpenAudioChannel() {
    const auto open_channel_start_time = std::chrono::steady_clock::now();
    Settings settings("websocket", false);
    std::string url = settings.GetString("url");
    server_url_ = url;
    std::string token = settings.GetString("token");
    int version = settings.GetInt("version");
    if (version != 0) {
        version_ = version;
    }

    error_occurred_ = false;

    auto network = Board::GetInstance().GetNetwork();
    websocket_ = network->CreateWebSocket(1);
    if (websocket_ == nullptr) {
        ESP_LOGE(TAG, "Failed to create websocket");
        return false;
    }

    if (!token.empty()) {
        // If token not has a space, add "Bearer " prefix
        if (token.find(" ") == std::string::npos) {
            token = "Bearer " + token;
        }
        websocket_->SetHeader("Authorization", token.c_str());
    }
    websocket_->SetHeader("Protocol-Version", std::to_string(version_).c_str());
    websocket_->SetHeader("Device-Id", SystemInfo::GetMacAddress().c_str());
    websocket_->SetHeader("Client-Id", Board::GetInstance().GetUuid().c_str());

    websocket_->OnData([this](const char* data, size_t len, bool binary) {
        if (binary) {
            if (on_incoming_audio_ != nullptr) {
                if (version_ == 2) {
                    if (len < sizeof(BinaryProtocol2)) {
                        ReportBinaryFrameError(len, 0);
                        return;
                    }
                    BinaryProtocol2* bp2 = (BinaryProtocol2*)data;
                    const uint32_t payload_size = ntohl(bp2->payload_size);
                    // Subtraction form guards against size_t wrap-around when a
                    // corrupted payload_size makes the addition overflow.
                    if (len - sizeof(BinaryProtocol2) < payload_size) {
                        ReportBinaryFrameError(len, payload_size);
                        return;
                    }
                    bp2->version = ntohs(bp2->version);
                    bp2->type = ntohs(bp2->type);
                    bp2->timestamp = ntohl(bp2->timestamp);
                    auto payload = (uint8_t*)bp2->payload;
                    on_incoming_audio_(std::make_unique<AudioStreamPacket>(AudioStreamPacket{
                        .sample_rate = server_sample_rate_,
                        .frame_duration = server_frame_duration_,
                        .timestamp = bp2->timestamp,
                        .payload = std::vector<uint8_t>(payload, payload + payload_size)}));
                } else if (version_ == 3) {
                    if (len < sizeof(BinaryProtocol3)) {
                        ReportBinaryFrameError(len, 0);
                        return;
                    }
                    BinaryProtocol3* bp3 = (BinaryProtocol3*)data;
                    const uint16_t payload_size = ntohs(bp3->payload_size);
                    // Subtraction form guards against size_t wrap-around (see v2 above).
                    if (len - sizeof(BinaryProtocol3) < payload_size) {
                        ReportBinaryFrameError(len, payload_size);
                        return;
                    }
                    auto payload = (uint8_t*)bp3->payload;
                    on_incoming_audio_(std::make_unique<AudioStreamPacket>(AudioStreamPacket{
                        .sample_rate = server_sample_rate_,
                        .frame_duration = server_frame_duration_,
                        .timestamp = 0,
                        .payload = std::vector<uint8_t>(payload, payload + payload_size)}));
                } else {
                    on_incoming_audio_(std::make_unique<AudioStreamPacket>(AudioStreamPacket{
                        .sample_rate = server_sample_rate_,
                        .frame_duration = server_frame_duration_,
                        .timestamp = 0,
                        .payload = std::vector<uint8_t>((uint8_t*)data, (uint8_t*)data + len)}));
                }
                ReportBinaryFrameRecovered();
            }
        } else {
            // Parse JSON data
            auto root = cJSON_ParseWithLength(data, len);
            auto type = cJSON_GetObjectItem(root, "type");
            if (cJSON_IsString(type)) {
                if (strcmp(type->valuestring, "hello") == 0) {
                    ParseServerHello(root);
                } else {
                    if (on_incoming_json_ != nullptr) {
                        on_incoming_json_(root);
                    }
                }
            } else {
                ESP_LOGE(TAG, "Missing message type, data: %s", std::string(data, len).c_str());
            }
            cJSON_Delete(root);
        }
        last_incoming_time_ = std::chrono::steady_clock::now();
    });

    websocket_->OnDisconnected([this]() {
        ESP_LOGI(TAG, "Websocket disconnected");
        if (on_audio_channel_closed_ != nullptr) {
            on_audio_channel_closed_();
        }
    });

    ESP_LOGI(TAG, "Connecting to websocket server: %s with version: %d", url.c_str(), version_);
    if (auto connected = websocket_->Connect(url.c_str()); !connected) {
        ESP_LOGE(TAG, "Failed to connect to websocket server: %s",
                 connected.error().ToString().c_str());
        SetError(Lang::Strings::SERVER_NOT_CONNECTED, url);
        return false;
    }

    // Send hello message to describe the client
    auto message = GetHelloMessage();
    if (!SendText(message)) {
        return false;
    }

    // Wait for server hello
    EventBits_t bits =
        xEventGroupWaitBits(event_group_handle_, WEBSOCKET_PROTOCOL_SERVER_HELLO_EVENT, pdTRUE,
                            pdFALSE, pdMS_TO_TICKS(10000));
    if (!(bits & WEBSOCKET_PROTOCOL_SERVER_HELLO_EVENT)) {
        ESP_LOGE(TAG, "Failed to receive server hello");
        SetError(Lang::Strings::SERVER_TIMEOUT);
        return false;
    }

    if (on_audio_channel_opened_ != nullptr) {
        on_audio_channel_opened_();
    }

    // 启动 UDP 心跳（防止 NAT 超时）
    OpenUdpChannel();

    const auto elapsed_ms = std::chrono::duration_cast<std::chrono::milliseconds>(
                                std::chrono::steady_clock::now() - open_channel_start_time)
                                .count();
    ESP_LOGI(TAG, "Audio channel opened in %ld ms (session=%s, server=%d Hz, frame=%d ms)",
             (long)elapsed_ms, session_id_.c_str(), server_sample_rate_, server_frame_duration_);

    return true;
}

std::string WebsocketProtocol::GetHelloMessage() {
    // keys: message type, version, audio_params (format, sample_rate, channels)
    cJSON* root = cJSON_CreateObject();
    cJSON_AddStringToObject(root, "type", "hello");
    cJSON_AddNumberToObject(root, "version", version_);
    cJSON* features = cJSON_CreateObject();
#if CONFIG_USE_SERVER_AEC
    cJSON_AddBoolToObject(features, "aec", true);
#endif
    cJSON_AddBoolToObject(features, "mcp", true);
    cJSON_AddItemToObject(root, "features", features);
    AddTextFontCapabilities(root);
    cJSON_AddStringToObject(root, "transport", "websocket");
    cJSON* audio_params = cJSON_CreateObject();
    cJSON_AddStringToObject(audio_params, "format", "opus");
    cJSON_AddNumberToObject(audio_params, "sample_rate", 16000);
    cJSON_AddNumberToObject(audio_params, "channels", 1);
    cJSON_AddNumberToObject(audio_params, "frame_duration", OPUS_FRAME_DURATION_MS);
    cJSON_AddItemToObject(root, "audio_params", audio_params);
    auto json_str = cJSON_PrintUnformatted(root);
    std::string message(json_str);
    cJSON_free(json_str);
    cJSON_Delete(root);
    return message;
}

void WebsocketProtocol::ParseServerHello(const cJSON* root) {
    auto transport = cJSON_GetObjectItem(root, "transport");
    if (!cJSON_IsString(transport)) {
        ESP_LOGE(TAG, "Missing or non-string transport in server hello");
        return;
    }
    if (strcmp(transport->valuestring, "websocket") != 0) {
        ESP_LOGE(TAG, "Unsupported transport: %s", transport->valuestring);
        return;
    }

    auto session_id = cJSON_GetObjectItem(root, "session_id");
    if (cJSON_IsString(session_id)) {
        session_id_ = session_id->valuestring;
        ESP_LOGI(TAG, "Session ID: %s", session_id_.c_str());
    }

    auto audio_params = cJSON_GetObjectItem(root, "audio_params");
    if (cJSON_IsObject(audio_params)) {
        auto sample_rate = cJSON_GetObjectItem(audio_params, "sample_rate");
        if (cJSON_IsNumber(sample_rate)) {
            server_sample_rate_ = sample_rate->valueint;
        }
        auto frame_duration = cJSON_GetObjectItem(audio_params, "frame_duration");
        if (cJSON_IsNumber(frame_duration)) {
            server_frame_duration_ = frame_duration->valueint;
        }
    }
    ESP_LOGI(TAG, "Server hello: sample_rate=%d, frame_duration=%d ms", server_sample_rate_,
             server_frame_duration_);
    if (server_sample_rate_ <= 0) {
        ESP_LOGW(TAG, "Server hello has no valid audio_params, using defaults (%d Hz, %d ms)",
                 server_sample_rate_, server_frame_duration_);
    }

    xEventGroupSetBits(event_group_handle_, WEBSOCKET_PROTOCOL_SERVER_HELLO_EVENT);
}

void WebsocketProtocol::ReportBinaryFrameError(size_t len, size_t payload_size) {
    // Malformed frames may arrive in bursts; only log state transitions and
    // report the total on recovery, mirroring the SendAudio error handling.
    binary_frame_drop_count_++;
    if (!binary_frame_error_state_) {
        ESP_LOGW(TAG, "Dropping malformed binary frame (len=%u, payload_size=%u, version=%d)",
                 (unsigned)len, (unsigned)payload_size, version_);
        binary_frame_error_state_ = true;
    }
}

void WebsocketProtocol::ReportBinaryFrameRecovered() {
    if (binary_frame_error_state_) {
        ESP_LOGI(TAG, "Binary frames recovered, %lu dropped in total",
                 (unsigned long)binary_frame_drop_count_);
        binary_frame_error_state_ = false;
        binary_frame_drop_count_ = 0;
    }
}

bool WebsocketProtocol::OpenUdpChannel() {
    if (udp_connected_) return true;
    if (server_url_.empty()) {
        ESP_LOGW(TAG, "No server URL configured, skipping UDP channel");
        return false;
    }

    // Extract host from URL (ws://host:port/path -> host)
    std::string host = server_url_;
    // Remove ws:// or wss:// prefix up to and including "://"
    auto scheme_pos = host.find("://");
    if (scheme_pos != std::string::npos) {
        host.erase(0, scheme_pos + 3);
    }
    // Find port (host:port)
    auto colon_pos = host.find(':');
    if (colon_pos != std::string::npos) {
        host.erase(colon_pos);
    }
    // Remove path
    auto slash_pos = host.find('/');
    if (slash_pos != std::string::npos) {
        host.erase(slash_pos);
    }

    auto network = Board::GetInstance().GetNetwork();
    udp_ = network->CreateUdp(1);
    if (!udp_) {
        ESP_LOGE(TAG, "Failed to create UDP");
        return false;
    }
    udp_->OnMessage([](const std::string& data) {
        // UDP heartbeat response: can be extended for config sync
        ESP_LOGD(TAG, "UDP heartbeat response received (%zu bytes)", data.size());
    });
    // Connect to server UDP port (default 8002)
    if (auto result = udp_->Connect(host, 8002); !result) {
        ESP_LOGE(TAG, "Failed to connect UDP to %s:8002: %s", host.c_str(),
                 result.error().ToString().c_str());
        udp_ = nullptr;
        return false;
    }
    udp_connected_ = true;

    // Start UDP heartbeat timer (15s interval, staggered from TCP heartbeat)
    esp_timer_create_args_t args = {
        .callback = [](void* arg) {
            static_cast<WebsocketProtocol*>(arg)->SendUdpHeartbeat();
        },
        .arg = this,
        .dispatch_method = ESP_TIMER_TASK,
        .name = "ws_udp_heartbeat",
        .skip_unhandled_events = true
    };
    esp_timer_create(&args, &udp_heartbeat_timer_);
    esp_timer_start_periodic(udp_heartbeat_timer_, 15 * 1000 * 1000ULL);
    ESP_LOGI(TAG, "UDP heartbeat channel opened to %s:8002", host.c_str());
    return true;
}

void WebsocketProtocol::CloseUdpChannel() {
    if (udp_heartbeat_timer_) {
        esp_timer_stop(udp_heartbeat_timer_);
        esp_timer_delete(udp_heartbeat_timer_);
        udp_heartbeat_timer_ = nullptr;
    }
    if (udp_) {
        udp_->Disconnect();
        udp_ = nullptr;
    }
    udp_connected_ = false;
}

void WebsocketProtocol::SendUdpHeartbeat() {
    if (!udp_connected_ || !udp_) return;
    // 发送简单心跳包 {"type":"udp_heartbeat"}
    std::string heartbeat = "{\"type\":\"udp_heartbeat\"}";
    udp_->Send(heartbeat);
}

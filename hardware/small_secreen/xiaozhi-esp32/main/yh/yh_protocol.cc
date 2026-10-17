#include "yh_protocol.h"
#include "yh_ws2812_led.h"

#include <application.h>
#include <board.h>
#include <cjson_utils.h>
#include "notify/notify_player.h"
#include <system_info.h>

#include <esp_app_desc.h>
#include <esp_log.h>
#include <esp_random.h>
#include <esp_timer.h>

#include <tcp.h>

#include <cJSON.h>
#include <cstdio>
#include <cstring>
#include <memory>

#define TAG "YH"

namespace {

// ---- 协议常量 ----
constexpr int kProtocolVersion = 1;
// 25s 心跳：服务器 HEARTBEAT_MAX_AGE_S=30s 判死，30s 间隔会产生边界竞争
// （每周期闪 STALE），提前 5s 留出网络抖动余量。
constexpr int kHeartbeatIntervalMs = 25000;
constexpr int kReconnectMinDelayMs = 1000;
constexpr int kReconnectMaxDelayMs = 60000;
constexpr size_t kMaxFrameSize = 4096;  // 超长消息视为攻击, 直接断开
// 注意: 服务器端口以 Kconfig CONFIG_YH_SERVER_PORT 为准 (sdkconfig: 12399)
// 此常量已废弃, 保留仅作历史参考
// constexpr int kDefaultServerPort = 3333;

// 服务器 DeviceAck 错误码（与屿禾服务器一致）
constexpr const char* kErrNone = "NONE";
constexpr const char* kErrInvalidMessage = "INVALID_MESSAGE";
constexpr const char* kErrInvalidVersion = "INVALID_VERSION";
constexpr const char* kErrWrongDevice = "WRONG_DEVICE";
constexpr const char* kErrUnknownCommand = "UNKNOWN_COMMAND";
constexpr const char* kErrInvalidParameters = "INVALID_PARAMETERS";
constexpr const char* kErrDuplicateCommand = "DUPLICATE_COMMAND";
constexpr const char* kErrMalformedMessage = "MALFORMED_MESSAGE";
// 设备非 idle（listening/speaking/notifying/activating 等）拒绝 SEND_NOTIFY
constexpr const char* kErrBusy = "BUSY";

// 当前白名单：SET_LED + SEND_NOTIFY
bool IsKnownOperation(const char* op) {
    return strcmp(op, "SET_LED") == 0 || strcmp(op, "SEND_NOTIFY") == 0;
}

std::string MakeSessionId() {
    uint8_t raw[16];
    esp_fill_random(raw, sizeof(raw));
    char buf[37];
    snprintf(buf, sizeof(buf),
             "%02x%02x%02x%02x-%02x%02x-%02x%02x-%02x%02x-%02x%02x%02x%02x%02x%02x",
             raw[0], raw[1], raw[2], raw[3], raw[4], raw[5], raw[6], raw[7],
             raw[8], raw[9], raw[10], raw[11], raw[12], raw[13], raw[14], raw[15]);
    return std::string(buf);
}

}  // namespace

YhProtocol::YhProtocol() {
    // 服务器 DeviceHello.validate() 拒绝含 ': / @' 等传输层地址特征的
    // device_id（MAC 冒号格式会被判为地址直接拒绝），使用去冒号 MAC +
    // 业务前缀：稳定（重启不变）、通过校验。
    std::string mac = SystemInfo::GetMacAddress();  // "aa:bb:cc:dd:ee:ff"
    std::string compact;
    compact.reserve(mac.size());
    for (char c : mac) {
        if (c != ':') {
            compact += c;
        }
    }
    device_id_ = "xiaozhi-" + compact;
}

YhProtocol::~YhProtocol() {
    Stop();
}

YhProtocol& YhProtocol::GetInstance() {
    static YhProtocol instance;
    return instance;
}

// ---------------------------------------------------------------------------
// 生命周期
// ---------------------------------------------------------------------------

void YhProtocol::Start() {
    if (started_) {
        return;
    }
    started_ = true;
    ESP_LOGI(TAG, "started (server=%s:%d)", CONFIG_YH_SERVER_HOST, CONFIG_YH_SERVER_PORT);
    ScheduleReconnect();
}

void YhProtocol::Stop() {
    if (!started_) {
        return;
    }
    started_ = false;
    ESP_LOGI(TAG, "stopped");
    if (reconnect_timer_ != nullptr) {
        esp_timer_stop((esp_timer_handle_t)reconnect_timer_);
    }
    if (heartbeat_timer_ != nullptr) {
        esp_timer_stop((esp_timer_handle_t)heartbeat_timer_);
    }
    Disconnect();
}

// ---------------------------------------------------------------------------
// 连接管理（esp_timer 回调上下文，禁止长阻塞）
// ---------------------------------------------------------------------------

void YhProtocol::ScheduleReconnect() {
    if (!started_ || state_ == State::kConnecting || state_ == State::kOnline) {
        return;
    }
    // 指数退避：首次 1s，失败后翻倍，封顶 60s（连接成功时重置）
    if (reconnect_delay_ms_ < kReconnectMinDelayMs) {
        reconnect_delay_ms_ = kReconnectMinDelayMs;
    } else {
        reconnect_delay_ms_ = reconnect_delay_ms_ * 2;
        if (reconnect_delay_ms_ > kReconnectMaxDelayMs) {
            reconnect_delay_ms_ = kReconnectMaxDelayMs;
        }
    }
    state_ = State::kBackoff;
    ESP_LOGI(TAG, "========================================");
    ESP_LOGI(TAG, "  retry in %d s (backoff)", reconnect_delay_ms_ / 1000);
    ESP_LOGI(TAG, "========================================");
    if (reconnect_timer_ == nullptr) {
        esp_timer_create_args_t args = {
            .callback = [](void* arg) { static_cast<YhProtocol*>(arg)->Connect(); },
            .arg = this,
            .dispatch_method = ESP_TIMER_TASK,
            .name = "yh_reconnect",
            .skip_unhandled_events = true,
        };
        ESP_ERROR_CHECK(esp_timer_create(&args, (esp_timer_handle_t*)&reconnect_timer_));
    }
    esp_timer_start_once((esp_timer_handle_t)reconnect_timer_, reconnect_delay_ms_ * 1000ULL);
}

void YhProtocol::Connect() {
    if (!started_ || state_ == State::kOnline) {
        return;
    }
    state_ = State::kConnecting;
    ESP_LOGI(TAG, "TCP connecting to %s:%d ...", CONFIG_YH_SERVER_HOST, CONFIG_YH_SERVER_PORT);

    if (tcp_ == nullptr) {
        tcp_ = Board::GetInstance().GetNetwork()->CreateTcp().release();
    }
    auto* tcp = static_cast<Tcp*>(tcp_);
    tcp->OnStream([this](const std::string& data) { OnStreamData(data); });
    tcp->OnDisconnected([this]() {
        ESP_LOGW(TAG, "!!! SERVER CLOSED CONNECTION -> will reconnect");
        Disconnect();
        ScheduleReconnect();
    });

    auto result = tcp->Connect(CONFIG_YH_SERVER_HOST, CONFIG_YH_SERVER_PORT);
    if (!result) {
        ESP_LOGE(TAG, "##### SERVER UNREACHABLE #####");
        ESP_LOGE(TAG, "# %s:%d -> %s", CONFIG_YH_SERVER_HOST, CONFIG_YH_SERVER_PORT,
                 result.error().Message());
        ESP_LOGE(TAG, "##############################");
        Disconnect();
        ScheduleReconnect();
        return;
    }

    // 连接成功 -> 新会话 + 重置退避
    session_id_ = MakeSessionId();
    reconnect_delay_ms_ = 0;
    state_ = State::kOnline;
    ESP_LOGI(TAG, "********************************");
    ESP_LOGI(TAG, "* YH ONLINE: %s", device_id_.c_str());
    ESP_LOGI(TAG, "* session: %s", session_id_.c_str());
    ESP_LOGI(TAG, "********************************");

    // HELLO
    auto hello = CJsonUniquePtr(cJSON_CreateObject());
    cJSON_AddStringToObject(hello.get(), "type", "HELLO");
    cJSON_AddNumberToObject(hello.get(), "protocol_version", kProtocolVersion);
    cJSON_AddStringToObject(hello.get(), "device_id", device_id_.c_str());
    cJSON_AddStringToObject(hello.get(), "firmware",
                            esp_app_get_description()->version);
    cJSON_AddStringToObject(hello.get(), "session_id", session_id_.c_str());
    if (!SendJson(hello.get())) {
        return;
    }
    ESP_LOGI(TAG, ">>> HELLO sent");

    // ADVERTISEMENT
    auto adv = CJsonUniquePtr(cJSON_CreateObject());
    cJSON_AddStringToObject(adv.get(), "type", "ADVERTISEMENT");
    cJSON_AddNumberToObject(adv.get(), "protocol_version", kProtocolVersion);
    cJSON_AddStringToObject(adv.get(), "device_id", device_id_.c_str());
    auto* ops = cJSON_AddArrayToObject(adv.get(), "operations");
    cJSON_AddItemToArray(ops, cJSON_CreateString("SET_LED"));
    cJSON_AddItemToArray(ops, cJSON_CreateString("SEND_NOTIFY"));
    if (!SendJson(adv.get())) {
        return;
    }
    ESP_LOGI(TAG, ">>> ADVERTISEMENT sent [SET_LED, SEND_NOTIFY]");

    // HEARTBEAT 定时器（30s）
    if (heartbeat_timer_ == nullptr) {
        esp_timer_create_args_t args = {
            .callback = [](void* arg) { static_cast<YhProtocol*>(arg)->SendHeartbeat(); },
            .arg = this,
            .dispatch_method = ESP_TIMER_TASK,
            .name = "yh_heartbeat",
            .skip_unhandled_events = true,
        };
        ESP_ERROR_CHECK(esp_timer_create(&args, (esp_timer_handle_t*)&heartbeat_timer_));
    }
    esp_timer_start_periodic((esp_timer_handle_t)heartbeat_timer_,
                             kHeartbeatIntervalMs * 1000ULL);
}

void YhProtocol::Disconnect() {
    if (tcp_ != nullptr) {
        auto* tcp = static_cast<Tcp*>(tcp_);
        tcp->Disconnect();
        delete tcp;
        tcp_ = nullptr;
    }
    if (heartbeat_timer_ != nullptr) {
        esp_timer_stop((esp_timer_handle_t)heartbeat_timer_);
    }
    rx_buffer_.clear();
    if (state_ == State::kOnline || state_ == State::kConnecting) {
        state_ = State::kIdle;
    }
}

// ---------------------------------------------------------------------------
// 发送
// ---------------------------------------------------------------------------

bool YhProtocol::SendJson(cJSON* root) {
    if (tcp_ == nullptr || state_ != State::kOnline) {
        return false;
    }
    CJsonStringUniquePtr payload(cJSON_PrintUnformatted(root));
    if (payload == nullptr) {
        return false;
    }
    std::string line(payload.get());
    line += '\n';
    auto* tcp = static_cast<Tcp*>(tcp_);
    int sent = tcp->Send(line);
    if (sent < 0) {
        ESP_LOGE(TAG, "[ERR] send failed (errno=%d)", -sent);
        Disconnect();
        ScheduleReconnect();
        return false;
    }
    return true;
}

// ---------------------------------------------------------------------------
// 入站：newline 分帧（处理半包/粘包/空行/超长）
// ---------------------------------------------------------------------------

void YhProtocol::OnStreamData(const std::string& data) {
    rx_buffer_ += data;

    size_t pos = 0;
    while (true) {
        size_t nl = rx_buffer_.find('\n', pos);
        if (nl == std::string::npos) {
            break;
        }
        std::string frame = rx_buffer_.substr(pos, nl - pos);
        pos = nl + 1;

        // 去除行尾 \r（容忍 CRLF）
        if (!frame.empty() && frame.back() == '\r') {
            frame.pop_back();
        }
        if (frame.empty()) {
            continue;  // 空行
        }
        HandleFrame(frame);
    }
    rx_buffer_.erase(0, pos);

    // 超长拒绝：分帧后残留仍超限 -> 恶意数据，断开
    if (rx_buffer_.size() > kMaxFrameSize) {
        ESP_LOGE(TAG, "[ERR] INVALID_MESSAGE: oversized packet (%u bytes)",
                 (unsigned)rx_buffer_.size());
        Disconnect();
        ScheduleReconnect();
    }
}

void YhProtocol::HandleFrame(const std::string& frame) {
    if (frame.size() > kMaxFrameSize) {
        // 超长帧：单帧拒绝 + NACK，连接保留（恶意持续超长由
        // OnStreamData 的累计缓冲上限兜底断开，这里只管本帧）。
        ESP_LOGE(TAG, "[ERR] INVALID_MESSAGE: oversized frame");
        SendMalformedNack();
        return;
    }

    CJsonUniquePtr root(cJSON_ParseWithLength(frame.c_str(), frame.size()));
    if (root == nullptr) {
        // malformed JSON = 协议层错误，不是传输错误：
        // NACK(MALFORMED_MESSAGE) 后继续收下一帧，绝不 Disconnect。
        ESP_LOGE(TAG, "[ERR] INVALID_MESSAGE: malformed JSON -> NACK, keep session");
        SendMalformedNack();
        return;
    }
    if (!cJSON_IsObject(root.get())) {
        ESP_LOGE(TAG, "[ERR] INVALID_MESSAGE: not a JSON object -> NACK, keep session");
        SendMalformedNack();
        return;
    }

    const cJSON* type = cJSON_GetObjectItem(root.get(), "type");
    if (!cJSON_IsString(type)) {
        ESP_LOGE(TAG, "[ERR] INVALID_MESSAGE: missing type -> NACK, keep session");
        SendMalformedNack();
        return;
    }

    if (strcmp(type->valuestring, "COMMAND") == 0) {
        HandleCommand(root.get());
    } else {
        ESP_LOGE(TAG, "[ERR] INVALID_MESSAGE: unknown message type \"%s\" -> NACK, keep session",
                 type->valuestring);
        SendMalformedNack();
    }
}

// ---------------------------------------------------------------------------
// COMMAND：严格校验 + 白名单 + 幂等 + ACK
// ---------------------------------------------------------------------------

void YhProtocol::HandleCommand(cJSON* root) {
    // protocol_version 必须为 1
    const cJSON* version = cJSON_GetObjectItem(root, "protocol_version");
    if (!cJSON_IsNumber(version) || version->valueint != kProtocolVersion) {
        ESP_LOGE(TAG, "[ERR] INVALID_VERSION");
        SendCommandAck(root, false, kErrInvalidVersion);
        return;
    }

    const cJSON* device = cJSON_GetObjectItem(root, "device_id");
    const cJSON* cmd_id = cJSON_GetObjectItem(root, "command_id");
    const cJSON* op = cJSON_GetObjectItem(root, "operation");
    const cJSON* params = cJSON_GetObjectItem(root, "parameters");

    // 缺字段
    if (!cJSON_IsString(device) || !cJSON_IsString(cmd_id) || !cJSON_IsString(op)) {
        ESP_LOGE(TAG, "[ERR] INVALID_PARAMETERS: missing required field");
        SendCommandAck(root, false, kErrInvalidParameters);
        return;
    }

    // 错误设备
    if (device_id_ != device->valuestring) {
        ESP_LOGE(TAG, "[ERR] WRONG_DEVICE: \"%s\"", device->valuestring);
        SendCommandAck(root, false, kErrWrongDevice);
        return;
    }

    // 未知 operation（白名单外）
    if (!IsKnownOperation(op->valuestring)) {
        ESP_LOGE(TAG, "[ERR] UNKNOWN_COMMAND: \"%s\"", op->valuestring);
        SendCommandAck(root, false, kErrUnknownCommand);
        return;
    }

    // SEND_NOTIFY 是"播放通知"：Application::NotifyAudio 在非 idle 时静默丢弃。
    // 必须在幂等登记前按状态拒绝，否则 busy 的 command_id 会被记入去重表，
    // 服务端重试同一 id 会命中 DUPLICATE_COMMAND 而被误判为已执行（AC-14）。
    if (strcmp(op->valuestring, "SEND_NOTIFY") == 0 &&
        Application::GetInstance().GetDeviceState() != kDeviceStateIdle) {
        ESP_LOGW(TAG, "<<< COMMAND SEND_NOTIFY [%s] rejected: device busy (state=%d)",
                 cmd_id->valuestring, (int)Application::GetInstance().GetDeviceState());
        SendCommandAck(root, false, kErrBusy);
        return;
    }

    // 幂等：重复 command_id 不执行
    if (IsDuplicateCommand(cmd_id->valuestring)) {
        ESP_LOGE(TAG, "[ERR] DUPLICATE_COMMAND: %s", cmd_id->valuestring);
        SendCommandAck(root, false, kErrDuplicateCommand);
        return;
    }

    // SET_LED 参数 schema：parameters 必须存在且只含 boolean "on"
    if (strcmp(op->valuestring, "SET_LED") == 0) {
        bool on;
        bool ok = false;
        if (cJSON_IsObject(params)) {
            // additionalProperties = false：对象必须恰好只有 "on" 一个键
            bool only_on = (cJSON_GetArraySize(params) == 1);
            const cJSON* on_item = cJSON_GetObjectItem(params, "on");
            if (only_on && cJSON_IsBool(on_item)) {
                on = cJSON_IsTrue(on_item);
                ok = true;
            }
        }
        if (!ok) {
            ESP_LOGE(TAG, "[ERR] INVALID_PARAMETERS: SET_LED expects {\"on\": <boolean>}");
            SendCommandAck(root, false, kErrInvalidParameters);
            return;
        }

        ESP_LOGI(TAG, "<<< COMMAND SET_LED [%s]", cmd_id->valuestring);
        ExecuteSetLed(on);
        ESP_LOGI(TAG, "    -> LED %s (GPIO48 WS2812)", on ? "ON ***" : "OFF");
        SendCommandAck(root, true, kErrNone);
    } else if (strcmp(op->valuestring, "SEND_NOTIFY") == 0) {
        // params 必须存在且为 object，含 string "audio_url"，可选 string "text"
        if (!cJSON_IsObject(params) || cJSON_GetObjectItem(params, "audio_url") == nullptr) {
            ESP_LOGE(TAG, "[ERR] INVALID_PARAMETERS: SEND_NOTIFY requires {\"audio_url\": <string>}");
            SendCommandAck(root, false, kErrInvalidParameters);
            return;
        }
        const char* audio_url = cJSON_GetObjectItem(params, "audio_url")->valuestring;
        const cJSON* text_item = cJSON_GetObjectItem(params, "text");
        std::string text = cJSON_IsString(text_item) ? text_item->valuestring : "";
        ESP_LOGI(TAG, "<<< COMMAND SEND_NOTIFY [%s] url=%s", cmd_id->valuestring, audio_url);
        Application::GetInstance().Schedule([audio_url, text]() {
            std::vector<NotifySubtitle> subtitles;
            if (!text.empty()) {
                NotifySubtitle sub;
                sub.text = text;
                subtitles.push_back(sub);
            }
            Application::GetInstance().NotifyAudio(audio_url, subtitles);
        });
        SendCommandAck(root, true, kErrNone);
    }
}

// ---------------------------------------------------------------------------
// ACK / HEARTBEAT / 幂等缓存
// ---------------------------------------------------------------------------

// ---------------------------------------------------------------------------
// NACK(MALFORMED_MESSAGE)：envelope 级错误，command_id 合法留空
// （服务器 DeviceAck._ENVELOPE_LEVEL_ERRORS 允许空 command_id）。
// 只在 Online 状态发送；发送失败按既有 SendJson 语义触发重连。
// ---------------------------------------------------------------------------
void YhProtocol::SendMalformedNack() {
    auto nack = CJsonUniquePtr(cJSON_CreateObject());
    cJSON_AddStringToObject(nack.get(), "type", "NACK");
    cJSON_AddNumberToObject(nack.get(), "protocol_version", kProtocolVersion);
    cJSON_AddStringToObject(nack.get(), "device_id", device_id_.c_str());
    cJSON_AddStringToObject(nack.get(), "status", "NACK");
    cJSON_AddStringToObject(nack.get(), "error_code", kErrMalformedMessage);
    cJSON_AddStringToObject(nack.get(), "command_id", "");
    SendJson(nack.get());
    ESP_LOGI(TAG, ">>> NACK NACKED [%s] (session kept)", kErrMalformedMessage);
}

void YhProtocol::SendCommandAck(cJSON* cmd, bool ok, const char* error_code) {
    auto ack = CJsonUniquePtr(cJSON_CreateObject());
    cJSON_AddStringToObject(ack.get(), "type", "ACK");
    cJSON_AddNumberToObject(ack.get(), "protocol_version", kProtocolVersion);
    cJSON_AddStringToObject(ack.get(), "status", ok ? "ACKED" : "NACKED");
    cJSON_AddStringToObject(ack.get(), "error_code", error_code);

    // 回显 command_id / device_id（原消息可能缺字段，尽力回显）
    const cJSON* cmd_id = cJSON_GetObjectItem(cmd, "command_id");
    if (cJSON_IsString(cmd_id)) {
        cJSON_AddStringToObject(ack.get(), "command_id", cmd_id->valuestring);
    }
    const cJSON* device = cJSON_GetObjectItem(cmd, "device_id");
    if (cJSON_IsString(device)) {
        cJSON_AddStringToObject(ack.get(), "device_id", device->valuestring);
    } else {
        cJSON_AddStringToObject(ack.get(), "device_id", device_id_.c_str());
    }

    SendJson(ack.get());
    ESP_LOGI(TAG, ">>> ACK %s [%s]", ok ? "ACKED (ok)" : "NACKED (rejected)", error_code);
}

void YhProtocol::SendHeartbeat() {
    if (state_ != State::kOnline || tcp_ == nullptr) {
        return;
    }
    auto hb = CJsonUniquePtr(cJSON_CreateObject());
    cJSON_AddStringToObject(hb.get(), "type", "HEARTBEAT");
    cJSON_AddNumberToObject(hb.get(), "protocol_version", kProtocolVersion);
    cJSON_AddStringToObject(hb.get(), "device_id", device_id_.c_str());
    cJSON_AddStringToObject(hb.get(), "session_id", session_id_.c_str());
    if (SendJson(hb.get())) {
        ESP_LOGI(TAG, "hb ^ (keep-alive 25s)");
    }
}

bool YhProtocol::IsDuplicateCommand(const std::string& command_id) {
    for (int i = 0; i < kCommandCacheSize; i++) {
        if (command_cache_[i] == command_id) {
            return true;
        }
    }
    command_cache_[cache_next_] = command_id;
    cache_next_ = (cache_next_ + 1) % kCommandCacheSize;
    return false;
}

// ---------------------------------------------------------------------------
// SET_LED：YH LED 适配层 -> 现有 WS2812 驱动
// ---------------------------------------------------------------------------

void YhProtocol::ExecuteSetLed(bool on) {
    // 协议代码不直接操作 GPIO；通过 Board 桥接到真实 WS2812 驱动。
    auto* led = Board::GetInstance().GetWs2812Led();
    if (led != nullptr) {
        led->SetYhLed(on);
    } else {
        ESP_LOGW(TAG, "no WS2812 on this board, SET_LED ignored at hardware level");
    }
    led_state_ = on;
}

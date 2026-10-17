#ifndef YH_PROTOCOL_H
#define YH_PROTOCOL_H

#include <cstdint>
#include <mutex>
#include <string>

// YH Device Protocol v1 适配层。
//
// 职责边界：小智固件 <-> 屿禾工坊服务器 (TCP :12399, newline-delimited JSON)。
// 小智原有 AI / ASR / TTS / WebSocket / MQTT / OTA 通道完全不受影响，
// 本模块是独立的旁路设备管理通道（见 docs/Xiaozhi-YH-通信架构审计报告.md）。
//
// 消息类型: HELLO / ADVERTISEMENT / HEARTBEAT / COMMAND / ACK
// 传输: Board::GetNetwork()->CreateTcp() (EspTcp, 自带接收任务)
// 生命周期: 网络就绪后连接; 升级/断网时断开; 指数退避重连, 新 session_id。

class YhProtocol {
public:
    static YhProtocol& GetInstance();

    // 网络就绪后调用（WiFi 已连接）。幂等：已启动则忽略。
    void Start();
    // 立即断开并停止重连（OTA 升级 / 深度逻辑需要时调用）。
    void Stop();

    // 壁纸执行结果回执（SET_WALLPAPER 异步下载/应用完成后调用）。
    // 走本通道（TCP 12399，常连）而非 WS：设备空闲时 WS 不保持，只有本通道在线。
    // 线程安全：可从壁纸后台任务上下文调用（内部加锁；失败只记日志不触发重连）。
    void SendWallpaperResult(const std::string& version, bool ok, const std::string& reason);

private:
    YhProtocol();
    ~YhProtocol();
    YhProtocol(const YhProtocol&) = delete;
    YhProtocol& operator=(const YhProtocol&) = delete;

    // ---- 状态机 ----
    enum class State {
        kIdle,          // 未启动
        kBackoff,       // 等待重连定时器
        kConnecting,    // 正在拨号
        kOnline,        // 已连接（HELLO/ADVERTISEMENT 已发）
    };

    // ---- 连接管理（esp_timer 回调上下文） ----
    void ScheduleReconnect();          // 安排下一次连接尝试
    void Connect();                    // 建连 + HELLO + ADVERTISEMENT
    void Disconnect();                 // 断开（不改变退避状态）
    void SendHeartbeat();
    void SendCommandAck(class cJSON* cmd, bool ok, const char* error_code);
    void SendMalformedNack();
    void ExecuteSetLed(bool on);

    // ---- 发送 ----
    bool SendJson(class cJSON* root);  // 序列化 + '\n' + Send；失败触发重连
    std::mutex send_mutex_;            // 保护 tcp_->Send：RECV 任务与壁纸任务并发调用

    // ---- 入站处理（EspTcp 接收任务上下文） ----
    void OnStreamData(const std::string& data);   // 累积 + '\n' 分帧
    void HandleFrame(const std::string& frame);   // 单条完整 JSON
    void HandleCommand(class cJSON* root);        // COMMAND 校验 + 执行 + ACK

    // ---- 幂等缓存（64 槽环形，RAM-only） ----
    static constexpr int kCommandCacheSize = 64;
    bool IsDuplicateCommand(const std::string& command_id);
    std::string command_cache_[kCommandCacheSize];
    int cache_next_ = 0;

    // ---- 成员 ----
    State state_ = State::kIdle;
    std::string device_id_;
    std::string session_id_;
    std::string rx_buffer_;
    int reconnect_delay_ms_ = 0;
    void* reconnect_timer_ = nullptr;   // esp_timer_handle_t
    void* heartbeat_timer_ = nullptr;   // esp_timer_handle_t
    void* tcp_ = nullptr;               // std::unique_ptr<Tcp>
    bool led_state_ = false;
    bool started_ = false;
};

#endif  // YH_PROTOCOL_H

# 小智 ESP32 固件代码修改思路梳理

> 生成时间：2026-10-11
> 路径基准：`G:\demo\21_xiaozhi\code\small_secreen\xiaozhi-esp32`
> 分析范围：固件侧 + 服务端（概要）

---

## 一、唤醒词参数动态下发

### 现状（已实现）

**关键流程：**
1. `application.cc:776-821` — 处理 `device_config` 消息类型，调用 `Board::GetInstance().ApplyDeviceConfig(payload)`
2. `board.cc:172-300` — `ApplyDeviceConfig()` 解析 `wake_word` 字段（字符串或数组），通过 `HanziToPinyin()` 转拼音，再调用 `audio.UpdateWakeWordCommands()`
3. `audio_service.h/cc` — 缓存 pending wake word（引擎未就绪时）
4. `custom_wake_word.cc:219-297` — `UpdateCommands()` 重建 MultiNet 命令表并持久化 NVS
5. `custom_wake_word.cc:299-353` — `ClearWakeWordCommands()` 恢复默认并清 NVS

**当前 device_config JSON 结构（已支持）：**
```json
{
  "volume": 50,
  "brightness": 80,
  "wake_word": ["你好小禾", "小禾你好"]
}
```

### 扩展方案

**需要修改的文件：**
| 文件 | 角色 |
|---|---|
| `main/boards/common/board.cc:172` | `ApplyDeviceConfig()` 扩展点 |
| `main/audio/audio_service.h` | 新增持久化字段（可选） |
| `main/audio/wake_words/custom_wake_word.h` | 新增参数接口（可选） |

**需要新增的字段（建议）：**
```json
{
  "wake_word": ["你好小禾"],
  "wake_word_threshold": 75,
  "wake_word_duration": 2000
}
```

**伪代码思路（board.cc ApplyDeviceConfig 扩展）：**
```cpp
// 在 wake_word 处理分支之后增加
auto threshold = cJSON_GetObjectItem(payload, "wake_word_threshold");
if (cJSON_IsNumber(threshold)) {
    int t = threshold->valueint;
    if (t >= 1 && t <= 100) {
        Settings settings("wake_word_config", true);
        settings.SetInt("threshold", t);
        // 下次引擎初始化时读取；或热更新（需 AudioEngine 暴露接口）
    }
}

auto duration = cJSON_GetObjectItem(payload, "wake_word_duration");
if (cJSON_IsNumber(duration)) {
    int d = duration->valueint;
    if (d >= 500 && d <= 5000) {
        Settings settings("wake_word_config", true);
        settings.SetInt("duration", d);
    }
}
```

**与其他模块依赖：**
- `custom_wake_word.cc:Initialize()` 第 96 行读取 `CONFIG_CUSTOM_WAKE_WORD_THRESHOLD`，可改为优先读 NVS
- 需在 `AudioService::InitializeAudioEngine()` 中读取 NVS 阈值，设置到 Multinet
- **可选优化**：热更新阈值（不重启），需在 `custom_wake_word.h` 暴露 `SetThreshold()` 接口

**坑和注意事项：**
- `HanziToPinyin()` 的映射表 `board.cc:26-79` 覆盖范围有限，未收录字会丢弃该词（不是整批丢弃）
- NVS 持久化键名是持久 API，改键名需迁移逻辑
- 带声调数字的旧拼音（如 `"ni3 hao3"`）已被 NVS 自愈逻辑丢弃，无需额外兼容

---

## 二、UDP 通信（配置更新 + 心跳）

### 现状分析

**已有 UDP 能力：**
- `board.h:8` — 已 include `<udp.h>`，`NetworkInterface` 暴露了 `CreateUdp(int priority)` 接口
- `mqtt_protocol.cc` — 已有 UDP 实现（用于音频传输），可参考其模式
- `yh_protocol.cc` — 使用 TCP 长连接，已有心跳机制（25s 间隔）

**WebSocket 协议侧（当前无 UDP）：**
- `websocket_protocol.cc` — 仅 WebSocket，无 UDP 通道
- `application.cc:99-243` — `OpenAudioChannel()` 只创建 WebSocket

### 设计方案

**场景 A：复用 YH 旁路通道**（推荐，改动最小）
YH 协议已有 TCP 长连接和心跳，UDP 可直接叠加：

```cpp
// yh_protocol.cc 新增成员
std::shared_ptr<Udp> udp_;
esp_timer_handle_t udp_heartbeat_timer_ = nullptr;
```

**修改文件清单：**
| 文件 | 修改内容 |
|---|---|
| `main/yh/yh_protocol.h` | 新增 UDP 成员变量和接口声明 |
| `main/yh/yh_protocol.cc` | Connect() 成功后创建 UDP；新增 UDP 收发包函数；UDP 心跳定时器 |
| `main/application.cc` | 网络断开时同步停止 UDP |

**伪代码思路：**
```cpp
// yh_protocol.cc Connect() 成功后
udp_ = Board::GetInstance().GetNetwork()->CreateUdp(1);
udp_->OnMessage([this](const std::string& data) {
    HandleUdpMessage(data);  // 解析配置/心跳响应
});
udp_->Connect(server_host_, udp_port_);  // 服务器同 IP 不同端口

// 新增 UDP 心跳（独立于 TCP 心跳，防止 NAT 超时）
esp_timer_create_args_t args = {
    .callback = [](void* arg) {
        static_cast<YhProtocol*>(arg)->SendUdpHeartbeat();
    },
    .arg = this, .dispatch_method = ESP_TIMER_TASK,
    .name = "yh_udp_heartbeat", .skip_unhandled_events = true
};
esp_timer_create(&args, &udp_heartbeat_timer_);
esp_timer_start_periodic(udp_heartbeat_timer_, 15 * 1000 * 1000ULL);  // 15s
```

**场景 B：独立 UDP 通道（纯配置/心跳，不依赖 YH）**
如需与 YH 完全解耦，可在 `websocket_protocol.cc` 中新增：
```cpp
bool WebsocketProtocol::OpenUdpChannel() {
    auto network = Board::GetInstance().GetNetwork();
    udp_ = network->CreateUdp(1);
    udp_->OnMessage([this](const std::string& data) {
        ParseUdpConfig(data);  // 解析 device_config
    });
    return udp_->Connect(config.udp_server, config.udp_port);
}
```

### 依赖关系
- 服务端需同步开放 UDP 端口并实现心跳回应
- UDP 端口建议与 WebSocket 分开（如 WS:8001, UDP:8002）

### 坑和注意事项
- **ESP32 UDP 是无连接的**：`Connect()` 只是设定默认对端，仍可收任意来源包；建议加源 IP 校验
- **NAT 超时**：路由器通常 60-300s 无流量会清表，UDP 心跳间隔需 < 30s
- **ML307/NT26 蜂窝网络**：UDP 在运营商 NAT 下可能受限，需验证；WiFi 场景通常没问题
- 心跳间隔与 TCP 心跳错开，避免同时发包造成瞬时带宽峰值

---

## 三、OTA 预留

### 现状（已实现）

**关键文件：**
- `ota.h/cc` — OTA 升级核心逻辑
- `application.cc:510-597` — `CheckNewVersion()` 调用 OTA 检查
- `application.cc:1498-1560` — `UpgradeFirmware()` 执行下载和重启

**当前流程：**
1. `ActivationTask()` 中调用 `CheckNewVersion()`
2. `Ota::CheckVersion()` 请求服务器版本接口
3. 有新版本时调用 `UpgradeFirmware(url, version)`
4. 下载 → 写入 partition → `esp_restart()`

**配置来源：**
- `ota.cc:48-55` — URL 从 NVS key `"wifi"."ota_url"` 读取，fallback 到 `CONFIG_OTA_URL`
- `Kconfig.projbuild` — 编译时默认 OTA URL

### 扩展方案

**需要修改的文件：**
| 文件 | 修改内容 |
|---|---|
| `main/ota.h` | 新增 `GetConfigUrl()` / `CheckConfigVersion()` 接口 |
| `main/ota.cc` | 新增配置版本检查逻辑 |
| `main/application.cc:433-448` | `ActivationTask()` 中增加配置检查步骤 |

**伪代码思路：**
```cpp
// ota.h 新增
class Ota {
public:
    // 检查配置版本（与固件版本分离）
    std::expected<bool, NetworkError> CheckConfigVersion();
    // 获取配置下载 URL
    std::string GetConfigDownloadUrl();
private:
    std::string config_version_;      // 当前配置版本号
    std::string config_download_url_; // 配置下载地址
};

// ota.cc 实现
std::expected<bool, NetworkError> Ota::CheckConfigVersion() {
    auto http = SetupHttp();
    std::string url = GetCheckVersionUrl() + "/config/version";
    // GET /config/version?device_id=xxx&current_version=1.2.3
    auto response = http->Get(url);
    // 解析响应: {"version": "2", "download_url": "http://.../config.zip"}
    auto root = cJSON_Parse(response.c_str());
    config_version_ = cJSON_GetObjectItem(root, "version")->valuestring;
    config_download_url_ = cJSON_GetObjectItem(root, "download_url")->valuestring;
    return config_version_ != current_config_version_;  // 有更新返回 true
}
```

**在 application.cc ActivationTask() 中增加：**
```cpp
void Application::ActivationTask() {
    ota_ = std::make_unique<Ota>();

    // 新增：检查配置版本（在固件版本检查之前）
    auto config_check = ota_->CheckConfigVersion();
    if (config_check && *config_check) {
        DownloadAndApplyConfig(ota_->GetConfigDownloadUrl());
    }

    CheckAssetsVersion();
    CheckNewVersion();
    InitializeProtocol();
    xEventGroupSetBits(event_group_, MAIN_EVENT_ACTIVATION_DONE);
}
```

### 依赖关系
- 服务端需新增 `/ota/config/version` 接口
- 配置文件建议用 zip 格式，包含 `config.json` + 音频资源

### 坑和注意事项
- **NVS 空间限制**：ESP32-S3 的 NVS 分区通常 2-4MB，配置版本字符串不宜过长
- **降级保护**：配置下载失败不应阻塞固件启动，用 `std::expected` 处理错误
- **配置幂等性**：同版本配置重复下发应跳过（对比版本号）
- **与 assets 的关系**：配置 OTA 与 assets OTA 是两套独立机制，避免混淆

---

## 四、随机推送处理

### 现状分析

**现有通知机制：**
- `main/notify/notify_player.cc` — 通知播放核心
- `application.cc:1350-1414` — `StartNotification()` / `StopNotification()`
- `application.cc:664-696` — 处理 `notify` 消息类型（WebSocket 推送）
- `yh_protocol.cc:416-437` — YH 协议的 `SEND_NOTIFY` 命令处理

**当前 notify 消息处理（application.cc:664-696）：**
```cpp
if (strcmp(type->valuestring, "notify") == 0) {
    auto audio_url = cJSON_GetObjectItem(root, "audio_url");
    // ... 解析 subtitles ...
    Schedule([this, url, subtitles]() {
        StartNotification(std::move(url), std::move(subtitles));
    });
}
```

### 随机推送设计方案

**方案：复用现有 notify 机制，新增消息类型标识**

服务器推送随机消息时，在 JSON 中增加 `"priority"` 或 `"push_type"` 字段：

```json
{
  "type": "notify",
  "push_type": "random",  // 新增字段：random/scheduled/urgent
  "audio_url": "http://...",
  "subtitles": [...]
}
```

**需要修改的文件：**
| 文件 | 修改内容 | 优先级 |
|---|---|---|
| `main/application.cc:664` | 解析 `push_type` 字段 | 必须 |
| `main/notify/notify_player.h` | 新增优先级枚举 | 可选 |
| `main/audio/audio_service.h` | 打断策略配置 | 可选 |

**伪代码思路：**
```cpp
// application.cc OnIncomingJson 回调中
} else if (strcmp(type->valuestring, "notify") == 0) {
    auto push_type = cJSON_GetObjectItem(root, "push_type");
    NotifyPriority priority = kNotifyPriorityNormal;
    
    if (cJSON_IsString(push_type)) {
        if (strcmp(push_type->valuestring, "urgent") == 0) {
            priority = kNotifyPriorityUrgent;  // 紧急：立即打断
        } else if (strcmp(push_type->valuestring, "random") == 0) {
            priority = kNotifyPriorityRandom;  // 随机：低优先级
        }
    }
    
    // 根据优先级决定是否打断当前状态
    if (priority == kNotifyPriorityUrgent && 
        GetDeviceState() != kDeviceStateIdle) {
        StopNotification();  // 先停当前播报
    } else if (GetDeviceState() != kDeviceStateIdle) {
        ESP_LOGW(TAG, "Ignoring low-priority notify: device busy");
        return;
    }
    
    // ... 后续解析 audio_url 和 subtitles ...
}
```

**优先级定义（notify_player.h）：**
```cpp
enum class NotifyPriority {
    kNotifyPriorityLow = 0,     // 随机推送，设备忙时丢弃
    kNotifyPriorityNormal = 1,  // 普通通知，排队等待
    kNotifyPriorityUrgent = 2,  // 紧急通知，立即打断
};
```

### 随机推送调度策略

**固件侧行为：**
1. **Idle 状态**：立即播放
2. **Listening 状态**：
   - 紧急推送：打断当前会话，播放通知
   - 普通推送：排队等待
   - 随机推送：丢弃或排队（可配置）
3. **Speaking 状态**：
   - 紧急推送：打断 TTS，播放通知
   - 普通/随机：排队

**服务端调度（概要）：**
- 定时任务： cron 表达式或 Redis Lua 脚本
- 随机选择：按设备标签、在线状态过滤
- 频率控制：同一设备 5 分钟内最多 1 条随机推送

### 依赖关系
- 服务端需要新增推送调度服务
- 客户端需扩展 `NotifyPriority` 枚举（向后兼容：旧消息无 `push_type` 字段时默认为 `Normal`）

### 坑和注意事项
- **打断逻辑**：`StopNotification()` 会清空发送队列，需注意音频数据完整性
- **队列管理**：多条通知排队时，建议用 FIFO，避免长队列导致用户体验差
- **YH 协议兼容性**：YH 的 `SEND_NOTIFY` 命令不考虑优先级，需单独处理

---

## 五、服务端改动概要

### 1. 随机推送调度

**需要新增的 API：**
```
POST /api/v1/push/random
Content-Type: application/json

{
  "device_ids": ["device_001", "device_002"],  // 目标设备（空=全量）
  "content": {
    "type": "notify",
    "push_type": "random",
    "audio_url": "http://...",
    "subtitles": [{"start_ms": 0, "text": "你好"}]
  },
  "schedule": {
    "type": "cron",           // immediate | cron | delayed
    "cron": "0 9,18 * * *",   // 每天 9:00 和 18:00
    "delay_seconds": 300      // 延迟 5 分钟
  },
  "rate_limit": {
    "per_device": 1,          // 每设备最多 N 条
    "window_seconds": 300     // 时间窗口
  }
}
```

**调度器实现建议：**
- 使用 Redis + Lua 脚本保证原子性
- 定时任务用 Celery/Django ORM 的 periodic task
- 推送失败重试：最多 3 次，指数退避

### 2. 唤醒词参数下发

**device_config JSON 结构扩展：**
```json
{
  "version": "1.2.0",
  "volume": 70,
  "brightness": 80,
  "wake_word": ["你好小禾", "小禾你好"],
  "wake_word_threshold": 75,
  "wake_word_duration": 2000,
  "language": "zh-CN",
  "features": {
    "mcp_enabled": true,
    "aec_mode": "server"
  }
}
```

**服务端存储建议：**
- 设备配置存在 `device_config` 表，key 为 `device_id`
- 版本管理：每次下发递增版本号，客户端对比后决定是否更新
- 灰度发布：支持按 `board_type` 或 `firmware_version` 定向下发

### 3. 记忆时间图

**新表设计：**
```sql
-- 记忆条目表
CREATE TABLE memories (
    id BIGINT PRIMARY KEY,
    device_id VARCHAR(64) NOT NULL,
    user_id VARCHAR(64),
    content TEXT NOT NULL,
    memory_type VARCHAR(32),  -- fact | preference | event
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP,
    expires_at TIMESTAMP,
    importance FLOAT DEFAULT 0.5,
    INDEX idx_device_created (device_id, created_at)
);

-- 时间关联表（用于时间图查询）
CREATE TABLE memory_times (
    memory_id BIGINT,
    time_reference VARCHAR(255),  -- "昨天" | "2024-01-01" | "每逢周末"
    actual_date DATE,
    PRIMARY KEY (memory_id, time_reference),
    FOREIGN KEY (memory_id) REFERENCES memories(id) ON DELETE CASCADE
);
```

**查询接口：**
```
GET /api/v1/memories/{device_id}
Query params:
  - from: ISO8601 开始时间
  - to: ISO8601 结束时间
  - type: fact | preference | event
  - limit: 20
  - offset: 0
```

### 4. 实体图谱

**新表设计：**
```sql
-- 实体表
CREATE TABLE entities (
    id BIGINT PRIMARY KEY,
    device_id VARCHAR(64) NOT NULL,
    name VARCHAR(255) NOT NULL,
    entity_type VARCHAR(32),  -- person | object | location | concept
    metadata JSON,            -- LLM 提取的额外属性
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_device_type (device_id, entity_type)
);

-- 关系表
CREATE TABLE relations (
    id BIGINT PRIMARY KEY,
    device_id VARCHAR(64) NOT NULL,
    subject_id BIGINT NOT NULL,
    predicate VARCHAR(255) NOT NULL,
    object_id BIGINT NOT NULL,
    confidence FLOAT DEFAULT 0.8,
    source_memory_id BIGINT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (subject_id) REFERENCES entities(id),
    FOREIGN KEY (object_id) REFERENCES entities(id),
    FOREIGN KEY (source_memory_id) REFERENCES memories(id)
);
```

**LLM 提取接口：**
```
POST /api/v1/llm/extract-entities
Content-Type: application/json

{
  "device_id": "xxx",
  "text": "小明喜欢听音乐，他昨天买了个新音箱",
  "language": "zh-CN"
}

Response:
{
  "entities": [
    {"name": "小明", "type": "person", "confidence": 0.95},
    {"name": "音乐", "type": "concept", "confidence": 0.88},
    {"name": "音箱", "type": "object", "confidence": 0.92}
  ],
  "relations": [
    {"subject": "小明", "predicate": "likes", "object": "音乐"},
    {"subject": "小明", "predicate": "bought", "object": "音箱"}
  ]
}
```

### 5. 一键导入 LLM 分析

**API 设计：**
```
POST /api/v1/llm/analyze-memory
Content-Type: application/json

{
  "device_id": "xxx",
  "text": "用户说喜欢听古典音乐，尤其是莫扎特",
  "context": {
    "conversation_id": "conv_123",
    "timestamp": "2024-01-15T10:30:00Z"
  }
}

Response:
{
  "success": true,
  "memory": {
    "id": 12345,
    "content": "用户喜欢古典音乐，尤其是莫扎特",
    "type": "preference",
    "entities": ["古典音乐", "莫扎特"],
    "importance": 0.7,
    "expires_at": null
  },
  "actions": {
    "updated_entities": ["莫扎特"],
    "new_relations": [
      {"subject": "用户", "predicate": "likes", "object": "莫扎特"}
    ]
  }
}
```

**批量导入接口：**
```
POST /api/v1/llm/batch-analyze
Content-Type: application/json

{
  "device_id": "xxx",
  "conversations": [
    {"id": "conv_1", "text": "..."},
    {"id": "conv_2", "text": "..."}
  ],
  "options": {
    "max_memories_per_conv": 5,
    "min_importance": 0.3
  }
}
```

### 6. 微信 OpenClaw 接入

**架构建议：**
```
┌─────────────┐     ┌──────────────┐     ┌─────────────┐
│  微信客户端  │────▶│  OpenClaw    │────▶│  小智网关    │
│  (小程序/H5) │     │  网关服务    │     │  (新增)      │
└─────────────┘     └──────────────┘     └─────────────┘
                                           │
                                           ▼
                                    ┌─────────────┐
                                    │  小智服务器  │
                                    │  (现有)      │
                                    └─────────────┘
```

**需要新增的组件：**
1. **OpenClaw 网关服务**（独立部署）
   - 鉴权：微信 OpenID → 小智 device_id 映射
   - 消息转发：微信消息 → 小智协议
   - 状态同步：小智状态 → 微信推送

2. **数据库表：**
```sql
CREATE TABLE wechat_bindings (
    id BIGINT PRIMARY KEY,
    openid VARCHAR(128) NOT NULL,
    device_id VARCHAR(64) NOT NULL,
    bound_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_active_at TIMESTAMP,
    UNIQUE KEY uk_openid (openid),
    INDEX idx_device (device_id)
);
```

3. **API 接口：**
```
POST /api/v1/wechat/bind
{
  "openid": "oXXXX",
  "device_id": "xiaozhi-xxx"
}

GET /api/v1/wechat/device/{device_id}/status
→ {"state": "idle", "wake_word": "你好小禾"}

POST /api/v1/wechat/device/{device_id}/command
{
  "command": "wake_word_invoke",
  "params": {"wake_word": "你好小禾"}
}
```

---

## 六、实施顺序建议

### Phase 1：基础能力建设（1-2 周）
- [ ] 唤醒词参数动态下发（服务端 JSON 扩展 + 客户端解析）
- [ ] UDP 通信通道（配置更新 + 心跳）
- [ ] OTA 配置版本检查

**并行度**：三项可并行开发，服务端接口先定契约

### Phase 2：消息系统增强（1 周）
- [ ] 随机推送优先级处理
- [ ] 服务端推送调度器
- [ ] 通知队列管理

### Phase 3：AI 能力集成（2-3 周）
- [ ] 记忆时间图表设计 + 接口
- [ ] 实体图谱表设计 + LLM 提取接口
- [ ] 一键导入分析接口

### Phase 4：微信接入（1-2 周）
- [ ] OpenClaw 网关服务搭建
- [ ] 微信绑定流程
- [ ] 状态同步与远程控制

---

## 七、关键风险点

| 风险 | 影响 | 缓解措施 |
|---|---|---|
| UDP 在蜂窝网络受限 | 配置更新失败 | 保留 WebSocket 作为 fallback |
| NVS 空间不足 | 唤醒词缓存丢失 | 监控 NVS 使用率，超限告警 |
| 随机推送频率过高 | 用户体验差 | 服务端频率限制 + 客户端忽略策略 |
| LLM 提取准确率 | 记忆质量差 | 人工审核入口 + 重要性阈值 |
| 微信绑定安全 | 设备被盗用 | OpenID 校验 + 设备解绑流程 |

---

## 八、附录：关键文件索引

| 功能 | 关键文件 | 行号范围 |
|---|---|---|
| 唤醒词动态下发 | `main/boards/common/board.cc` | 172-300 |
| 唤醒词引擎 | `main/audio/wake_words/custom_wake_word.cc` | 219-353 |
| device_config 处理 | `main/application.cc` | 776-821 |
| UDP 参考实现 | `main/protocols/mqtt_protocol.cc` | 全文件 |
| 通知播放 | `main/notify/notify_player.cc` | 全文件 |
| OTA 升级 | `main/ota.h/cc` | 全文件 |
| YH 协议心跳 | `main/yh/yh_protocol.cc` | 28-36, 484-496 |


# 小智 ESP32 固件 — 需求文档

> 路径：`G:/demo/21_xiaozhi/code/small_secreen/yuhe-esp32`
> 生成日期：2026-10-11
> 范围：固件侧（ESP-IDF/ESP32-S3）+ 服务端（含 Web 管理后台）

---

## 目录

1. [功能概述](#1-功能概述)
2. [详细需求描述](#2-详细需求描述)
3. [数据模型设计](#3-数据模型设计)
4. [接口设计](#4-接口设计)
5. [实施优先级建议](#5-实施优先级建议)
6. [风险与注意事项](#6-风险与注意事项)

---

## 1. 功能概述

| # | 功能 | 背景 | 价值 |
|---|------|------|------|
| 1 | 随机推送发聊天 | 当前设备完全被动，用户需要主动唤醒才能交互 | 提升设备"陪伴感"，像智能音箱一样主动关心 |
| 2 | 唤醒词参数服务器下发 | 灵敏度/VAD/AEC 等参数写死在 sdkconfig，修改需重新烧录 | 可按环境动态调整，支持 A/B 测试 |
| 3 | OTA 升级地址动态获取 | 当前 OTA URL 硬编码，版本回滚依赖手动策略 | 支持灰度发布和故障自动回滚 |
| 4 | 硬件通信走 UDP | 当前控制信令走 WebSocket，心跳和数据开销偏大 | UDP 轻量、低延迟，适合频繁心跳和配置同步 |
| 5 | 记忆时间图 | 对话历史无时间维度展示 | 用户可快速了解"什么时间说了什么" |
| 6 | 实体图谱优化 | 当前图谱质量差，节点关系混乱 | 基于 LLM 提取的精准实体关系图谱 |
| 7 | 记忆一键导入 | 用户手动逐条录入记忆成本高 | LLM 自动分析文本，批量导入到记忆库 |
| 8 | 接入微信 OpenClaw | 设备仅能通过语音交互，缺乏移动端触达能力 | 用户可通过微信与设备双向通信 |

---

## 2. 详细需求描述

### 2.1 随机推送发聊天

**背景**：当前设备完全被动响应，用户必须主动唤醒才能交互。类似智能音箱的"主动关心"功能可提升陪伴感。

**需求**：
- 服务器按随机间隔（如 5-30 分钟）向在线设备推送一条闲聊消息
- 消息内容包含文本 + TTS 音频 URL + 可选字幕
- 推送优先级低于用户唤醒，设备非空闲时丢弃或排队
- 支持配置推送频率、时段（如夜间静音）

**约束**：
- 同一设备 5 分钟内最多 1 条随机推送
- 设备处于 Listening/Speaking 状态时，随机推送等待或丢弃
- 紧急推送（如天气预警）可打断当前会话

**输入**：服务器定时任务生成推送内容
**处理**：WebSocket 下发 `notify` 消息，固件判断优先级后播放
**输出**：设备播报闲聊内容，屏幕显示字幕

### 2.2 唤醒词参数服务器下发

**背景**：当前唤醒词灵敏度、VAD 阈值等参数写死在 `sdkconfig.defaults`，修改需重新编译烧录。

**需求**：
- 服务器通过 `device_config` JSON 下发唤醒词相关参数
- 关键参数：`wake_word_threshold`（灵敏度 1-100）、`wake_word_duration`（时长 ms）、`vad_threshold`（VAD 阈值）
- 支持热更新，无需重启设备
- 参数持久化到 NVS，断网后仍有效

**约束**：
- 参数范围校验（服务端 + 客户端双重）
- 旧设备兼容：未下发参数时回退到编译默认值
- NVS 空间监控，超限告警

**输入**：服务器 `device_config` 消息
**处理**：`Board::ApplyDeviceConfig()` 解析新字段，写入 NVS
**输出**：下次引擎初始化时读取 NVS 参数生效

### 2.3 OTA 升级地址动态获取

**背景**：当前 OTA URL 硬编码在固件中，版本回滚依赖手动策略。

**需求**：
- 服务端提供 `/ota/config/version` 接口，返回配置版本号 + 下载地址
- 固件启动时检查配置版本，有更新则下载并应用
- 配置包格式：zip 包含 `config.json` + 音频资源
- 支持回滚：新版本失败可回退到旧配置

**约束**：
- 配置 OTA 与固件 OTA 分离管理
- 下载失败不阻塞启动，重试机制（最多 3 次）
- 同版本配置幂等（版本号相同则跳过）

**输入**：固件启动时请求版本接口
**处理**：对比版本号，有新版本则下载解压应用到 NVS
**输出**：配置更新日志 + 版本号持久化

### 2.4 硬件通信走 UDP

**背景**：当前控制信令走 WebSocket，心跳和数据开销偏大。UDP 更轻量，适合频繁心跳和配置同步。

**需求**：
- 新增 UDP 通道用于心跳和配置更新（独立于 WebSocket 音频流）
- 心跳间隔：15 秒（防止 NAT 超时）
- 配置更新通过 UDP 推送，比 WebSocket 更低延迟
- 保留 WebSocket 用于音频流和复杂协议

**约束**：
- WiFi 环境正常，蜂窝网络（ML307/NT26）需验证 NAT 兼容性
- UDP 无连接特性：需加源 IP 校验防伪造
- 心跳失败时自动 fallback 到 WebSocket 心跳

**输入**：服务器定时推送 UDP 心跳包/配置
**处理**：设备创建 UDP socket，收发包，独立定时器
**输出**：轻量心跳确认 + 实时配置同步

### 2.5 记忆时间图

**背景**：当前对话历史无时间维度展示，用户难以快速回顾"什么时间说了什么"。

**需求**：
- Web 管理后台展示用户与设备的对话时间线图
- 时间轴按小时/天聚合，支持缩放
- 点击时间点可展开查看详情（对话内容、实体提取结果）
- 支持筛选：按日期范围、对话类型、实体类型

**约束**：
- 数据量大的时候分页加载（每次 20 条）
- 时间图数据从对话记录表聚合，不单独存储
- 前端图表库推荐：ECharts timeline

**输入**：用户选择时间范围
**处理**：后端按 `created_at` 聚合对话记录
**输出**：时间轴图表 + 详情弹窗

### 2.6 实体图谱优化

**背景**：当前实体图谱质量差，节点关系混乱，缺乏 LLM 辅助提取。

**需求**：
- 基于 LLM 提取对话中的实体（人名、地点、事件、偏好）
- 图谱可视化：节点 = 实体，边 = 关系，支持力导向布局
- 实体去重：同名实体合并（如"小明"和"张三"可能是同一人）
- 关系置信度：LLM 返回 confidence 分数，低于阈值人工审核

**约束**：
- LLM 调用异步处理，不阻塞对话流程
- 实体提取失败时降级为关键词匹配
- 图谱数据增量更新，不全量重建

**输入**：新对话完成后触发 LLM 提取
**处理**：调用 LLM API 提取实体和关系，存储到图谱表
**输出**：前端图谱可视化 + 实体列表

### 2.7 记忆一键导入文本 LLM 分析提取

**背景**：用户手动逐条录入记忆成本高，希望批量导入历史记录。

**需求**：
- 记忆管理模块新增"一键导入"按钮
- 用户粘贴文本（对话记录、笔记等）→ LLM 分析提取关键信息 → 存入记忆库
- 支持批量导入：一次性处理多条历史记录
- 提取结果可人工编辑后再确认存入

**约束**：
- 单次导入文本长度限制（如 5000 字符）
- LLM 提取超时：10 秒 timeout，失败提示用户重试
- 导入结果预览：显示提取的记忆条目，用户确认后再写入

**输入**：用户粘贴文本 + 选择目标设备
**处理**：后端调用 LLM 分析，返回结构化记忆条目
**输出**：前端预览 + 确认后写入数据库

### 2.8 接入微信 OpenClaw

**背景**：设备仅能通过语音交互，缺乏移动端触达能力。用户希望用微信直接与设备对话。

**需求**：
- 参考 https://clawbot.ai/zh/wechatclawbot/installation-guide.html
- 新增 OpenClaw 网关服务，桥接微信生态与小智服务器
- 用户通过微信小程序或公众号与小智设备交互
- 支持双向通信：微信发消息 → 设备播报，设备状态 → 微信推送

**约束**：
- 微信 OAuth 鉴权：OpenID → device_id 映射
- 消息长度限制：微信单条消息 2000 字符
- 设备离线时消息缓存，上线后补推

**输入**：用户在微信发送消息
**处理**：OpenClaw 网关转发到小智服务器，触发对话流程
**输出**：设备播报回复 + 微信推送文本/音频

---

## 3. 数据模型设计

### 3.1 扩展 device_config 表

```sql
ALTER TABLE device_config ADD COLUMN wake_word_threshold INT DEFAULT 75;
ALTER TABLE device_config ADD COLUMN wake_word_duration INT DEFAULT 2000;
ALTER TABLE device_config ADD COLUMN vad_threshold INT DEFAULT 50;
ALTER TABLE device_config ADD COLUMN aec_mode VARCHAR(32) DEFAULT 'server';
ALTER TABLE device_config ADD COLUMN random_push_enabled BOOLEAN DEFAULT true;
ALTER TABLE device_config ADD COLUMN random_push_interval_min INT DEFAULT 5;
ALTER TABLE device_config ADD COLUMN random_push_interval_max INT DEFAULT 30;
ALTER TABLE device_config ADD COLUMN push_silent_start TIME DEFAULT '22:00:00';
ALTER TABLE device_config ADD COLUMN push_silent_end TIME DEFAULT '07:00:00';
```

### 3.2 新增 memories 表

```sql
CREATE TABLE memories (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    device_id VARCHAR(64) NOT NULL,
    user_id VARCHAR(64),
    content TEXT NOT NULL,
    memory_type VARCHAR(32) NOT NULL DEFAULT 'fact',
    importance FLOAT DEFAULT 0.5,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    expires_at TIMESTAMP NULL,
    imported_from TEXT NULL COMMENT '导入来源',
    INDEX idx_device_created (device_id, created_at),
    INDEX idx_type (memory_type)
);
```

### 3.3 新增 entities 表

```sql
CREATE TABLE entities (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    device_id VARCHAR(64) NOT NULL,
    name VARCHAR(255) NOT NULL,
    entity_type VARCHAR(32) NOT NULL DEFAULT 'person',
    metadata JSON NULL COMMENT 'LLM 提取的额外属性',
    confidence FLOAT DEFAULT 0.8,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_device_type (device_id, entity_type),
    INDEX idx_name (name)
);
```

### 3.4 新增 relations 表

```sql
CREATE TABLE relations (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    device_id VARCHAR(64) NOT NULL,
    subject_id BIGINT NOT NULL,
    predicate VARCHAR(255) NOT NULL,
    object_id BIGINT NOT NULL,
    confidence FLOAT DEFAULT 0.8,
    source_memory_id BIGINT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (subject_id) REFERENCES entities(id) ON DELETE CASCADE,
    FOREIGN KEY (object_id) REFERENCES entities(id) ON DELETE CASCADE,
    FOREIGN KEY (source_memory_id) REFERENCES memories(id) ON DELETE SET NULL,
    INDEX idx_subject (subject_id),
    INDEX idx_object (object_id)
);
```

### 3.5 新增 wechat_bindings 表

```sql
CREATE TABLE wechat_bindings (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    openid VARCHAR(128) NOT NULL,
    device_id VARCHAR(64) NOT NULL,
    bound_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_active_at TIMESTAMP NULL,
    is_active BOOLEAN DEFAULT true,
    UNIQUE KEY uk_openid (openid),
    INDEX idx_device (device_id),
    INDEX idx_active (is_active, device_id)
);
```

### 3.6 新增 push_schedules 表

```sql
CREATE TABLE push_schedules (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    device_id VARCHAR(64) NOT NULL,
    push_type VARCHAR(32) NOT NULL DEFAULT 'random',
    content_text TEXT NOT NULL,
    audio_url VARCHAR(512) NULL,
    scheduled_at TIMESTAMP NOT NULL,
    status VARCHAR(32) DEFAULT 'pending' COMMENT 'pending/sent/failed',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_device_status (device_id, status),
    INDEX idx_scheduled (scheduled_at)
);
```

---

## 4. 接口设计

### 4.1 固件协议扩展

**新增 device_config 字段：**
```json
{
  "type": "device_config",
  "payload": {
    "wake_word_threshold": 75,
    "wake_word_duration": 2000,
    "vad_threshold": 50,
    "aec_mode": "server",
    "random_push_enabled": true,
    "random_push_interval_min": 5,
    "random_push_interval_max": 30,
    "push_silent_start": "22:00:00",
    "push_silent_end": "07:00:00"
  }
}
```

**新增 notify 消息类型：**
```json
{
  "type": "notify",
  "push_type": "random",
  "audio_url": "http://...",
  "subtitles": [{"start_ms": 0, "text": "你好"}]
}
```

**新增 UDP 心跳协议：**
```
客户端 → 服务端：{"type":"udp_heartbeat","device_id":"xxx","ts":1234567890}
服务端 → 客户端：{"type":"udp_heartbeat_ack","ts":1234567890}
```

### 4.2 服务端 API

| 接口 | 方法 | 说明 |
|------|------|------|
| `/api/v1/device/config` | GET | 获取设备完整配置 |
| `/api/v1/ota/config/version` | GET | 检查配置版本号 |
| `/api/v1/push/random` | POST | 创建随机推送任务 |
| `/api/v1/push/schedule` | POST | 定时推送任务 |
| `/api/v1/memories/{device_id}` | GET | 获取记忆时间图数据 |
| `/api/v1/entities/{device_id}` | GET | 获取实体图谱数据 |
| `/api/v1/llm/analyze-memory` | POST | LLM分析文本提取记忆 |
| `/api/v1/llm/batch-analyze` | POST | 批量导入分析 |
| `/api/v1/wechat/bind` | POST | 微信绑定设备 |
| `/api/v1/wechat/unbind` | DELETE | 微信解绑设备 |

---

## 5. 实施优先级建议

### Phase 1：基础能力（1-2周）
- [ ] 唤醒词参数动态下发
- [ ] UDP通信通道（配置+心跳）
- [ ] OTA配置版本检查

### Phase 2：消息系统（1周）
- [ ] 随机推送优先级处理
- [ ] 服务端推送调度器
- [ ] 通知队列管理

### Phase 3：AI能力（2-3周）
- [ ] 记忆时间图表设计+接口
- [ ] 实体图谱表设计+LLM提取接口
- [ ] 一键导入分析接口

### Phase 4：微信接入（1-2周）
- [ ] OpenClaw网关服务搭建
- [ ] 微信绑定流程
- [ ] 状态同步与远程控制

---

## 6. 风险与注意事项

| 风险 | 影响 | 缓解措施 |
|------|------|----------|
| UDP在蜂窝网络受限 | 配置更新失败 | 保留WebSocket fallback |
| NVS空间不足 | 唤醒词缓存丢失 | 监控NVS使用率，超限告警 |
| 随机推送频率过高 | 用户体验差 | 服务端频率限制+客户端忽略策略 |
| LLM提取准确率 | 记忆质量差 | 人工审核入口+重要性阈值 |
| 微信绑定安全 | 设备被盗用 | OpenID校验+设备解绑流程 |

---

## 7. 附录：关键文件索引

| 功能 | 关键文件 | 行号范围 |
|------|----------|----------|
| 唤醒词动态下发 | `main/boards/common/board.cc` | 172-300 |
| 唤醒词引擎 | `main/audio/wake_words/custom_wake_word.cc` | 219-353 |
| device_config处理 | `main/application.cc` | 776-821 |
| UDP参考实现 | `main/protocols/mqtt_protocol.cc` | 全文件 |
| 通知播放 | `main/notify/notify_player.cc` | 全文件 |
| OTA升级 | `main/ota.h/cc` | 全文件 |
| YH协议心跳 | `main/yh/yh_protocol.cc` | 28-36, 484-496 |
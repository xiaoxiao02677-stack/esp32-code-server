# 微信 ClawBot 模块后端架构设计文档

## 1. 概述

微信 ClawBot 模块为 xiaozhi-server 提供微信小程序 AI 插件（ClawBot）的接入能力，包括：
- 微信用户绑定与身份管理
- LLM 多轮对话（基于 OpenClaw CLI）
- 定时消息推送调度
- HTTP API 管理接口

本模块独立于现有 WebSocket 设备链路，通过 `core/services/wechat_claw_service.py` 作为核心业务层，通过 `core/api/wechat_claw_handler.py` 暴露 RESTful API。

---

## 2. 目录结构

```
xiaozhi-server/
├── core/
│   ├── services/
│   │   └── wechat_claw/
│   │       ├── __init__.py
│   │       └── service.py          # WeChatClawService 核心服务
│   └── api/
│       └── wechat_claw_handler.py  # HTTP API 处理器
├── config/
│   └── wechat_claw.yaml            # 配置模板
├── data/
│   └── wechat_claw.db              # SQLite 数据库（运行时创建）
└── migrations/
    └── create_wechat_claw_tables.py # 数据库迁移脚本
```

---

## 3. 数据库设计

### 3.1 表结构 DDL

```sql
-- 微信用户绑定表
CREATE TABLE IF NOT EXISTS wechat_users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    openid        TEXT    NOT NULL UNIQUE,      -- 微信用户唯一标识
    union_id      TEXT,                         -- 开放平台 unionid
    device_id     TEXT,                         -- 绑定的 xiaozhi 设备 ID
    nickname      TEXT,
    avatar_url    TEXT,
    bind_status   TEXT    NOT NULL DEFAULT 'pending',  -- pending | bound | unbound
    bind_qr_code   TEXT,                        -- 绑定二维码 content（一次性）
    created_at    TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at    TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- 对话记录表
CREATE TABLE IF NOT EXISTS conversations (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id       INTEGER NOT NULL,             -- FK -> wechat_users.id
    session_id    TEXT    NOT NULL UNIQUE,       -- 对话会话 ID（UUID）
    title         TEXT    DEFAULT '',            -- 对话标题（首条用户消息摘要）
    status        TEXT    NOT NULL DEFAULT 'active',  -- active | archived
    created_at    TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at    TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES wechat_users(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_conversations_user ON conversations(user_id);
CREATE INDEX IF NOT EXISTS idx_conversations_session ON conversations(session_id);

-- 消息内容表
CREATE TABLE IF NOT EXISTS messages (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    conversation_id INTEGER NOT NULL,            -- FK -> conversations.id
    role          TEXT    NOT NULL,              -- user | assistant | system
    content       TEXT    NOT NULL,              -- 消息正文
    message_type  TEXT    NOT NULL DEFAULT 'text', -- text | audio | image
    audio_url     TEXT,                          -- 音频 URL（message_type=audio 时）
    tokens_used   INTEGER DEFAULT 0,             -- 本次对话消耗的 token 数
    created_at    TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_messages_conv ON messages(conversation_id);
CREATE INDEX IF NOT EXISTS idx_messages_created ON messages(created_at);

-- 定时任务表
CREATE TABLE IF NOT EXISTS schedules (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id       INTEGER NOT NULL,              -- FK -> wechat_users.id
    conversation_id INTEGER,                     -- FK -> conversations.id (可为空，全局推送时为 NULL)
    task_name     TEXT    NOT NULL,
    task_type     TEXT    NOT NULL DEFAULT 'broadcast', -- broadcast | conversation
    content       TEXT    NOT NULL,              -- JSON: {push_type, audio_url, subtitles, ...}
    schedule      TEXT    NOT NULL,              -- JSON: {type, cron, delay_seconds}
    rate_limit    TEXT,                          -- JSON: {per_device, window_seconds}
    status        TEXT    NOT NULL DEFAULT 'active', -- active | paused | completed | failed
    last_run_at   TIMESTAMP,
    next_run_at   TIMESTAMP,
    run_count     INTEGER NOT NULL DEFAULT 0,
    fail_count    INTEGER NOT NULL DEFAULT 0,
    created_at    TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at    TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES wechat_users(id) ON DELETE CASCADE,
    FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_schedules_user ON schedules(user_id);
CREATE INDEX IF NOT EXISTS idx_schedules_status ON schedules(status);
CREATE INDEX IF NOT EXISTS idx_schedules_next_run ON schedules(next_run_at);
```

### 3.2 ER 关系

```
wechat_users (1) ──< conversations (1) ──< messages
       │
       │ (1) ──< schedules
       │
       └── (N) device_id → xiaozhi 设备
```

---

## 4. 核心服务设计

### 4.1 WeChatClawService 类图

```
┌─────────────────────────────────────────────────────────────┐
│                   WeChatClawService                          │
├─────────────────────────────────────────────────────────────┤
│ - config: dict                                              │
│ - db_path: str                                              │
│ - _llm_client: OpenClawCLI (optional)                       │
│ - _push_scheduler: PushScheduler                            │
│ - _conversation_cache: dict[str, list]  (session_id→msgs)   │
│ + __init__(config)                                          │
│ + start()                                                   │
│ + stop()                                                    │
│                                                             │
│ # 用户管理                                                   │
│ + bind_user(openid, device_id) -> dict                      │
│ + get_user(openid) -> Optional[dict]                        │
│ + get_user_by_device(device_id) -> Optional[dict]           │
│ + unbind_user(openid)                                       │
│                                                             │
│ # 对话管理                                                   │
│ + create_conversation(user_id) -> str  (session_id)         │
│ + list_conversations(user_id, limit, offset) -> list        │
│ + get_conversation(session_id) -> Optional[dict]            │
│ + archive_conversation(session_id)                          │
│                                                             │
│ # 消息管理                                                   │
│ + send_message(session_id, role, content, msg_type) -> dict │
│ + get_messages(session_id, limit, offset) -> list           │
│                                                             │
│ # LLM 对话                                                   │
│ + chat(session_id, user_msg) -> dict  (response+tokens)     │
│ + clear_context(session_id)                                 │
│                                                             │
│ # 定时任务                                                   │
│ + create_schedule(user_id, task) -> str  (schedule_id)      │
│ + list_schedules(user_id) -> list                           │
│ + get_schedule(schedule_id) -> Optional[dict]               │
│ + delete_schedule(schedule_id)                              │
│ + pause_schedule(schedule_id)                               │
│ + resume_schedule(schedule_id)                              │
│ + run_once(schedule_id)                                     │
└─────────────────────────────────────────────────────────────┘
```

### 4.2 关键时序图

#### 用户扫码绑定流程

```
微信小程序          HTTP API          WeChatClawService        SQLite
   │                 │                     │                    │
   │  POST /bind     │                     │                    │
   │  {qr_code}      │                     │                    │
   │────────────────→│                     │                    │
   │                 │  generate_qr()      │                    │
   │                 │────────────────────→│                    │
   │                 │                     │  INSERT wechat_users│
   │                 │                     │───────────────────→│
   │                 │                     │                    │
   │  {bind_url}     │                     │                    │
   │←────────────────│                     │                    │
   │                 │                     │                    │
   │  用户扫码确认    │                     │                    │
   │（回调OpenClaw）  │                     │                    │
   │                 │                     │                    │
   │                 │  POST /bind/confirm │                    │
   │                 │  {openid, code}     │                    │
   │                 │────────────────────→│                    │
   │                 │                     │  UPDATE bind_status │
   │                 │                     │───────────────────→│
   │                 │                     │                    │
   │  {device_id}    │                     │                    │
   │←────────────────│                     │                    │
```

#### LLM 多轮对话流程

```
微信小程序         HTTP API         WeChatClawService        LLM(OpenClaw)    SQLite
    │                │                     │                      │              │
    │ POST /messages │                     │                      │              │
    │ {content}      │                     │                      │              │
    │───────────────→│                     │                      │              │
    │                │ create_convo/check  │                      │              │
    │                │────────────────────→│                      │              │
    │                │                     │ build_prompt(ctx)    │              │
    │                │                     │─────────────────────→│              │
    │                │                     │                      │  generate    │
    │                │                     │                      │←─────────────│
    │                │                     │  {reply, tokens}     │              │
    │                │                     │←─────────────────────│              │
    │                │                     │ INSERT messages      │              │
    │                │                     │─────────────────────→│              │
    │                │                     │ cache context        │              │
    │  {reply}       │                      │                      │              │
    │←───────────────│                      │                      │              │
```

---

## 5. HTTP API 设计

### 5.1 路由注册

所有路由挂载在 `/api/wechat/claw/` 前缀下，受 Bearer token 鉴权保护（与现有 `/api/push/*` 一致）。

| 方法 | 路径 | 功能 |
|------|------|------|
| GET | `/api/wechat/claw/status` | 查询微信绑定状态 |
| POST | `/api/wechat/claw/bind` | 发起扫码绑定 |
| POST | `/api/wechat/claw/bind/confirm` | 确认绑定（扫码后回调） |
| GET | `/api/wechat/claw/conversations` | 对话列表 |
| POST | `/api/wechat/claw/conversations` | 创建新对话 |
| GET | `/api/wechat/claw/conversations/{session_id}` | 对话详情 |
| POST | `/api/wechat/claw/conversations/{session_id}/messages` | 发送消息 |
| GET | `/api/wechat/claw/conversations/{session_id}/messages` | 消息历史 |
| DELETE | `/api/wechat/claw/conversations/{session_id}` | 归档对话 |
| GET | `/api/wechat/claw/schedules` | 定时任务列表 |
| POST | `/api/wechat/claw/schedules` | 创建定时任务 |
| GET | `/api/wechat/claw/schedules/{id}` | 定时任务详情 |
| DELETE | `/api/wechat/claw/schedules/{id}` | 删除定时任务 |
| POST | `/api/wechat/claw/schedules/{id}/pause` | 暂停任务 |
| POST | `/api/wechat/claw/schedules/{id}/resume` | 恢复任务 |
| POST | `/api/wechat/claw/schedules/{id}/run` | 立即执行一次 |

### 5.2 请求/响应示例

**GET /api/wechat/claw/status**
```json
// 响应 200
{
  "code": 0,
  "msg": "success",
  "data": {
    "bound": true,
    "openid": "oXXX...",
    "nickname": "张三",
    "device_id": "esp32_001",
    "bind_time": "2026-10-12T10:30:00Z"
  }
}
```

**POST /api/wechat/claw/conversations/{id}/messages**
```json
// 请求体
{
  "content": "今天天气怎么样？",
  "message_type": "text"
}

// 响应 200
{
  "code": 0,
  "msg": "success",
  "data": {
    "message_id": 42,
    "conversation_id": "conv_abc123",
    "reply": "今天北京晴，气温18-25度...",
    "tokens_used": 156,
    "response_time_ms": 820
  }
}
```

---

## 6. 配置文件

详见 `config/wechat_claw.yaml`。关键配置项：

```yaml
wechat_claw:
  enabled: true
  database_path: "data/wechat_claw.db"
  auth_key: ""                          # 与 server.auth_key 共用，或单独指定
  llm:
    provider: "openclaw"                # openclaw | openai | anthropic
    model: "claude-sonnet-4-20250514"
    max_tokens: 2048
    context_window: 8000                # 保留最近 N 条消息作为上下文
  binding:
    qr_expiry_seconds: 300              # 绑定二维码有效期
  schedule:
    max_per_user: 10                    # 每用户最大定时任务数
    default_cron_allowed: true          # 是否允许自定义 cron
```

---

## 7. 与现有系统的集成点

| 集成点 | 方式 |
|--------|------|
| `PushScheduler` | 复用其 `schedule_push()` 执行定时推送，目标为绑定的 device_id |
| `WebSocketServer` | 通过 `wake_word_service.get_online_devices()` 校验设备在线状态 |
| `OpenClaw CLI` | 通过 `subprocess` 调用 `openclaw chat` 命令完成 LLM 对话 |
| `SimpleHttpServer` | 在 `app.py` 启动时初始化 `WeChatClawService`，注册路由到 `wechat_claw_handler` |

---

## 8. 安全考虑

1. **鉴权**：所有 `/api/wechat/claw/*` 端点使用 Bearer token 校验（`_verify_auth`），token 来自 `config.server.auth_key`
2. **Loopback 限制**：与 `/api/memory/*` 相同策略，仅允许 `127.0.0.1` / `::1` 访问（中间件拦截）
3. **SQL 注入防护**：所有数据库操作使用参数化查询（`?` 占位符），禁止字符串拼接
4. **Token 限额**：LLM 调用限制 `max_tokens`，防止 Prompt 注入导致费用爆炸
5. **绑定二维码**：一次性使用，生成后 5 分钟过期，防止重放攻击

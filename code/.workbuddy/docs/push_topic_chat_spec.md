# 推送任务「话题源随机聊天」功能 — 具体需求规格说明书

> 版本：v1.0（2026-10-12）
> 生成方式：5 agent 协同（需求解析 / 前端分析 / 服务端分析 / 固件分析 / 整合成文）
> 约束：本需求**禁止对代码进行增删**，本文档仅为需求规格与修改思路
> 涉及仓库：console-v2（前端管理台）、xiaozhi-server（Python 服务端）、xiaozhi-esp32（固件，仅作兼容约束分析，不改）

---

## 1. 需求背景与目标

### 1.1 原始需求（用户原话）
> 关于推送任务：`#app > ... > div.modal-body > div:nth-child(3) > input`，改成"不是不选项"。主要就一个目的，随机发起一个对话跟用户聊天，话题来自记忆，话题源可从配置界面让管理员多选或单选：记忆、天气...等

### 1.2 需求澄清（req-parser 结论）
- CSS 选择器指向 `PushScheduler.vue:117-120` 的**音频 URL 输入框**（当前带 `*` 必填标记 + 提交阻断校验）。
- "改成不是不选项"最可能解读为 **"改成不再是必填选项"**（"不/必"语音近音混淆）；语义延伸为"推送方式不再只有音频 URL 一种"。
- 两种解读收敛到同一产品改动：**音频 URL 改选填 + 新增动态话题推送类型**。

### 1.3 核心目标（一句话）
把"新建推送任务"从只能推固定音频 URL，升级为：**推送触发时由 LLM 基于管理员选定的话题源（记忆/天气/闲聊）动态生成对话开场白，经服务端 TTS 合成后下发设备播放，实现"系统主动找用户聊天"**。

### 1.4 成功标准（可验证）
1. 管理员可创建不含 audio_url、仅含话题源的推送任务并提交成功。
2. 任务触发后，设备播报一段基于该设备 agent 记忆（或天气/闲聊）生成的自然开场白（≤80 字）。
3. 会话保持窗口内（路径 B'），开场白播完设备自动进入聆听态，用户可直接接话。
4. 记忆为空/天气失败/LLM 超时均有降级路径，任务不悬挂。
5. 现有"固定音频 URL"推送任务行为完全不变（向后兼容）。

---

## 2. 名词定义

| 名词 | 定义 |
|---|---|
| 话题源（topic source） | 开场白内容的取材来源，一期枚举：`memory`（记忆）/ `weather`（天气）/ `chat`（闲聊），架构可扩展 |
| 话题生成（topic generation） | 推送触发时，服务端按话题源取材后调用 LLM 生成开场白文本的过程 |
| 开场白（opener） | LLM 生成的一句自然对话发起语，如"我记得你上周说想学吉他，练得怎么样啦？" |
| 固定音频模式 | 现状模式：管理员预填 audio_url，设备直接播放 |
| 话题生成模式 | 新模式：audio_url 留空 + 话题源 ≥1，服务端动态生成内容 |
| 会话保持窗口（B' 窗口） | 设备上一轮对话结束后音频通道仍开的时段（WS 传输 120s 超时内，protocol.cc:112-121） |

---

## 3. 功能需求

### FR-1 音频 URL 改为可选（P0，前端）
- 依据 fe-analyst，3 处精确改动点（`console-v2/src/views/admin/PushScheduler.vue`）：
  1. **模板 118 行**：删除 `<span class="req">*</span>`；hint 文案改为"留空则必须选择话题源，由服务端生成推送内容"。
  2. **校验 292 行**：`if (!f.audioUrl.trim())` 改为二选一校验：
     `if (!f.audioUrl.trim() && !f.topicSources.length) { toast('音频 URL 与话题源至少配置一项'); return }`
  3. **payload 293 行**：改为条件添加（与 294-295 行 subtitles 同风格）：
     `const content = { push_type: f.pushType }; if (f.audioUrl.trim()) content.audio_url = f.audioUrl.trim()`
- **audio_url 为空时省略字段而非传 null**（fe-analyst 结论）：与现有条件字段风格一致；后端 `content.get('audio_url')` 判缺失最自然；避免 Pydantic Optional 兼容问题。

### FR-2 话题源选择器（P0，前端）
- **控件**：checkbox 多选，样式复用现有 `.dev-picker`（72-82 行），位于字幕文本（121-125 行）之后。
- **候选选项**（一期前端写死，参照 cronPresets 195-200 行常量表模式）：

  | value | label |
  |---|---|
  | memory | 记忆 |
  | weather | 天气 |
  | chat | 闲聊 |

  渲染规则："查表取 label，查不到显示 value 原文"，payload 只传 value 字符串——二期可切服务端下发枚举（新增 `GET /api/push/topic-sources`），只换数据源函数。
- **默认值**：`topicSources: []`（不勾选），blankForm()（202-212 行）新增该字段。
- **互斥/共存矩阵**：

  | audioUrl | topicSources | 结果 |
  |---|---|---|
  | 空 | ≥1 | ✅ 话题生成模式 |
  | 非空 | 空 | ✅ 现状固定音频模式 |
  | 非空 | ≥1 | ❌ 服务端 400 拒绝（避免歧义，见 FR-4）；前端建议 UI 禁用一方 |
  | 空 | 空 | ❌ FR-1 校验拦截 |

- **推荐终态（P1）**：新增 radio"内容来源"（固定音频 / 话题生成）切换显示 audioUrl+subtitleText 或 topicSources，blankForm 加 `contentMode: 'audio'` 默认旧行为。一期可先平铺 + 校验拦截。

### FR-3 话题源数据获取与开场白生成（P0，服务端）
- **新文件**：`core/services/topic_generator.py`（be-analyst 设计）。
- **接口**：`async generate(device_id, topic_sources) -> {text, source_used, materials}`。
- **多源随机语义**（req-parser 问题 2，建议默认）：多选时随机挑一个源 → 源内随机取材 → LLM 生成时注入随机因子（当前时间+随机数）保证多样性。三层叠加。
- **各源实现要点**：

  | 源 | 数据获取 | 关键注意 |
  |---|---|---|
  | memory | `memory/base.py:22` `query_memory(query)`；按 agent_id 惰性缓存 provider 实例（勿复用 conn 实例——绑定 session 且有创建开销） | nomem 永远返回空（nomem.py:18-20）；mem_local_short 返回全量需截断（~500 字）；mem0/powermem role_id 空则返回空。**空记忆必须降级** |
  | weather | 走 `plugins_func/functions/get_weather.py:165-171` 底层函数；TopicGenerator 构造最小 stub conn（config 透传 plugins 段、client_ip=None、loop=运行中 loop），全异步调用；**禁止**直接用 `_get_weather_info`（prompt_manager.py:166-209 内含 threading.Event 同步阻塞，专为线程池设计） | 无 client_ip 落 default_location"广州"（get_weather.py:171,190,193）；建议任务级 `location` 字段可选传入 |
  | chat | `LLMProviderBase.response_no_stream(system, user)`（llm/base.py:13-22）纯 LLM 闲聊 | **必须 `asyncio.to_thread` 包装**（同步网络 IO），否则阻塞整个事件循环 |

- **生成时机**：**任务触发时实时生成**（be-analyst 结论）——话题新鲜度是核心价值；cron 周期任务无法预生成；创建 API 保持毫秒级。LLM 2-5s 延迟靠独立并发信号量 + 降级缓解。
- **个性化粒度**：**per-agent 而非 per-device**（be-analyst 核实）——记忆维度是 agent（role_id=agent_id，connection.py:1051-1053），同 agent 多设备共享记忆；生成次数 = 目标设备去重后的 agent 数；agent 反查用 `wake_word_service._agent_devices`（wake_word_service.py:17），反查失败按 device_id 兜底。

### FR-4 内容下发路径：服务端 TTS 合成 → audio_url（P0，服务端）
- **选定路径①**（be-analyst + fw-analyst 一致推荐）：开场白文本 → 服务端 TTS 合成 → 托管静态文件 → 写回 `content.audio_url` → 走既有 notify 通道下发。**零固件改动**。
- **TTS 可行性证据**：`TTSProviderBase.text_to_speak(text, output_file)`（tts/base.py:357-359）抽象方法；edge provider 完全免 conn（edge.py:45-65）；现成先例 `_synthesize_fallback_audio`（tts/base.py:152-178）就在无会话上下文中合成；复用 `initialize_tts` 的 fallback 降级链（modules_initialize.py:151-208，默认挂 EdgeTTS）。
- **约束**：仅可用 `delete_audio_file=False` 模式 provider（产物留文件供设备拉取）；**需新增 HTTP 静态路由暴露 tmp 目录**（先例：OTA 下载路由 http_server.py:180-187）；audio_url 与 OTA 地址同源保证设备可达；开场白限长（prompt 约束 + 截断 ≤80 字）控制 TTS 时长/费用。

### FR-5 对话闭环（P0 设计决策，依据 fw-analyst 三路径对比）
- **主路径 B'（零固件改动）**：服务端在设备上一轮会话的音频通道仍开窗口内（`IsAudioChannelOpened()` 且 120s 超时未触发），直接下发 `tts start + 音频 + stop`。设备 auto 模式下"TTS 播完自动回 Listening"是**现成机制**（application.cc:734-748，auto/realtime → 745 行 SetDeviceState(kDeviceStateListening)），天然支持"开场白→用户接话"闭环。
- **兜底路径 A（冷启动场景）**：设备久置 Idle 时无下行音频通道（WS 传输 Idle 时根本无连接，websocket_protocol.cc:21-24；MQTT 音频需设备侧握手建 UDP，mqtt_protocol.cc:274-384），服务端无法凭空发起对话——只能走 notify 播报（application.cc:677-682，audio_url 必填；播完 Notifying→Idle，device_state_machine.cc:97-98 单向），用户喊唤醒词再进入对话（application.cc:1134-1136 已支持 Notifying 态唤醒打断）。**话术设计建议**：冷启动开场白结尾加"想聊就喊我"引导。
- **路径 C（固件小改，明确列为后续增强，不在本期）**：Notifying→Listening 状态机转换 + HandleNotificationFinished（1419-1426 行）改走开通道→StartListeningAudio；须用字段开关（如 `expect_reply:true`）避免影响闹铃/提醒类单向播报场景；风险含开麦 1s 空窗、manual 模式残留（需强制 auto，1099 行先例）、失败回退 Notifying→Idle。
- **结论**：本期 FR 全部零固件改动；B' 覆盖"趁热聊天"主场景，A 覆盖冷启动；C 独立排期。

### FR-6 详情与列表展示（P1，前端）
- 详情弹窗（156-168 行）：162 行后新增"话题源"kv 行：`(detail.content?.topic_sources || []).join('、') || '—'`；162 行 audio_url 展示增强为 `audio_url || (topic_sources?.length ? '（按话题源动态生成）' : '—')`。
- 服务端 `list_tasks`（push_scheduler.py:369-378）是白名单字段拼装、不含 content——**需补 topic_sources 字段**，列表才能区分话题任务与普通任务。
- 旧任务无 topic_sources 字段时 `|| []` / `|| '—'` 兜底，不报错。

### FR-7 管理配置与调度器扩展（P0，服务端）
- **任务数据结构**：content 新增约定字段 `topic_sources: ["memory",...]`（至少一个，取值 ⊆ 枚举，单字符串归一化为列表）；可选 `location`（weather 源城市）。
- **_deliver 前插入生成步骤**（push_scheduler.py:252 入口）：`content.get("topic_sources")` 且无 audio_url → 按 agent 去重生成 → TTS 合成 → 写回 audio_url/subtitles（含 `generated_text` 供详情追溯）。生成逻辑放 `_deliver` 内可同时覆盖 cron 修复后的路径。
- **降级链**（be-analyst 推荐）：生成失败 → 重试 1 次（LLM 超时 8-10s）→ 降级 chat 源纯 LLM（无外部依赖，成功率最高）→ 仍失败跳过本次推送计入 failed_count（不置任务 failed、不推无声字幕）。
- **限流前置**：生成前先算 `target ∩ online` 并预检 per-device rate limit，全部被限流则跳过生成（避免白做）。
- **独立生成并发池**：新增 `_generation_semaphore = asyncio.Semaphore(2~3)`——现有 `max_concurrent=5`（push_scheduler.py:51）只管下发并发，LLM+TTS 生成是秒级慢操作，必须独立限流；LLM 调用包 `asyncio.to_thread` + `asyncio.wait_for`。
- **⚠ 前置阻塞缺陷必须先修（be-analyst 发现）**：
  - **cron 任务永不执行**：调度循环显式排除 cron（push_scheduler.py:79），而 `_execute_cron`（194-225 行）全仓库零调用；
  - **delayed 立即执行**：`delay_seconds` 从未被调度器使用，`_execute_delayed`（189-192 行）死代码；
  - "管理员定时发起闲聊"核心场景依赖 cron，**此项是 P0 前置修复**。

### FR-8 API 变更（P0，服务端 push_handler.py）
- **创建接口 handle_schedule（44-119 行）**：
  - 修改 audio_url 必填规则（75-76 行）→ **audio_url 与 topic_sources 二选一**，两者都无 → 400「content 必须包含 audio_url 或 topic_sources」；两者都有 → 400 拒绝（歧义）。
  - 新增校验：topic_sources 非空列表且取值 ⊆ {memory, weather, chat}。
  - 新增可选字段：`content.location`。
- **详情接口 get_task（134-148 行）**：返回原始 task dict（push_scheduler.py:361-363），天然含 topic_sources/generated_text，无需改动。
- **列表接口 list_tasks**：补 topic_sources 字段（见 FR-6）。
- 鉴权机制不变（Bearer auth_key）。

---

## 4. 数据结构变更

### 4.1 创建任务请求体（新增字段标注 ★）
```json
{
  "device_ids": ["xiaozhi-xxxx"],
  "content": {
    "push_type": "random",
    "topic_sources": ["memory", "weather"],   // ★ 与 audio_url 二选一
    "location": "上海",                        // ★ 可选，weather 源城市
    "audio_url": "",                           // 选填；话题模式下省略
    "subtitles": [{"text": "..."}]             // 可选；话题模式下通常省略
  },
  "schedule": { "type": "cron", "cron": "every_5m" },
  "rate_limit": { "per_device": 3, "window_seconds": 300 }
}
```

### 4.2 任务详情响应体（生成后）
```json
{
  "push_id": "xxx",
  "content": {
    "push_type": "random",
    "topic_sources": ["memory"],
    "audio_url": "http://{server}/tmp/tts-xxxx.mp3",   // 生成后写回
    "subtitles": [{"text": "你上周说想学吉他，练得怎么样啦？"}],
    "generated_text": "你上周说想学吉他，练得怎么样啦？",  // ★ 追溯用
    "generation_meta": {"source_used": "memory", "agent_id": "xxx", "cost_ms": 2300}
  }
}
```

### 4.3 设备最终收到的消息（不变，固件零改动）
```json
{"type": "notify", "push_type": "random", "audio_url": "http://...", "subtitles": [...]}
```

---

## 5. 接口变更汇总

| 接口 | 变更类型 | 说明 |
|---|---|---|
| POST /api/push/schedule | 修改 | audio_url 改二选一；新增 topic_sources/location 校验 |
| GET /api/push/tasks | 修改 | 列表项补 topic_sources 字段 |
| GET /api/push/tasks/{id} | 不变 | 天然透传新字段 |
| （新增静态路由） | 新增 | 暴露 tmp/ TTS 产物目录（先例 OTA 路由） |
| GET /api/push/topic-sources | 二期预留 | 话题源枚举服务端下发 |

---

## 6. 交互流程

### 6.1 主流程（话题任务触发 → 设备播放）
```
管理员                    前端                服务端                        设备
  │ 创建任务               │                    │                            │
  ├─选设备+话题源─────────▶│ POST /push/schedule│                            │
  │                       ├─校验二选一─────────▶│ schedule_push 入队         │
  │                       │                    │ (audio_url 校验放行)        │
  │                       │                    │                            │
  │                  [触发时刻：immediate/delayed/cron]                    │
  │                       │                    │ _deliver 入口              │
  │                       │                    │ 1.限流预检(设备∩在线)       │
  │                       │                    │ 2.按agent去重              │
  │                       │                    │ 3.TopicGenerator.generate  │
  │                       │                    │   memory→query_memory      │
  │                       │                    │   (失败→降级chat)          │
  │                       │                    │ 4.LLM生成开场白(≤80字)     │
  │                       │                    │ 5.TTS合成→tmp/tts-*.mp3    │
  │                       │                    │ 6.写回audio_url/subtitles  │
  │                       │                    │ 7.notify 下发─────────────▶│
  │                       │                    │                     [B'窗口]│
  │                       │                    │              tts流播报      │
  │                       │                    │              播完自动Listening│
  │                       │                    │              ◀──用户接话───│
  │                       │                    │◀─────正常对话链路──────────│
```

### 6.2 降级流程
```
TopicGenerator.generate
  ├─ memory 源
  │    ├─ query_memory 成功且非空 ──▶ 取材生成
  │    └─ 空/异常 ──▶ 随机换源（weather → chat）
  ├─ weather 源
  │    ├─ get_weather 成功 ──▶ 取材生成
  │    └─ 异常/超时 ──▶ 降级 chat
  ├─ chat 源 / 全部降级后
  │    └─ 纯 LLM 随机闲聊
  └─ LLM 生成
       ├─ 第1次超时(8-10s) ──▶ 重试 1 次
       └─ 仍失败 ──▶ 跳过本次推送，failed_count+1，任务不置 failed
```

---

## 7. 边界与异常行为矩阵

| 场景 | 行为 | 归属 |
|---|---|---|
| 无记忆数据（nomem/空档案/新 agent） | 降级换源 → weather → chat | 服务端 TopicGenerator |
| 天气服务失败/超时 | 降级 chat 源 | 服务端 TopicGenerator |
| LLM 超时 | 重试 1 次 → 失败跳过本次 | 服务端调度器 |
| 设备全部离线 | 跳过下发（现状逻辑 266-270 行）；离线队列补推机制维持现状 | 服务端调度器 |
| 设备全部被频率限制命中 | 限流前置检查 → 跳过生成 | 服务端调度器 |
| 广播多设备（同 agent 多台） | 按 agent 去重，一次生成多台复用 | 服务端 TopicGenerator |
| 冷启动设备（久置 Idle） | notify 播报 + 开场白话术引导唤醒；不自动进聆听 | 服务端话术 + 固件现状 |
| 夜间时段 | 服务端推送时段白名单控制（固件无时段感知，fw-analyst 核实） | 服务端 |
| 循环对话（LLM 回答又触发推送） | 服务端防护：话题冷却时间、每设备每日上限、链式深度计数、"用户无应答停止再推" | 服务端 |
| MQTT 传输设备 | B' 窗口判断以设备会话状态为准，勿假设通道永续 | 服务端 |
| 旧版本前端 | 不传 topic_sources → 走原 audio_url 必填校验，行为不变 | 兼容性 |

---

## 8. 非目标（明确不做）

1. **固件任何改动**（notify 协议、状态机、Notifying→Listening 转换等均不动；路径 C 仅作为后续增强预留）。
2. 多轮对话托管状态机（后续轮次由设备现有 ASR→LLM→TTS 链路自然承接）。
3. 用户级话题偏好（话题源仅管理员可配）。
4. 新话题源实现（本期仅 memory/weather/chat 三源 + Provider 抽象扩展点；新闻/日程仅预留）。
5. 调度内核重构（仅修 cron/delayed 死代码缺陷，机制不变）。
6. 推送历史统计、失败重试策略优化。
7. 任务持久化（维持内存态现状，重启丢失已在 push_scheduler.py:6 声明可接受）。

---

## 9. 验收标准清单

### 前端（console-v2）
- [ ] 音频 URL 无 `*` 标记；双空提交被拦截并 toast 提示"音频 URL 与话题源至少配置一项"
- [ ] 仅填 audio_url 可提交（payload 无 topic_sources 字段）
- [ ] 仅勾话题源可提交（payload 无 audio_url 字段）
- [ ] 话题源 checkbox 三选项可多选，默认不勾选
- [ ] 详情弹窗正确显示话题源；旧任务显示"—"不报错

### 服务端（xiaozhi-server）
- [ ] audio_url 与 topic_sources 双空 → 400；双填 → 400
- [ ] topic_sources 非法值 → 400；单字符串归一化为列表
- [ ] cron 任务能按周期实际触发（缺陷修复验证）
- [ ] delayed 任务延迟 N 秒后触发（缺陷修复验证）
- [ ] 话题任务触发后 content 写回 generated_text/audio_url，详情接口可查
- [ ] memory 空记忆降级 chat；天气失败降级 chat；LLM 双次超时跳过推送
- [ ] 同 agent 多设备广播只生成一次
- [ ] LLM 调用在 to_thread 中执行（压测时设备连接不卡顿）
- [ ] TTS 产物可经静态路由被设备 HTTP 拉取

### 固件（xiaozhi-esp32，仅回归不改码）
- [ ] notify 固定音频推送行为与改造前一致
- [ ] B' 场景：会话窗口内收到 tts 流播完自动回 Listening，用户可直接接话
- [ ] 冷启动场景：notify 播报正常，唤醒词可打断 Notifying

### 端到端
- [ ] cron"每5分钟"+记忆源任务：设备播报基于记忆的开场白，用户接话后进入正常对话
- [ ] 全链路降级演练：停掉天气 API → 降级 chat 仍正常推送

---

## 10. 待用户确认问题清单（附建议默认答案）

| # | 问题 | 建议默认答案 |
|---|---|---|
| 1 | TTS 位置：服务端合成 vs 设备端合成？ | **服务端合成**（零固件改动，可行性已验证） |
| 2 | "随机"的定义？ | 三层叠加：随机挑源 → 源内随机取材 → LLM 随机发挥 |
| 3 | 记忆为空的降级策略？ | 随机换源（weather→chat），不跳过任务 |
| 4 | 开场白是否写入会话上下文，让设备 LLM"知道"是系统主动发起？ | **一期不写入**（B' 场景下服务端可在下发 TTS 时携带上下文提示词，二期再考虑记忆写入） |
| 5 | 话题源枚举前端写死还是服务端下发？ | 一期前端写死（渲染查表兜底），二期切服务端下发 |
| 6 | immediate 立即推送是否支持话题模式？ | **支持**（统一走 _deliver 生成管线，无例外） |
| 7 | 双填（audio_url + topic_sources）行为？ | 400 拒绝（避免歧义）；如需"话题生成失败回退固定音频"可二期加字段 |
| 8 | cron/delayed 调度缺陷修复是否纳入本期？ | **必须纳入**（P0 前置，否则定时闲聊场景不可用） |

---

## 附录：核心决策摘要

1. **"改成不是不选项" = 音频 URL 改选填 + 新增话题生成推送模式**（两层解读收敛）。
2. **下发路径**：话题生成 → 服务端 TTS（复用 text_to_speak + EdgeTTS fallback 链）→ 静态路由暴露 → 写回 audio_url → 既有 notify 通道，**零固件改动**。
3. **对话闭环**：主路径 B'（会话保持窗口内 tts 流推送，播完自动聆听是现成机制）；冷启动走 notify + 话术引导唤醒；路径 C（固件小改）独立排期。
4. **个性化粒度 per-agent**：按 agent 去重生成，同 agent 多设备复用。
5. **前置阻塞项**：push_scheduler 的 cron/delayed 死代码必须先修。
6. **关键工程约束**：LLM 同步调用必须 to_thread + 独立并发信号量；生成失败三级降级（换源→chat→跳过）；限流前置避免白生成。

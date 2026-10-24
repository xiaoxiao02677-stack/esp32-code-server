# TTS API 共享池与负载均衡设计方案（构思稿）

> 目标：因为 apiTTS 有配额/并发限制，大量设备同时说话时对上游 API 的请求做**共享池化 + 负载均衡**。
> 状态：只读审查代码后产出的方案构思，代码修改由其他 agent 执行。
> 审查日期：2026-10-20。审查代码基线：`yh/yuhe-server`（Python 服务端）+ `manager-api`（Java 管理端）。
> **实测依据**：同日 22:00 豆包 v3 生产压测（`.workbuddy/tts_concurrency_test.py`），见 §1.4。

---

## 1. 现状事实（代码证据）

### 1.1 调用链（谁在什么时候发起 HTTP 请求）

```
connection.py:644  _initialize_components() → self.tts = initialize_tts(config)
                     ↑ 每一条 WebSocket 连接各建一个 TTS 实例（设备断线时 close）
modules_initialize.py:191 initialize_tts()
                     → tts.create_instance(type, tts_config, delete_audio_file)   ← 主 provider
                     → _create_tts_fallback_provider()                             ← 备用 provider（默认 EdgeTTS）
base.py:421          open_audio_channels() → 每实例两条常驻线程
                     ├ tts_text_priority_thread   消费 tts_text_queue  → to_tts_stream()
                     └ _audio_play_priority_thread 消费 tts_audio_queue → 播报
base.py:192/247      to_tts_stream() → asyncio.run(self.text_to_speak(text, ...))
openai.py:50         text_to_speak() → requests.post(...)   ← 同步阻塞 HTTP，timeout=tts_timeout（默认 15s）
```

关键事实：

1. **每连接一实例**：`connection.py:644` 在连接初始化时创建；`connection.py:1061` 的
   `modules["tts"]` 只是"私有配置有 TTS 段"时用私有配置重搭一个，不是全局共享实例。
2. **没有任何全局限流**：`tts_text_queue` 是**每实例**的队列，进程里不存在跨连接的
   总闸门。100 台设备同时说话 = 100 个 TTS 实例、最多 100 个并发 HTTP 请求打同一个上游账号。
3. **全部 provider 都是同步 requests**：openai.py、doubao.py 等 22 个 provider 无一例外，
   没有任何连接池（requests 每次新建连接）、没有重试退避、没有并发窗口。
4. **单 key 固化在实例上**：`openai.py:17 self.api_key = config.get("api_key")`，构造时
   读死一个字符串；doubao 同理。要换 key 只能重建实例（即断线重连）。
5. **重试无退避**：`base.py:187 max_repeat_time = 5`，非致命错误重试 5 次；唯一快速失败
   路径是 `_is_fatal_tts_error`（403/鉴权类）。限流类错误（45000292/429）不在 fatal
   列表里——按 §1.4 实测这是**正确**行为（重试能消化瞬时窗口满），但缺退避间隔，
   高并发下 5 连撞会白白烧掉重试次数。
6. **降级链已存在**：主 TTS 失败耗尽后 `_synthesize_fallback_audio` 用 fallback_provider
   （默认 EdgeTTS）合成固定提示音。共享池应接在这条链**之前**，作为"用别的 key/别的账号
   再试一次"，而不是直接降到固定提示音。
7. **配置通道已存在**：Java `ai_model_config.configJson`（ModelConfigEntity.java:39）是
   JSON 字段，`ConfigServiceImpl.java:673-721` 把 TTS 模型配置（含 private_voice/ttsVolume
   等）随 agent 配置下发给 Python。**多 key 扩展不需要改数据库表结构**，只需往 configJson
   里塞字段 + 前端加编辑入口。

### 1.2 限流现状

- Python 侧已有两处 `asyncio.Semaphore` 先例可参考：
  `core/services/push_scheduler.py:83`（生成并发=3）、
  `core/providers/tools/device_config_sync.py:63`（上报并发=8）。
- 但 TTS 路径上**零限流**。
- Redis 在 Python 侧目前只有 wallpaper_ack 用到（`core/utils/wallpaper_ack.py:73`），
  尚未有配额计数器，但 Redis 可用。

### 1.3 各层瓶颈排序（哪一层先炸）

| 层 | 现状 | 打满时的表现 |
|---|---|---|
| 上游 API 账号配额 | 单账号单 key | 45000292/429 限流 → 无退避重试 5 次 → 高并发下丢句（实测 50 并发丢 2 句） |
| 服务端并发 | 每实例双线程 + 同步 requests | 线程数=连接数×2，CPU 被同步阻塞消耗，响应变慢 |
| 单连接吞吐 | 单 TTS 实例逐句合成 | 长回答逐段排队，天然串行 |
| 重试策略 | 无退避、限流也重试 | 雪崩放大器（50 并发 79 次重试才消化 48 句） |

**结论：瓶颈第一在"上游配额/并发"，第二在"服务端出向并发无闸门"。共享池要同时解决这两层。**

### 1.4 生产压测实证（2026-10-20 22:00，豆包 v3 unidirectional，生产服务器）

- **火山上游硬并发配额 = 10**（10 并发全过，11 并发必挂 1 个），
  错误码 `45000292 quota exceeded for types: concurrency`。
- 20 并发裸打：10 成功 10 失败；**走生产重试语义（5 次无退避）：20/20 全成功**，
  总重试 14 次，p50=2.1s，总耗时 2.6s。
- 50 并发：48/50 成功（2 句重试 5 次全撞墙），p50=4.1s，总耗时 6.5s。
- 10 并发满载延迟 p50≈1.2s/句（约 20 字）。
- 当前凭据（appid 2717008086，seed-tts-2.0）安全承载 ≈20 设备同时说话。

**对方案设计的直接约束**：
1. `45000292` 不在 `_TTS_FATAL_ERROR_MARKERS`（会重试）——**这是正确的行为**，
   限流错误下重试确实能成功消化排队中的请求。
2. **不要把限流类错误加入快速失败列表**——那会把 20/20 砍成 10/20。
   与通用 HTTP 429 语义相反：火山并发配额是"瞬时窗口满"，等一下就有位置。
3. 重试确实需要加**指数退避**（实测 50 并发 79 次重试才消化 48 句，
   无退避 5 连撞概率不低）。

---

## 2. 方案设计（分三层，可独立落地）

### 第一层：Key 池（多 key 轮换，解配额）

**目标**：把"一个模型一个 key"变成"一个模型一个 key 池"，请求在池内轮转，
单 key 配额打满只影响池的一角。

- **配置形状**（无表结构改动）：`ai_model_config.configJson` 里新增可选字段：
  ```json
  {
    "api_key": "sk-主key",                       // 兼容旧字段
    "api_keys": [                                // 新增：key 池
      {"key": "sk-a", "weight": 2, "tag": "账号A"},
      {"key": "sk-b", "weight": 1, "tag": "账号B"}
    ],
    "concurrency": 5,                            // 可选：全局出向并发上限
    "rate_limit": {"per_min": 60, "window": 60}  // 可选：全局速率上限
  }
  ```
  有 `api_keys` 时优先用池；没有时退化为单 key 现状（完全向后兼容）。
- **Python 侧接入点**：新建 `core/utils/tts_pool.py`（共享模块），在
  `base.py` 里加一个 `_pick_key()`（取 key 的方法），provider 子类把
  `self.api_key` 的读取改为从池取。改动面最小的是：在 `TTSProviderBase` 挂一个
  **进程级共享调度器**（见第二层），由调度器决定"这次请求用哪个 key"。
- **轮换策略**：加权轮询（weighted round-robin）起步即可；后续可加"失败标记
  冷却"（某 key 连续 429 后从池中摘除 N 秒）。

### 第二层：全局信号量 + 队列（解并发，核心层）

**目标**：给"打向上游的 HTTP 请求"装一个**进程级**闸门，让并发不再等于在线设备数。

- 新建 `core/utils/tts_pool.py`，实现一个进程级单例调度器：
  ```
  TtsPoolGate:
    - 全局信号量（默认并发 = 池内 key 数 × 每 key 安全并发，可配置）
    - 全局队列：请求按 (优先级, 到达时间) 排队
    - acquire() 阻塞取号 → 分配 key → 执行 → release()
    - 统计：每 key 的 in-flight、累计请求数、失败数（供观测与冷却决策）
  ```
  **实测校准**：单 key 安全并发 = 火山实测硬配额 10，即默认信号量初值 =
  min(10 × key 数, 配置值)。多 key 不会线性放大安全并发——需用闸门主动钳制。
- **接入点**（关键：不需要改 22 个 provider）：在 `TTSProviderBase` 加一个
  非侵入的包装方法，例如 `_run_in_pool(self, request_fn)`，或者更彻底一点：
  在 `connection.py` 里把 TTS 实例**共享化**（见 2.4 的取舍讨论）。
- **超时语义**：`base.py` 的 `tts_timeout` 语义保持不变；排队等待另设一个
  `queue_timeout`（如 30s），排队超时直接走现有降级链（fallback 固定提示音），
  保证设备最终有声音。
- 参考实现先例：`push_scheduler.py` 的 `asyncio.Semaphore(3)`。但 TTS 请求跑在
  线程里（不是事件循环），所以用 `threading.Semaphore` / `concurrent.futures` 更合适。
- **优先级设计**（关键加分项）：正常对话请求 = 普通优先级；
  **打断后新请求 = 高优先级**（设备打断旧回答再问，用户在等）；topic_generator
  等后台合成 = 低优先级。避免后台任务挤占互动语音的配额。

### 第三层：重试策略修正（解雪崩，基于实测校准）

- **限流错误不快速失败，改为"退避重试"**：实测证明 `45000292`（并发配额满）
  重试是有效的（20/20 全靠重试消化）。正确策略不是加入 fatal 列表，而是：
  - 限流错误重试时加**指数退避**：200ms / 400ms / 800ms / 1600ms
    （50 并发档无退避 5 连撞概率高，退避可显著降低失败率）。
  - 保留 5 次重试上限不变。
- **重试换 key**：每次重试重新 `_pick_key()`。若池里有多 key，
  "限流"转化为"换一个账号立即再试"（不同账号配额独立），比纯退避更优；
  单 key 时退化为纯退避，兼容现状。
- **鉴权/授权类错误保持快速失败**（`_is_fatal_tts_error` 现有逻辑不动）。
- **分层降级顺序**（在现有 `_synthesize_fallback_audio` 之前插入一级）：
  ```
  主 key 失败 → 换 key 立即重试（限 2 次）→ 仍限流 → 退避重试（200/400/800ms）
            → 重试耗尽 → 现有 fallback_provider（EdgeTTS 固定提示音）
  ```
  注意保持现有"固定提示音"兜底，这是最后的安全网。

### 2.4 取舍讨论：全局共享实例 vs 每连接实例 + 全局闸门

- **方案 A（推荐）：每连接实例不动，只加全局闸门 + key 池**。
  改动集中在 base.py + 新增 tts_pool.py，22 个 provider 几乎零改动，
  连接生命周期、队列、打断逻辑全部不变。风险最低。
- **方案 B：TTS 实例全局共享（单例池）**。彻底省资源，但要动
  `connection.py` 的连接/清理逻辑、`tts_text_queue` 的 per-connection 语义
  （队列里混入不同设备的句子）、打断逻辑，风险大，不建议作为第一步。
- **推荐路径**：先 A 后 B。A 解决 80% 的配额问题；等 A 上线稳定后，
  如果线程开销成为瓶颈，再做 B 或给 provider 换 httpx 连接池。

---

## 3. 改动清单（给执行 agent 的任务拆分）

| # | 文件 | 改动 | 类型 |
|---|---|---|---|
| 1 | `core/utils/tts_pool.py`（新建） | KeyPool（加权轮询+冷却）+ TtsPoolGate（全局信号量/队列/统计） | 新增 |
| 2 | `core/providers/tts/base.py` | `_pick_key()` 挂池；`_run_in_pool()` 包装；限流错误退避重试（不快速失败）；重试换 key | 修改 |
| 3 | `core/utils/modules_initialize.py` | `initialize_tts` 里解析 `api_keys` 初始化全局池（进程级单例） | 修改 |
| 4 | `manager-api .../model/...` | 模型编辑接口/DTO 支持 `api_keys`/`concurrency`/`rate_limit` 字段透传（configJson 已是 JSON 列，大概率只需 DTO 白名单 + 前端表单） | 修改 |
| 5 | 前端 console-v2（模型配置页） | 多 key 录入 UI（增删 key、权重、启用开关） | 修改 |
| 6 | 配置/文档 | config_from_api.yaml 示例段、README 说明 | 文档 |

**执行顺序**：1 → 2 → 3 是核心闭环（纯 Python 侧，可独立上线）；
4 → 5 是管理侧（让池可配置、可观测）；6 收尾。
注意 #2 与 #3 有依赖（池必须先存在），应同一批提交。

**验收基线**（用已有的压测脚本回归）：`tts_concurrency_retry_test.py`
20 并发应 20/20 且重试次数显著下降（池+退避生效的标志）；
50 并发应 ≥48/50 且总重试次数低于实测基线 79 次。

## 4. 可观测性（上线后要能回答的问题）

- 每 key：请求数 / 429 数 / 平均延迟 / 冷却次数（tts_pool.py 统计 + 日志）。
- 全局：排队长度、排队超时次数、降级到 fallback 的次数。
- 建议日志 tag 统一 `tts_pool`，方便 grep。

## 5. 风险与回退

- **风险 1：池配置错误导致全部 key 失效** → 保持现有 fallback 链，设备仍有固定提示音；
  池初始化失败时回退单 key 模式。
- **风险 2：全局闸门过小导致排队过长** → `queue_timeout` + 降级链保证有界；
  并发上限做成配置项，出问题一行配置调回来。
- **风险 3：上游对同一 IP 跨 key 也限流**（少数服务商按 IP 限）→ 需在池配置里
  留 `proxy` 或分 key 出口的扩展位，第一步先不做。
- **回退**：所有新字段均可选，删掉 configJson 里的 `api_keys` 即回到现状，
  代码路径完全一致。

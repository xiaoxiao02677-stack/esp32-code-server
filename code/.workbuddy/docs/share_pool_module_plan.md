# 共享池模块规划（TTS 池 / LLM 池 / 全模态池）

> 环境：测试环境（sandyun.top:22223）
> 约束：本次仅读代码、只做规划，未增删任何代码
> 前置文档：`tts_api_pool_design.md`（TTS 侧三层方案已定稿，本规划直接沿用其结论）
> 排查日期：2026-10-25

---

## 1. 现状事实（全部有代码/库证据）

### 1.1 测试库启用模型清单（ai_model_config，is_enabled=1）

| 类型 | 模型名 | 默认 | 关键配置形状（key 字段） |
|---|---|---|---|
| LLM | DeepSeek | ✅ | `{type:openai, api_key:sk-cf79..., base_url:https://api.deepseek.com, model_name:deepseek-flash}` |
| TTS | 千问TTS-Flash(48音色) | ✅ | `{type:qwen_tts, api_key:sk-ws-H.PRYR..., base_url:...qianwenaiapi.com, model:qwen3-tts-flash}` |
| TTS | 阿里云百炼全模态 | — | `{type:aliyun_multimodal, app_id:mm_8e05..., api_key:sk-ws-H.YMD..., workspace_id:llm-mzu9..., ws_url, full_duplex:true}` |
| TTS | 豆包声音复刻 | — | `{type:doubao_v3, api_key:d9f77dba..., access_token:W6P9..., resource_id:seed-tts-2.0}` |
| TTS | 豆包语音合成v3(HTTP) | — | `{type:doubao_v3, api_key:d9f77dba...(同上一把), resource_id:seed-icl-2.0}` |
| VLLM | 智谱视觉AI | ✅ | ⚠️ 脏数据：内容与 DeepSeek 完全相同（type:openai + deepseek base_url） |
| ASR | FunASR语音识别 | ✅ | `{type:fun_local}` 本地模型无 API |
| ASR | 千问语音识别(多语种) | — | `{type:qwen3_asr_flash, api_key:sk-ws-H.PEM...}` |
| 其余 | Intent×3 / Memory×5 / RAG×1 / VAD×1 | — | 本地或非 API 池对象 |

**结论 1：三类池子的真实需求范围**
- TTS 池：4 个 TTS 模型但仅 3 把 key（两个豆包共用一把）→ 池化价值中等
- LLM 池：仅 1 个 DeepSeek key → 池化价值当前为 0（规划要支持，将来加 key）
- 全模态池：1 个百炼 app（app_id+api_key+workspace_id）→ 池化价值当前为 0，但并发敏感度最高
- **共享池模块的真正价值在"结构先行"**：先把池的骨架建好，用户再往里加第二个、第三个 key

**结论 2：测试库智谱视觉AI 是脏数据**（复制了 DeepSeek 配置），执行 agent 建池前应先提醒用户修正，否则视觉请求会打到 DeepSeek。

### 1.2 实例生命周期与并发模型（决定三类池的切换语义不同）

| 链路 | 实例粒度 | 并发模型 | 请求时长 | 池化语义 |
|---|---|---|---|---|
| TTS | 每连接一实例（connection.py:644/1061 重建） | HTTP 请求级，同步 requests 阻塞 | 2-5s | 信号量 + key 轮询 |
| LLM | 每连接一实例（modules_initialize.py 工厂） | 流式 HTTP，openai SDK（openai.py:73）或 dashscope SDK（AliBL.py:3） | 10-60s | 信号量 + key 轮询 |
| 全模态 | 每连接一个 WS 长会话（aliyun_multimodal.py:889 websockets.connect） | 长连接，会话存活数分钟 | 会话级 | 新会话路由到"当前活跃会话最少"的 key |

**关键差异**：TTS/LLM 是"请求打过来时借槽位、打完释放"；全模态是"建会话时占槽、会话结束才释放"。所以全模态池的阈值是**每 key 活跃会话数**，而不是并发请求数。

### 1.3 key 固化位置（池化要改的点）

- TTS/LLM：api_key 在 provider `__init__` 从 config 读取后固化，全程无换 key 能力
- 全模态：`header = {"Authorization": f"Bearer {api_key}"}` 构造期固化（aliyun_multimodal.py:159）
- 重试模型：TTS base.py 双队列 + max_repeat_time=5 + fallback_provider（EdgeTTS 兜底）；LLM 无重试
- 实测校准（tts_api_pool_design.md §1.4）：火山硬并发配额=10，限流错误重试可消化，**不应快速失败，应指数退避+换 key**

### 1.4 配置下发链路（池定义怎么到 Python 端）

```
Java ConfigServiceImpl.getAgentModels (POST /config/agent-models)
  → 按 MAC 找设备 → 找 agent → 组装 LLM/TTS/VLLM 配置段
  → Python config/manage_api_client.py get_agent_models()（connection.py:902 触发重建）
  → modules_initialize.py _safe_init 工厂逐模块初始化
```

- 模型配置缓存：`model:data:{id}`（RedisKeys.java:48）+ `model:name:{id}`，ModelConfigServiceImpl 读写，改模型须清缓存（历史经验）
- 基础配置：`POST /config/server-base`（ConfigController.java:35）
- **池配置建议挂到 server-base 下发**（全局基础设施，不随 agent 走），Python 侧 config_loader 已保留 redis 等基础设施键（config_loader.py:105 有先例）

### 1.5 Python 侧现成的并发控制先例（照抄模式即可）

- `tts_voice_probe_handler.py:255` asyncio.Semaphore(5) 并发探测
- `device_config_sync.py:63` asyncio.Semaphore(8)
- `push_scheduler.py:83` asyncio.Semaphore(3)
- Redis 客户端单例：`wallpaper_ack.py:83` aioredis.Redis.from_url（配置里 redis 段，config_loader 保留）

### 1.6 设备规模（测试环境）

ai_device 共 3 台，近 1 天全部活跃（last_connected_at 均在 24h 内）。3 台设备即使全 duplex，全模态长连接也只有 3 个会话——**测试环境本身压不出阈值切换**，切换逻辑要靠管理端"人工置阈值+模拟"或单 key 硬配额极低来验证。

---

## 2. 总体设计：共享池数据模型

### 2.1 概念

- **池（Pool）**：一类能力的分组，类型固定（tts / llm / multimodal），对应一个业务属性集合
- **成员（PoolMember）**：池内一个 API 身份（一把 key 或一个百炼 app），有自己的阈值与状态
- **路由**：请求/会话到来时选一个成员；**阈值切换**：当前成员并发计数 ≥ 阈值 → 换下一个成员

### 2.2 建表（Liquibase，照 202610232300.sql 样板）

```sql
-- ai_share_pool 池定义
CREATE TABLE IF NOT EXISTS `ai_share_pool` (
    `id`          BIGINT      NOT NULL AUTO_INCREMENT,
    `pool_type`   VARCHAR(16) NOT NULL COMMENT 'tts/llm/multimodal',
    `name`        VARCHAR(64) NOT NULL COMMENT '池名（展示）',
    `strategy`    VARCHAR(16) NOT NULL DEFAULT 'round_robin' COMMENT '路由策略',
    `status`      TINYINT     NOT NULL DEFAULT 1,
    `remark`      VARCHAR(255) DEFAULT NULL,
    `creator`     BIGINT      DEFAULT NULL,
    `create_date` DATETIME    DEFAULT NULL,
    `updater`     BIGINT      DEFAULT NULL,
    `update_date` DATETIME    DEFAULT NULL,
    PRIMARY KEY (`id`),
    UNIQUE KEY `uk_pool_type_name` (`pool_type`, `name`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='共享池';

-- ai_share_pool_member 池成员
CREATE TABLE IF NOT EXISTS `ai_share_pool_member` (
    `id`          BIGINT      NOT NULL AUTO_INCREMENT,
    `pool_id`     BIGINT      NOT NULL,
    `name`        VARCHAR(64) NOT NULL COMMENT '成员名（展示，如 key 尾号）',
    `config_json` JSON        NOT NULL COMMENT 'API 身份（api_key/app_id/workspace_id/base_url/model...）',
    `threshold`   INT         NOT NULL DEFAULT 1 COMMENT '并发阈值：达到后切下一成员',
    `sort`        INT         NOT NULL DEFAULT 0,
    `status`      TINYINT     NOT NULL DEFAULT 1,
    `create_date` DATETIME    DEFAULT NULL,
    PRIMARY KEY (`id`),
    KEY `idx_pool_member` (`pool_id`, `sort`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='共享池成员';
```

要点：
- `config_json` 存"补丁"而非全量模型配置：下发时把池成员补丁叠加到 ai_model_config 的模型 config_json 之上（**只覆盖 api_key/app_id/workspace_id/base_url 等身份字段**），模型行为字段（voice/model 等）仍来自原模型配置
- 幂等：config_json 内容寻址可做缓存 key（壁纸 version 先例）

### 2.3 三种池的切换语义（核心差异）

| | 占用单位 | 阈值含义 | 切换时机 | 释放时机 |
|---|---|---|---|---|
| TTS 池 | 1 次合成请求 | 该 key 并发请求数上限（实测豆包=10，百炼 qwen-tts 建议先按 10 估） | 取槽时当前成员计数 ≥ 阈值 | 请求结束（成功/失败均释放） |
| LLM 池 | 1 条流式对话 | 该 key 并发流数上限（DeepSeek 官方默认 10-30） | 取槽时计数 ≥ 阈值 | 流结束 |
| 全模态池 | 1 个 WS 会话 | 该 app 活跃会话数上限（百炼按 QPS/会话配额，建议从 10 起调） | 建会话时选计数最低的成员（**最少连接优先**而非轮询） | 会话 close |

- 计数器放内存还是 Redis？**推荐 Redis INCR/DECR + 过期兜底**（进程重启/异常退出会泄漏槽位；Redis key 带 TTL 自愈）。测试服 Redis 已有（server:config 等键 + Python 端已连）。
- 成员全失败 → 回落行为：TTS 走现有 fallback_provider（EdgeTTS 提示音）；LLM 报"主人小智有点忙"现有逻辑；全模态会话失败现有重连逻辑不变。

---

## 3. 各池接入方案

### 3.1 TTS 池（方案已定稿，见 tts_api_pool_design.md）

改动点（引用前文档 §3，此处只列与本模块的接口）：
- 新建 `core/providers/tts/tts_pool.py`：成员列表从下发配置读（池模块提供的 config 段），api_keys[] 轮询 + TtsPoolGate 信号量
- base.py：构造期改为"接受成员列表"，重试时换下一成员 key（指数退避 200/400/800ms，不快速失败）

### 3.2 LLM 池

- 现状：LLM 仅 1 个 DeepSeek key，openai 兼容（openai.py:73 OpenAI client 构造期固化 key）
- 接入：`core/providers/llm/base.py` 之上加 `LLMPoolGate`（与 TTS 同构，可共用一个通用 PoolGate 类，参数化成员数）
- 触发点：`response()` / `response_no_stream()` 入口取槽 → 结束后 finally 释放
- AliBL（dashscope SDK）同样适用：Application.call 前取槽

### 3.3 全模态池（duplex 专属，差异最大）

- 现状：每设备一个 WS 长会话，api_key/app_id/workspace_id 三件套构造期必填（aliyun_multimodal.py:120-140），full_duplex=true 时音频直推百炼、本地 LLM/ASR 全旁路
- 池化语义：**建会话时**（`_ensure_ws` 或 start_session）向池请求一个成员 → 会话生命周期内独占 → close 时归还
- 路由策略：最少活跃会话优先（min-load），不是轮询——轮询会把新会话硬塞给已满的 key
- 阈值默认建议：每个百炼 app 10 个并发会话起步（测试环境 3 台设备远达不到，管理端可手调小值验证切换）
- 注意：同一设备重连/断线重建会话会换成员 → 会话状态（对话上下文）在百炼应用内按 app 隔离，换成员等于换 app，**duplex 模式下重连必须优先复用上次成员**（按设备 MAC 记粘性），否则对话历史断裂。粘性记录：Redis `pool:multimodal:sticky:{mac}` → member_id。

### 3.4 配置下发改动

- `POST /config/server-base` 的返回体新增 `share_pool` 段（Java ConfigServiceImpl.getConfig 组装）：
  ```json
  "share_pool": {
    "tts": [{"name":"key1","config":{"api_key":"..."},"threshold":10}, ...],
    "llm": [...],
    "multimodal": [{"name":"app1","config":{"app_id":"...","api_key":"...","workspace_id":"..."},"threshold":10}, ...]
  }
  ```
- Python config_loader 保留该键（与 redis 键同批基础设施键处理，有现成分支模式）
- 缓存：池表变更 → `redis-cli DEL server:config`（沿用 sys_params 变更惯例）
- **key 加密**：现有 ai_model_config.config_json 明文存 key，池成员表沿用同一脱敏/掩码模式（ModelConfigServiceImpl maskSensitiveFields 先例），管理端展示掩码、Python 端取明文

---

## 4. 管理端模块接入方案（Java + 前端）

### 4.1 Java 新模块 `modules/pool/`（照 order 模块四件套模板）

- `controller/PoolController.java`：`@RestController @RequestMapping("/pool")`，登录即可（照 GoodsController 风格：无权限注解）；六件套：GET /pool/page、GET /pool/info/{id}、POST /pool/create、PUT /pool/update/{id}、DELETE /pool/delete/{id}、GET /pool/{id}/members + 成员 CRUD
- 若要对齐"仅超管可见"：前端 hasAdminRole 控制路由即可（现有 L2 层），后端可加 `@RequiresPermissions("sys:role:superAdmin")` 与 SysParamsController 同款
- `service/PoolService.java`（Map 直传或实体，照 OrderShopService 风格）+ `dao/PoolMapper.java` + `entity/`
- 池变更后清缓存：`redisUtils.delete("server:config")`

### 4.2 Liquibase

- 新增 `db/changelog/20261025XXXX.sql`（上面 §2.2 两表）
- `db.changelog-master.yaml` 追加 include（照 891-898 行 202610232300 样板）

### 4.3 前端（console-v2）

- 新页面 `views/admin/Pools.vue`（池列表 + 成员抽屉，样式照 Agents.vue/Params.vue 范式）
- 接入点三处：
  1. `main.js` 路由：`{ path: '/admin/pools', component: AdminPools }`（照 61-82 行）
  2. `DockNav.vue` adminItems 加 `{ to: '/admin/pools', icon: 'share', label: '共享池' }`（照 123-136 行）
  3. `lib/api.js` adminApi 加 pool 六件套（照 338 行起）
- 角色页 PERM_GROUPS 可不加（细粒度权限点后端无拦截，加了只有展示意义——权限测试文档的已知 Gap）

---

## 5. 现状统计（用户要求的"池内 API 连接数量"）

### 5.1 每个 API 的 key 数量现状（测试环境）

| 池 | 模型 | key/app 数量 | 备注 |
|---|---|---|---|
| LLM 池 | DeepSeek | **1 把 key** | 池当前不可切（1 个成员） |
| TTS 池 | 千问TTS-Flash | 1 把 | 默认模型 |
| TTS 池 | 豆包声音复刻 + 豆包v3 HTTP | **共用 1 把 key**（d9f77dba...） | 同账号同配额，两模型互为成员才有意义 |
| TTS 池 | 百炼全模态 | 1 个 app | 也是全模态池成员 |
| 全模态池 | 百炼 app mm_8e05... | **1 个 app** | 池当前不可切 |
| VLLM | 智谱视觉AI | 0（脏数据） | 见 §1.1 结论 2 |

### 5.2 实际连接数（测试环境）

- 设备：3 台，全部 1 天内活跃
- 每台设备占用：1 个 WS 连接 + 1 个 TTS 实例 + 1 个 LLM 实例（duplex 设备另加 1 个百炼 WS 长会话）
- 峰值并发估算：3 台同时对话 = TTS 最多 3 并发合成、LLM 最多 3 并发流、全模态最多 3 个会话
- 阈值建议（第一版）：TTS 每 key 10、LLM 每 key 10、全模态每 app 10；管理端可调，测试环境想验证切换就把阈值调到 1

---

## 6. 落地任务拆分（给执行 agent，含优先级）

| # | 任务 | 涉及文件 | 优先级 |
|---|---|---|---|
| 1 | 提醒用户修正测试库智谱视觉AI 脏配置（执行前） | DB 手工 | P0 |
| 2 | Liquibase 两表 + master include | changelog | P0 |
| 3 | Java pool 模块四件套 + 缓存清理 | modules/pool/* | P0 |
| 4 | server-base 下发 share_pool 段（含掩码/明文策略） | ConfigServiceImpl | P0 |
| 5 | Python 通用 PoolGate（信号量+成员轮询+Redis 计数自愈） | core/providers/ 新建 | P0 |
| 6 | TTS 池接入（换 key 重试，照 tts_api_pool_design.md §3） | tts/base.py + tts_pool.py | P1 |
| 7 | LLM 池接入（openai + AliBL 两入口） | llm/base.py | P1 |
| 8 | 全模态池接入（最少连接+MAC 粘性） | aliyun_multimodal.py | P1 |
| 9 | 前端 Pools.vue + 路由/DockNav/api.js 三接入点 | console-v2 | P0 |
| 10 | 验收：阈值调 1 → 模拟并发 → 观察切换日志与回落行为 | 测试服 | P1 |

---

## 7. 验收基线

1. 管理端可建池/加成员/设阈值，列表与编辑正常（六件套全绿）
2. 阈值切换：把某池成员 threshold 设为 1，同池并发 2 → 第 2 个请求日志显示走成员 B，且无 4xx 冒烟
3. 计数器自愈：kill Python 进程重启后，Redis 槽位计数不泄漏（TTL 生效），请求正常
4. 单成员全失败：TTS 回落 EdgeTTS 提示音、LLM 走现有"有点忙"、全模态会话报错不崩
5. duplex 设备重连：粘性生效，复用同一百炼 app，对话不串
6. 缓存一致性：改池配置 → 清 server:config → 新连接生效，无需重启

## 8. 风险与备忘

- **明文 key**：池成员表沿用现有明文+掩码展示模式；若要加密需引入现有 AES（历史：登录 sm2 有 AES 先例），第一版不做
- **全模态换成员=换 app**：对话历史按 app 隔离，粘性是必须项不是优化项
- **生产与测试的 key 不同**：池配置属测试服，推送生产时池成员需重新录入（同 sys_params 惯例）
- **SSH 连接提醒**：直连 IP 会被拒，走 `sandyun` 别名（DNS+防护）

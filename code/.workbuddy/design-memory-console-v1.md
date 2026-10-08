# 架构设计：hermes 记忆模块接入小智控制台（v1）

| 项 | 内容 |
|---|---|
| 版本 | v1.0（任务 #2 交付） |
| 作者 | 高见远（Gao，架构师） |
| 状态 | 定稿（Q1~Q4、Q6 已拍板；本文档拍板 Q5 及 PRD 4.1 遗留项） |
| 上游 | PRD `prd-memory-console-v1.md`（任务 #1） |
| 下游 | #3 双引擎移植 / #4 记忆管理 API / #5 控制台页面 / #6 测试 / #7 部署 |

> 说明：本文档所有引用的事实（文件路径、行号行为、数据表、鉴权链路）均基于对镜像仓库 `G:/demo/21_xiaozhi/code-server-mirror` 与移植源 `G:/demo/21_xiaozhi/hermes-agent-main` 的实际侦察。实施者若发现偏差，以实际代码为准并回报 team-lead。

---

## 1. 实现方案（论证与拍板）

### 1.1 Q5 拍板：Python 内部管理 API（manager-api 经鉴权代理转发）

**结论：采用「xiaozhi-server 暴露内部管理 HTTP API，manager-api 以 ServerSecretFilter 鉴权代理转发给 Vue」方案；Java 不直读 SQLite。**

三个维度论证：

1. **并发安全（决定性）**：hermes `MemoryStore` 的锁语义是**进程内**的（`_shared` 连接注册表 + `threading.RLock`），SQLite 侧只有 WAL 兜底。Java 用 sqlite-jdbc 跨进程直写时，Java 进程完全绕过 RLock，所有"事务内先查后改"的复合操作（`update_fact` 的查→改→重抽实体→重建 bank；`record_feedback` 的查→钳制→改；`add_fact` 的幂等返回）在并发下都可能读到中间态。要安全就必须在 Java 侧重写一份 RLock + 幂等 + 信任分钳制 + 实体重抽取逻辑——这正是 PRD 明确反对的"重复实现规则"。Python 内部 API 复用 store 全部锁语义，两个进程的写全部经由同一把锁串行化，**天然正确**。
2. **部署复杂度**：xiaozhi-server 已有 aiohttp HTTP 服务（`core/http_server.py`，http_port 默认 8003，`/mcp/vision/explain` 已有带鉴权 handler 先例 `core/api/vision_handler.py`），新增一个 handler 不引任何新中间件、不新增端口；manager-api 已有 `RestTemplateConfig`（`common/config/RestTemplateConfig.java`）与 RAGFlowClient 外呼先例。Java 直读方案则要引 sqlite-jdbc 依赖 + 处理 SQLite 文件锁 + 两进程部署时序（文件权限、目录挂载），复杂度反而更高。
3. **鉴权复用**：manager-api 的 Shiro 过滤链（`modules/security/config/ShiroConfig.java`）已有 `server` 过滤器：`filterMap.put("/config/**", "server")`、`"/device/address-book/call"`、`"/agent/chat-history/report"` 等，由 `ServerSecretFilter` 校验 `server.secret`（`Constant.SERVER_SECRET`，xiaozhi-server 端就是 `manager-api.secret`，两端共享）。管理端 REST 全部落在 `oauth2` 下，鉴权零新增。

**链路设计**（管理面）：

```
manager-web (Vue)
  └─ HTTP (用户 oauth2 token)
      └─ manager-api /memory/** MemoryFactController [oauth2 + RequiresPermissions]
          └─ HTTP (service-to-service: Authorization: Bearer server.secret)
              └─ xiaozhi-server /api/memory/** MemoryManageHandler [AuthToken 校验 auth_key=server.secret]
                  └─ MemoryStore（进程内 RLock / WAL）—— 与设备对话 save/query 同一把锁
```

- **为何不把内部 API 直接暴露给 Vue**：Vue 侧拿不到也不会去拿 server.secret；且 8003 端口面向设备/公网（OTA/vision），管理操作必须走 manager-api 的统一鉴权与 `Result<T>` 包装，前端才能一个 `getServiceUrl()` 打天下。
- **转发路径规则**：manager-api 固定调用 `http://127.0.0.1:{http_port}/api/memory/...`（http_port 取自 `server.http_port` 系统参数，与 `/config/server-base` 同源；默认 8003）；超时 10s（写操作）→ 覆盖 SQLite busy timeout。
- **异常语义**：SQLite 库文件被占用/损坏等运行时故障，manager-api 返回 `Result.error(ErrorCode.INTERNAL_SERVER_ERROR, "记忆服务不可用")`，页面给"稍后重试"提示；**对话主链路完全不受影响**（xzx 的 save/query 是 provider 内直连，不经过 manager-api）。

### 1.2 holographic 移植策略：**拷贝改造（vendor 化），非适配层包装**

论证：

- holographic 的 `store.py`（约 310 行）依赖 `holographic.py`（HRR）+ 硬依赖 `hermes_state_wal.apply_wal_with_fallback` 与 `hermes_cli.sqlite_util.add_column_if_missing`。适配层包装意味着运行时 import hermes 包——把整个 hermes-agent 依赖带进 xiaozhi-server，两个巨型依赖树，不可接受。
- 包规模小（3 个文件、无第三方依赖、NumPy 可选），vendor 后按 xiaozhi provider 约定重写边界层（`mem_holographic.py` 约 300 行）即可；核心算法逐行保留（HRR 相位编码是确定性算法，改动即破坏语义）。
- 改造点收敛且明确：
  - `store.py`：剥离 hermes 依赖（WAL helper 改为内联 `PRAGMA journal_mode=WAL` + 失败降级；`add_column_if_missing` 改为内联 PRAGMA 检查）；schema 增 `status/agent_id/device_id/session_id` 四列；`add_fact/update_fact/remove_fact` 增加 `status` 与来源三元组参数。
  - `holographic.py`：**逐行原样拷贝**（含 NumPy 缺失降级 `_HAS_NUMPY`），仅改模块内 import。
  - `retrieval.py`：`_fts_candidates` / `list` 语义增加 `status='active'` 过滤（保证 rejected 永不参与注入）；其余保留。
  - 原 provider 的 `__init__.py` 是 hermes 的 `MemoryProvider`（agent 体系），**不移植**——xiaozhi 的 provider 边界层按 `MemoryProviderBase` 重写。
- 保留 hermes 原生降级路径：`holographic.py` 的 try-import NumPy + `retrieval.py` 的权重重分配（0.4/0.3/0.3 → 0.6/0.4/0）原样保留，防御性（Q6 已实测服务器 NumPy 1.26.4 可用，正常走完整 FTS5+Jaccard+HRR）。

### 1.3 数据命名：**每 Agent 一库**（PRD 4.1 遗留项拍板）

- 路径：`{project_dir}/data/memory/{agent_id}.db`（单文件 + 同目录 `-wal`/`-shm`）。xiaozhi-server 本地开发/远程部署路径一致（`get_project_dir()` 已存在）。
- 理由：最大化复用 hermes 单用户 store 代码（content UNIQUE、FTS5、bank 均按库独立，`agent_id` 列在单库方案下纯冗余）；Agent 增删即文件增删（`MemoryStore.release_all_under` 已支持按目录释放，Agent 删除时释放句柄后删文件）；备份/恢复按 Agent 粒度；锁粒度天然按 Agent 分片（不同 Agent 的记忆写不互斥）。
- **命名空间转换点**：`connection.py:_initialize_memory` 现传 `role_id=self.device_id`，改为 `role_id=self.agent_id`，同时通过 `init_memory(agent_id=..., device_id=..., session_id=...)` kwargs 传入来源三元组。`session_id` 为连接级 `self.session_id`（已有，见 connection.py L92）。
- mem0 的 `user_id` 同步改为 `self.role_id`（= agent_id），与 PRD 4.1 一致。

### 1.4 mem0 接入策略：**最小化 + 双向降级**

- 现有 `mem0ai/mem0ai.py` **不改写平台调用逻辑**（PRD 边界 §5）：`user_id=self.role_id`（agent_id）已随 1.3 生效。
- 增加一个返回配置状态的模块级函数：`get_status()` → `{"engine": "mem0", "available": bool, "reason": "未配置 API Key" | "已配置"}`，供内部管理 API 引擎徽标用（P0-3 明示"未配置"）。
- 管理页对 mem0：**P0 先做"只读列表 + 删除"**（对齐 Q7：排期紧张则降级为徽标——本设计把只读列表作为可降级项，接口层已预留，见 §3.2）。
- **控制台不做引擎回退**（PRD 4.3）：未配 key 时服务端仅告警、`save/query` 静默空返回，与现状行为一致。

---

## 2. 文件清单（新增 or 修改）

> 相对路径均基于 `G:/demo/21_xiaozhi/code-server-mirror/`。P0/P1 标记执行优先级；P1 文件在 #3/#4/#5 的 P0 验收通过后再实现。

### 2.1 Python（xiaozhi-server）

| # | 文件 | 类型 | 说明 |
|---|---|---|---|
| P-1 | `xiaozhi-server/core/providers/memory/mem_holographic/holographic.py` | 新增 | 从 `hermes plugins/memory/holographic/holographic.py` 原样 vendor（HRR 核心，含 NumPy 缺失降级） |
| P-2 | `xiaozhi-server/core/providers/memory/mem_holographic/store.py` | 新增 | 从 hermes `store.py` 拷贝改造：去 hermes 依赖（WAL/add_column 内联）；schema 增 `status/agent_id/device_id/session_id`；增 `set_fact_status/update_fact_trust/set_fact_sources` 管理操作；管理端查询分页/FTS/筛选封装 |
| P-3 | `xiaozhi-server/core/providers/memory/mem_holographic/retrieval.py` | 新增 | 从 hermes `retrieval.py` 拷贝改造：检索/列表一律 `status='active'`；其余算法原样 |
| P-4 | `xiaozhi-server/core/providers/memory/mem_holographic/mem_holographic.py` | 新增 | xiaozhi 边界层：`MemoryProvider(create_instance)` → `MemoryProviderBase` 实现；`init_memory(role_id=agent_id, llm, device_id, session_id, **kwargs)`；`save_memory`（auto_extract 正则抽取+来源落库）/`query_memory`（Top5 注入）；`get_store()` 供管理 handler 复用同实例 |
| P-5 | `xiaozhi-server/core/providers/memory/mem_holographic/__init__.py` | 新增 | 空（保持 `utils.memory.create_instance` 动态导入约定；provider 目录下无 `__init__.py` 也可以，但统一加空文件避免命名空间歧义） |
| P-6 | `xiaozhi-server/core/providers/memory/mem0ai/mem0ai.py` | 修改 | `get_status()` + 降级告警保持单次 error 日志（P0-3） |
| P-7 | `xiaozhi-server/core/connection.py` | 修改 | `_initialize_memory`：`role_id=self.device_id` → `role_id=self.agent_id`，kwargs 传 `agent_id/device_id/session_id`；其余 provider 兼容（见 §3.5） |
| P-8 | `xiaozhi-server/core/api/memory_handler.py` | 新增 | 内部管理 HTTP handler（aiohttp，仿 `vision_handler.py`）：AuthToken（auth_key）鉴权 + REST 路由 + 共享 store 注册表（`MemoryManageHandler`） |
| P-9 | `xiaozhi-server/core/http_server.py` | 修改 | 追加 `/api/memory/**` 路由（`MemoryManageHandler`） |
| P-10 | `xiaozhi-server/core/providers/memory/mem_local_short/mem_local_short.py` | 修改 | `get_status()` 返回 `{"engine": "mem_local_short", "available": true}`（P0 徽标） |
| P-11 | `xiaozhi-server/core/providers/memory/mem_report_only/mem_report_only.py`、`nomem/nomem.py` | 修改 | `get_status()` 同上（徽标一致性） |
| P-12 | `xiaozhi-server/config.yaml` / `config_from_api.yaml` | 修改 | `Memory` 段增加 `mem_holographic` provider 示例配置（对齐 PRD 4.3 参数）；注：API 模式（sandyun.top）以 Java 侧 ai_model_config 为准 |

### 2.2 Java（manager-api）

| # | 文件 | 类型 | 说明 |
|---|---|---|---|
| J-1 | `manager-api/src/main/java/xiaozhi/modules/memory/controller/MemoryFactController.java` | 新增 | `/memory/**` 管理端 REST（§3.2） |
| J-2 | `manager-api/src/main/java/xiaozhi/modules/memory/service/MemoryFactService.java` + `service/impl/MemoryFactServiceImpl.java` | 新增 | 业务编排：engine 分派（holographic→代理；mem0→平台 API；mem_local_short→只读档案） |
| J-3 | `manager-api/src/main/java/xiaozhi/modules/memory/client/MemoryInternalClient.java` | 新增 | 内部 API HTTP 客户端（`RestTemplate` + Bearer server.secret，仿 `RAGFlowClient`） |
| J-4 | `manager-api/src/main/java/xiaozhi/modules/memory/dto/MemoryFactDTO.java`、`MemoryAgentVO.java` | 新增 | DTO/VO（字段对齐 PRD 4.2） |
| J-5 | `manager-api/src/main/java/xiaozhi/modules/security/config/ShiroConfig.java` | 不改（勘误） | ~~filterMap.put("/memory/**", "server")~~ 勘误（team-lead 复核）：/memory/** 由既有默认链 `/**`→oauth2 保护（Vue 用户 token），挂 `server` 过滤器会挡掉用户请求（ServerSecretFilter 校验共享密钥而非用户 token）。实施时仅需通读 ShiroConfig 确认默认链覆盖，无代码改动 |
| J-6 | `manager-api/src/main/resources/db/changelog/2026xxxx_memory_provider.sql` + `db.changelog-master.yaml` | 修改 | 种子 `SYSTEM_Memory_mem_holographic`（fields 见 §3.3）+ master 追加 changeSet |
| J-7 | `manager-api/src/main/java/xiaozhi/modules/config/service/impl/ConfigServiceImpl.java` | 修改 | `buildModuleConfig` 对 `mem_holographic`：校验 agent_id 库存在性 + 注入 `db_dir`（默认 `data/memory/`） |
| J-8 | `manager-api/src/main/java/xiaozhi/modules/agent/vo/AgentVO.java` | 修改 | Agent 编辑页记忆引擎绑定沿用 `memModelId`（现有字段），仅加 mem0 未配 key 状态标记（可选） |
| J-9 | `manager-api/src/main/java/xiaozhi/modules/model/service/impl/ModelConfigServiceImpl.java` | 修改 | `getModelByIdFromCache` 对 mem0ai 增加 `apiKeyConfigured` 布尔（脱敏，不返回明文） |

### 2.3 Vue（manager-web）

| # | 文件 | 类型 | 说明 |
|---|---|---|---|
| V-1 | `manager-web/src/views/MemoryManagement.vue` | 新增 | 记忆管理页（参考 `KnowledgeBaseManagement.vue` 布局；P0 列表视图，P1 时间轴/审核池） |
| V-2 | `manager-web/src/apis/module/memory.js` | 新增 | API 封装（仿 `knowledgeBase.js`） |
| V-3 | `manager-web/src/router/index.js` | 修改 | 追加 `/memory-management` 路由 + `protectedRoutes` |
| V-4 | `manager-web/src/components/HeaderBar.vue` | 修改 | 一级菜单"记忆管理"（与知识库平级，Q3）；P1 加待审角标（Q7 可降级） |
| V-5 | `manager-web/src/i18n/zh_CN.js` | 修改 | 记忆管理页文案（中文本期硬编码亦可，但 i18n 是现有约定，推荐同页补齐） |
| V-6 | `manager-web/src/i18n/en.js`、`zh_TW.js` 等 | 修改 | 最小补齐（P1，允许顺延） |

### 2.4 说明

- **不改**：`MemoryProviderBase` 抽象（新增 provider 只需实现既有接口 + 可选 `get_status()`）；`mem_report_only/nomem` 行为；mem0 平台调用逻辑；ESP32 固件 / YH 协议。
- **不动**：`ai_model_config` / `selected_module` 机制本身——holographic 作为新 provider 接入，配置模型与现有 LLM/ASR/TTS 完全一致。

---

## 3. 接口设计

### 3.1 内部管理 API（xiaozhi-server 8003，`/api/memory/**`，服务间）

**鉴权**：`Authorization: Bearer {auth_key}`，`AuthToken.verify_token`（与 vision_handler 同机制，auth_key = server.secret 两端一致）。失败返回 `{"code": 401, "msg": "无效的认证token", "data": null}`。

**统一响应包**：`{"code": int, "msg": str, "data": object|null}`；code=0 成功。

| 方法 | 路径 | 入参 | 返回 data | 说明 |
|---|---|---|---|---|
| GET | `/api/memory/agents` | 无 | `[{agent_id, db_path, fact_count, pending_count}]` | 扫描 `data/memory/*.db`（全局 agent 表来自 Java，此处仅返回有库文件者） |
| GET | `/api/memory/{agent_id}/facts` | query：`keyword, category, status, trust_min, trust_max, start, end, page, size, sort_by(trust|created), order(asc|desc)` | `{total, items: [fact]}` | keyword 走 FTS5+Jaccard 组合检索 |
| GET | `/api/memory/{agent_id}/facts/{fact_id}` | path | `fact + entities[]` | 详情 |
| POST | `/api/memory/{agent_id}/facts` | body：`content*, category?, tags?, trust_score?` | `fact`（幂等：同 content 返回已有行） | 新建 |
| PUT | `/api/memory/{agent_id}/facts/{fact_id}` | body：`content?, category?, tags?, trust_score?` | `fact` | 编辑，内容变更触发实体重抽取 |
| DELETE | `/api/memory/{agent_id}/facts/{fact_id}` | path | `{"removed": true}` | 物理删除 |
| POST | `/api/memory/{agent_id}/facts/{fact_id}/feedback` | body：`{helpful: bool}` | `{fact_id, old_trust, new_trust, helpful_count}` | ±0.05/−0.10，钳制 [0,1] |
| POST | `/api/memory/{agent_id}/facts/{fact_id}/review` | body：`{action: "approve"\|"reject"}` | `fact`（status/trust 变更） | P1：approve→status=active 且 trust=固定 0.5（_APPROVE_TRUST 常量，不随 review_threshold 漂移）；reject→status=rejected。列表 status 参数：缺省=仅 active；显式 rejected=只看已驳回（支持 PRD 4.5 查看/恢复） |

### 3.2 对外管理 REST（manager-api 8002，`/memory/**`，用户 oauth2）

**统一响应包**：`Result<T>`（现有 `xiaozhi.common.utils.Result`，code=0 成功）；分页用现有 `PageData<T>`。

| 方法 | 路径 | 入参 | 返回 | 说明 |
|---|---|---|---|---|
| GET | `/memory/agents` | 无 | `Result<List<MemoryAgentVO>>` | 有记忆数据的 Agent（id、名称、引擎、条目数、待审数） |
| GET | `/memory/facts` | query：`agent_id*, keyword?, category?, status?, trust_min?, trust_max?, start?, end?, page?, size?` | `Result<PageData<MemoryFactDTO>>` | 分页列表（引擎分派：holographic→内部 API 代理；mem0→平台 API 只读映射；mem_local_short→友好提示） |
| GET | `/memory/facts/{fact_id}` | path + `agent_id` | `Result<MemoryFactDTO>`（含 `entities[]`） | 详情 |
| POST | `/memory/facts` | body：`agent_id*, content*, category?, tags?, trust_score?` | `Result<MemoryFactDTO>` | 新增 |
| PUT | `/memory/facts/{fact_id}` | body：`agent_id*, content?, category?, tags?, trust_score?` | `Result<MemoryFactDTO>` | 编辑 |
| DELETE | `/memory/facts/{fact_id}` | `agent_id` query | `Result<Void>` | 删除 |
| POST | `/memory/facts/{fact_id}/feedback` | body：`agent_id*, helpful*` | `Result<FeedbackVO>` | 反馈（P1-3） |
| POST | `/memory/facts/{fact_id}/review` | body：`agent_id*, action*` | `Result<MemoryFactDTO>` | P1 审核 |

> 引擎配置与切换**不新增接口**（PRD 4.6）：复用现有模型配置（`/model/**`）+ Agent 编辑（`memModelId`）接口。

### 3.3 provider 种子数据（J-6，对齐现有格式）

```sql
INSERT INTO `ai_model_provider` (id, model_type, provider_code, provider_name, fields, sort, status, created_at, creator, updated_at, updater) VALUES
('SYSTEM_Memory_mem_holographic', 'Memory', 'mem_holographic', 'Holographic 本地记忆', '[{"key":"db_dir","label":"数据库根目录","type":"string","default":"data/memory/"},{"key":"auto_extract","label":"自动抽取","type":"boolean","default":true},{"key":"default_trust","label":"默认信任分","type":"number","default":0.5},{"key":"min_trust_threshold","label":"检索/审核阈值","type":"number","default":0.3},{"key":"temporal_decay_half_life","label":"时间衰减半衰期(天,0=关)","type":"number","default":0}]', 4, 1, NOW(), 1, NOW(), 1);
```

### 3.4 mem0 平台 API 复用（只读列表）

- Java 侧通过现有 `MemoryClient` 等价调用（或直接 REST）：`GET /v1/memories?user_id={agent_id}` 只读列表；`DELETE /v1/memories/{memory_id}` 删除。P0 降级路径：仅徽标（`get_status()`），列表顺延 P1。
- mem0 结果无 trust/status/retrieval_count 概念，DTO 中相关字段置空，前端按引擎隐藏列。

### 3.5 agent_id 传递约定（Python 侧关键链路）

- 设备连接流程：`app.py:main()` 生成 `auth_key`（优先级 config → manager-api.secret → 随机，见 L50-62）→ `websocket_server` 校验 header（`AuthToken`）→ `connection.py:_initialize_private_config_async` 拉 private_config → `_initialize_memory` 时新增 `agent_id` 获取。
- **agent_id 来源**：`private_config` 中新增 `"agent_id": "{agent.id}"`，由 Java `ConfigServiceImpl.getAgentModels` 在返回 Map 中 `result.put("agent_id", agent.getId())` 注入（1 行修改，见 J-7）。
- `init_memory(role_id, llm, **kwargs)`：xiaozhi 侧 `_initialize_memory` 改为 `self.memory.init_memory(role_id=self.agent_id, llm=self.llm, agent_id=self.agent_id, device_id=self.device_id, session_id=self.session_id, ...)`；`role_id` 兼容 mem_local_short/mem0 的现有使用（`summaryMemory`、`save_to_file` 等 kwargs 原样透传）。
- **向后兼容**：`self.agent_id` 缺省时回退 `self.device_id`（防 API 侧尚未升级的过渡期），实现一行 `getattr(self, "agent_id", None) or self.device_id`。

---

## 4. 任务分解（映射 #3/#4/#5 边界）

### 任务 #3（工程师，双引擎移植）—— Python 全部

| 序 | 内容 | 交付 | 依赖 |
|---|---|---|---|
| 3.1 | vendor holographic.py（P-1） | 文件 + NumPy 缺失降级单测 | 无 |
| 3.2 | store.py 改造：去 hermes 依赖、schema 增 4 列、管理操作、管理查询 | P-2 + SQLite 自测脚本 | 3.1 |
| 3.3 | retrieval.py 改造：status 过滤 | P-3 | 3.2 |
| 3.4 | mem_holographic.py 边界层：init/save/query + 来源三元组 | P-4 | 3.2/3.3 |
| 3.5 | connection.py agent_id 注入改造（含 Java agent_id 下发约定） | P-7 | 3.4 |
| 3.6 | 内部管理 handler + http_server 路由 + 鉴权 | P-8/P-9 | 3.4 |
| 3.7 | mem0ai/mem_local_short 降级与 get_status | P-6/P-10/P-11 | 无（可与 3.1 并行） |
| 3.8 | 本地联调：模拟对话写库 + curl 内部 API 全操作 | 验收 A1 预演 | 3.1~3.7 |

### 任务 #4（后端 Java）—— 依赖 #3 完成（内部 API 就绪）

| 序 | 内容 | 交付 | 依赖 |
|---|---|---|---|
| 4.1 | MemoryInternalClient（Bearer server.secret + 超时/错误映射） | J-3 | #3 |
| 4.2 | DTO/VO + MemoryFactService 引擎分派骨架 | J-2/J-4 | 4.1 |
| 4.3 | MemoryFactController + ShiroConfig `server` 过滤链 | J-1/J-5 | 4.2 |
| 4.4 | provider 种子 + changelog | J-6 | 无（可与 4.1 并行） |
| 4.5 | ConfigServiceImpl agent_id 下发 + db_dir 注入 | J-7 | #3 |
| 4.6 | mem0 只读列表/删除 + mem_local_short 引导文案 | J-2/J-9 | 4.2 |
| 4.7 | 联调 curl 全接口（含 401/500 分支） | A2 预演 | 4.3~4.6 |

### 任务 #5（前端 Vue）—— 依赖 #4（REST 就绪）

| 序 | 内容 | 交付 | 依赖 |
|---|---|---|---|
| 5.1 | memory.js API 封装 + router + HeaderBar 一级菜单 | V-2/V-3/V-4 | #4 |
| 5.2 | MemoryManagement.vue P0 列表视图（Agent 选择/筛选/表格/抽屉/删除确认/引擎徽标/高亮） | V-1 | 5.1 |
| 5.3 | mem0/mem_local_short 自适应（列隐藏/引导文案） | V-1 | 5.2 |
| 5.4 | P1 时间轴视图 + 审核池 + 反馈按钮 + 待审角标 | V-1/V-4 | #6 P0 验收后 |

### 任务 #6（QA）—— P0 = 3.8 + 4.7 + 5.3 完成后

- A1~A6、A9、A10 全链路验证（含 demo Agent 真机对话）；P1 追加 A7、A8。
- 交叉项：远程部署（#7）前在本地镜像环境完整跑通。

### 任务 #7（部署）

- 本地镜像验证通过后 rsync/tar 同步 sandyun.top：Python systemd 重启（xiaozhi-server.service）、Java xiaozhi-manager-api.service 重启、Vue 构建产物刷新（**先探明 manager-web 在服务器是 dev 模式还是 build 产物服务，再定同步方式**——此为 #7 首项侦察）。
- 上线后复测 A1/A4/A6。

---

## 5. 共享知识（跨文件约定）

### 5.1 通用约定

- **错误码**：Java 复用现有 `ErrorCode`（`PARAMS_GET_ERROR` 参数错、`NO_PERMISSION`、`INTERNAL_SERVER_ERROR`）；Python 内部 API 统一 `{"code":0}` 成功，非 0 时 msg 中文可读。
- **分页**：page 从 1 起，size 默认 20 上限 100；`PageData<T>`（Java）与 `{total, items}`（Python）字段名对应。
- **日期格式**：存储层保持 SQLite TIMESTAMP（`YYYY-MM-DD HH:MM:SS`，hermes 语义）；API 层统一 `yyyy-MM-dd HH:mm:ss` 字符串透传（不引时区变换）；Java 的 `Date` 序列化按现有全局 jackson 配置。
- **agent_id**：文本主键，原样透传，**不做大小写/转义变换**；Python 侧以 `agent_id` 作为库文件名时做安全校验（拒绝 `..`、`/`、`\`，防路径穿越）。
- **trust_score**：一律 float，钳制 [0,1]（store `_clamp_trust`）；步进 0.05 是**前端**展示约定，后端不强制。
- **category**：`preference` / `profile` / `habit` / `event` / `general`；中文标签仅前端 i18n 映射。
- **status**：`active` / `rejected`（仅 holographic）；mem0 无此字段。
- **关键词高亮**：FTS 命中词由后端返回 `matched_terms[]`（从检索 token 集取交集），前端高亮；不做 HTML 注入式高亮（XSS）。

### 5.2 引擎分派约定

- Java `MemoryFactService` 入口统一判定 `agent.memModelId → config_json.type`：
  - `mem_holographic` → 内部 API 代理；
  - `mem0ai` → 平台 API 只读 + 删除（无 key → 徽标降级）；
  - `mem_local_short` → `{"engine":"mem_local_short","message":"压缩档案式记忆，暂不支持条目管理"}`；
  - `nomem`/`mem_report_only` → 空列表 + 提示。

### 5.3 并发与一致性

- **同源实时**（PRD 4.7）：管理写与对话读共用 `MemoryStore._shared` 连接 + RLock；Java 只经 HTTP 进入，无第二写入通道。
- **WAL**：vendor 后 WAL 由 store 内联启用（`PRAGMA journal_mode=WAL`，失败降级 DELETE 并告警）；`synchronous=NORMAL`，`busy_timeout=10000`。
- **连接生命周期**：`MemoryManageHandler` 用 `weakref.WeakValueDictionary[agent_id → MemoryStore]` 共享设备链路已开的 store；无实例时按配置新开（`db_dir` + agent_id）。

---

## 6. 待明确事项

| # | 事项 | 建议 | 影响 |
|---|---|---|---|
| 1 | manager-web 在 sandyun.top 的服务形态（dev 模式 vs build 产物） | #7 首项侦察 | 部署方式/回滚策略 |
| 2 | mem0 只读列表本期是否保留（Q7） | P0 先做徽标；列表属可降级项 | #4 排期 |
| 3 | Agent 删除时是否级联删除 `data/memory/{agent_id}.db` | 建议保留（记忆不可恢复，删 Agent ≠ 删记忆） | 部署/数据治理 |
| 4 | 时间轴/审核流 P1 排期是否与 #6/#7 并行 | 建议 P0 验收后启动，避免阻塞上线 | #6/#7 排期 |
| 5 | 待审角标刷新策略（轮询 vs WebSocket 推送） | v1 轮询 30s + 页面内刷新 | 前端工作量 |

---

## 附：关键侦察事实（供实施者引用，避免重复探路）

- xiaozhi-server 记忆链路：`app.py:main` → `WebSocketServer` → `connection.py:_initialize_private_config_async`（`/config/agent-models` 取 private_config，L800-957）→ `_initialize_memory`（L959-999）→ `MemoryProviderBase.init_memory(role_id=self.device_id)`（L963-968）→ `query_memory`（L1115-1119，`future.result()` 阻塞等待）→ `dialogue.get_llm_dialogue_with_memory`（`<memory>...</memory>` 注入，`core/utils/dialogue.py` L114-121）。
- provider 动态加载：`core/utils/memory.py:create_instance` 按 `core/providers/memory/{name}/{name}.py` 约定（`name=type`），`modules_initialize.py` L65-77 读取 `Memory.{name}.type`。
- manager-api：Spring Boot 8002，Shiro 过滤链 `modules/security/config/ShiroConfig.java`（`/config/**`→server，`/**`→oauth2）；`ConfigServiceImpl.getAgentModels` 是 private_config 唯一来源，`agent.getMemModelId()` → `ai_model_config`（type=memory）→ `selected_module.Memory`。
- holographic vendor 源：`hermes-agent-main/plugins/memory/holographic/{store,retrieval,holographic}.py`；hermes 专属依赖点：`hermes_state_wal.apply_wal_with_fallback`（store.py L128）、`hermes_cli.sqlite_util.add_column_if_missing`（L133）。
- 现有 provider 种子：`db/changelog/202504082211.sql`（`SYSTEM_Memory_mem0ai/nomem/mem_local_short`）；新增按 `db.changelog-master.yaml` changeSet 格式（`202609172100.sql` 是最新样例）。
- 服务器已验证：NumPy 1.26.4 + SQLite FTS5 可用 → 完整 FTS5+Jaccard+HRR，无需降级路径（代码仍保留防御）。
- 前端 i18n：`manager-web/src/i18n/{zh_CN,en,...}.js`；菜单在 `components/HeaderBar.vue`（`routerPaths` + `featureStatus`），路由保护在 `router/index.js:protectedRoutes`。

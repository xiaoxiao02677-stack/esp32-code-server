# 需求说明：将 /cc/ 控制台功能与 API 全量迁移至 admincc 管理台

> 版本：v1.0 · 生成日期：2026-10-08
> 配套：前序 `PROJECT-REQUIREMENTS.md`、`PROJECT-REQUIREMENTS-2.md`、`PROJECT-HANDOFF.md`
> 目标：把部署于 `/cc/` 的 **cc-console** 的全部业务功能与后端 API 集成逻辑，原样迁移到下一代管理台 **admincc**（即 `console-v2` 的 admin 构建）。

---

## 0. 需求重述（清晰话术）

> 将现有 `/cc/`（cc-console）管理台的全部**业务功能**与**后端 API 集成**（并非页面外观），完整迁移到 **admincc** 管理台（项目 `console-v2`，发布路径 `/admincc/`）。
>
> - **迁移内容**：所有页面交互逻辑、Vue 组件、状态管理、以及全部接口调用（约 80+ 端点，覆盖智能体 / 音色 / 聊天 / 记忆 / 知识库 / 模型 / 设备 / 系统参数 / 用户 / 模板 / OTA / 数据字典 / 替换词 / 服务器节点 / MCP 接入点 / 链路模拟 / API 调试）。
> - **明确排除**：cc-console 的**视觉装饰层**——kawaii 主题样式、`src/styles/` 目录、动画类（`fade-in-up` / `stagger-item` / `hover-glow`）、卡片外观等；admincc 保留自身 UI 外壳（TopBar / DockNav / DataTable / StatCard / Toasts）与主题。
> - **验收目标**：admincc 在功能与接口行为上与 `/cc/` 完全对等，且不依赖 cc-console 的独立样式文件。

---

## 1. 源与目标（架构界定）

### 1.1 源：`/cc/` = cc-console
- 形态：**单文件** `G:/demo/21_xiaozhi/cc-console/src/App.vue`（约 2400 行），16 个功能页 + API 调试页（+ 后续追加的 MCP 接入点页、链路模拟器）。
- 接口层：统一 `this.api(path, opts)`，基址 `/yuhe`，SM2 登录鉴权。
- 装饰层（**不迁移**）：`src/styles/`、kawaii 卡片/动画 CSS。

### 1.2 目标：`admincc` = console-v2 的 admin 构建
- 形态：**组件化** Vue3 应用 `G:/demo/21_xiaozhi/console-v2/`：
  - `src/views/admin/*.vue` 管理端页面（现有：Home / Knowledge / Templates / Users）。
  - `src/views/customer/*.vue` 顾客端（Devices / Home / Points / Voices）——本次**不迁移顾客端**，仅管理端。
  - `src/lib/api.js`：统一接口层 `api` + `authApi` + `customerApi` + `adminApi`，基线注明"源自 cc-console/contract/openapi.json（173 接口）"。
  - `src/components/`：UI 外壳（TopBar / DockNav / DataTable / StatCard / Toasts）。
- 构建与发布：`vite.config.js` 中 `mode==='admin'` → base `/admincc/`、outDir `dist-admin`；由 `scripts/deploy.py` 发布到 `/var/www/console-v2/admin`，nginx 以 `/admincc/` 提供（已验证 `https://sandyun.top/admincc/`）。

---

## 2. 现状盘点

### 2.1 cc-console 功能面（16 页 + 扩展，含 API 端点）
| 页（key） | 核心端点（来自 App.vue 实测） |
|---|---|
| overview 总览 | stats 聚合 |
| agents 智能体 | `/agent/list`、`/agent/{id}`(GET/PUT/DELETE)、`POST /agent`、`POST /device/bind/{agentId}[/{code}]`、`/agent/{id}/sessions` |
| voices 音色试听 | `/models/list?modelType=TTS`、`/models/{id}/voices`、`/models/ttsPreview`、`/ttsVoice`(GET/PUT/POST/DELETE)、`/voiceClone/play/{id}` |
| chat 聊天记录 | `/agent/{id}/sessions`、`/agent/{id}/chat-history/{sid}`、`POST /agent/audio/{id}`、`DELETE /agent/{id}/chat-history/{sid}` |
| memory 记忆管理 | `/memory/agents`、`/memory/facts`(GET/POST/DELETE)、`/memory/facts/{id}/feedback`、`/memory/facts/{id}/review`、`PUT /models/Memory/{code}/{engine}` |
| knowledge 知识库 | `/datasets`(GET/POST/DELETE)、`PUT /datasets/{id}` |
| models 模型管理 | `/models/list`、`/models/names?modelType=`、`/models/{id}`、`/models/{type}/provideTypes`、`POST/PUT/DELETE /models/...`、`/models/modelTest`、`PUT /models/enable/{id}/{status}` |
| devices 设备管理 | `/admin/device/all`、`POST /device/bind/{agentId}`、`PUT /device/update/{id}`、`POST /device/manual-add`、`POST /device/unbind` |
| params 系统参数 | `/admin/params/page`、`PUT /admin/params` |
| users 用户管理 | `/admin/users`、`PUT /admin/users/changeStatus/{status}` |
| templates 智能体模板 | `/agent/template/page` |
| ota OTA 固件 | `/otaMag`(GET)、`DELETE /otaMag/{id}` |
| dicts 数据字典 | `/admin/dict/type/page`、`/admin/dict/data/type/{type}`、`POST /admin/dict/data/delete` |
| correctwords 替换词 | `/correct-word/file/list`、`POST/PUT/DELETE /correct-word/file[/{id}]` |
| servers 服务器节点 | `/admin/server/server-list` |
| apis API 调试 | 142 接口（lib/apiCatalog.js，任意原始请求） |
| （扩展）MCP 接入点 | `/agent/mcp/address/{id}`、`/agent/mcp/tools/{id}`、`/agent/mcp/test/{id}` |
| （扩展）链路模拟器 | `/models/asrRecognize`、`/models/llmPreview`、`/models/ttsPreview` |

### 2.2 admincc 已具备（避免重复建设）
- 页面：`views/admin/Home.vue`、`Knowledge.vue`、`Templates.vue`、`Users.vue`。
- `adminApi` 已覆盖：`devicePage`、`template*`(list/page/detail/CRUD/batch)、`tagList`、`user*`(page/resetPassword/delete/changeStatus)、`dataset*`(page/detail/CRUD/docs/ragModels)、`modelList`、`memoryAgents`、`memoryFacts`。
- `authApi`：SM2 登录鉴权（与 cc-console 契约一致）。

### 2.3 缺口（待补建）
- **待建 admin 视图**：Agents、Voices、Chat、Memory、Models、Devices、Params、Ota、Dicts、CorrectWords、Servers、ApiDebug、（可选）Mcp、LinkSimulator。
- **待补 `adminApi` 方法**：见 §4。

---

## 3. 迁移映射表（每页 → admincc 视图 + 状态）

| cc-console 页 | admincc 视图 | 状态 |
|---|---|---|
| overview | `views/admin/Home.vue`（已存在，需对齐统计项）| 对齐 |
| agents | `views/admin/Agents.vue`（新建）| 待建 |
| voices | `views/admin/Voices.vue`（新建）| 待建 |
| chat | `views/admin/Chat.vue`（新建）| 待建 |
| memory | `views/admin/Memory.vue`（新建）| 待建 |
| knowledge | `views/admin/Knowledge.vue`（已存在，对齐）| 对齐 |
| models | `views/admin/Models.vue`（新建）| 待建 |
| devices | `views/admin/Devices.vue`（新建，区分顾客端 Devices）| 待建 |
| params | `views/admin/Params.vue`（新建）| 待建 |
| users | `views/admin/Users.vue`（已存在，对齐）| 对齐 |
| templates | `views/admin/Templates.vue`（已存在，对齐）| 对齐 |
| ota | `views/admin/Ota.vue`（新建）| 待建 |
| dicts | `views/admin/Dicts.vue`（新建）| 待建 |
| correctwords | `views/admin/CorrectWords.vue`（新建）| 待建 |
| servers | `views/admin/Servers.vue`（新建）| 待建 |
| apis | `views/admin/ApiDebug.vue`（新建，复用 apiCatalog）| 待建 |
| mcp | `views/admin/Mcp.vue`（新建，可选）| 待建 |
| linksim | `views/admin/LinkSimulator.vue`（新建，可选）| 待建 |

> 路由：admincc 现有 `DockNav.vue` 的 `adminItems`（`/admin`、`/admin/templates`、`/admin/knowledge`、`/admin/users`）需扩展为完整菜单，对应上表路由。

---

## 4. API 迁移清单（adminApi 待补方法）

以下为 cc-console 已用、但 `adminApi` 尚未声明的方法，按域分组，**照 cc-console 契约补入 `src/lib/api.js`**：

- **智能体**：`agentList`、`agentDetail(id)`、`createAgent(body)`、`updateAgent(id,body)`、`deleteAgent(id)`、`bindDevice(agentId,code?)`、`agentSessions(id)`、`agentMcpAddress(id)`、`agentMcpTools(id)`、`agentMcpTest(id)`。
- **聊天**：`chatHistory(agentId,sid)`、`playChatAudio(audioId)`、`deleteChatSession(agentId,sid)`、`agentAudio(audioId)`。
- **音色 / TTS**：`ttsModels()`、`modelVoices(id)`、`ttsPreview({modelId,voice,text})`、`ttsVoicePage/Detail/Create/Update/Delete`、`voiceClonePlay(id)`。
- **记忆**：`memoryFactsPage(params)`（已有）、`createFact`、`deleteFact(id)`、`factFeedback(id,helpful)`、`factReview(id,action)`、`memoryEngineConfig(engine)`(PUT)。
- **模型**：`modelNames(type)`、`modelDetail(id)`、`modelProvideTypes(type)`、`createModel/_updateModel/deleteModel`、`modelTest(id)`、`enableModel(id,status)`。
- **设备**：`deviceAll(params)`（已有）、`deviceUpdate(id,body)`、`deviceManualAdd(body)`、`deviceUnbind(body)`、`boundDevices(agentId)`。
- **系统参数**：`paramPage`、`updateParam(body)`。
- **OTA**：`otaPage`、`deleteOta(id)`。
- **数据字典**：`dictTypePage`、`dictData(type)`、`deleteDictData(id)`。
- **替换词**：`correctWordList`、`createCorrectWord`、`updateCorrectWord`、`deleteCorrectWord(id)`。
- **服务器**：`serverList`。
- **链路模拟**：`asrRecognize(modelId)`、`llmPreview({modelId,text,systemPrompt})`。

> 复用：`authApi`（登录）、`customerApi` 无需迁移；`api.js` 基座 `/yuhe`、SM2 鉴权、业务码 `code===0` 判定均直接复用，**零修改**。

---

## 5. 实施方法（技术约定）

- **FR-M.1** 每页一个 `views/admin/<Page>.vue`，组件化拆分（不保留 cc-console 单文件结构）。
- **FR-M.2** 全部接口调用经 `src/lib/api.js` 的 `adminApi`/`api`，**禁止**在视图内硬编码 `fetch`/`axios` 直连。
- **FR-M.3** 缺失接口按 §4 补入 `adminApi`（或按域拆 `modelsApi`/`deviceApi` 等），保持与 cc-console 契约一致。
- **FR-M.4** 登录/鉴权复用 `authApi`（SM2 加密、token 存储），与 `/cc/` 行为一致。
- **FR-M.5** **禁止引入** cc-console 的 `src/styles/` 与 kawaii 类（`fade-in-up`/`stagger-item`/`hover-glow`/卡片外观）；admincc 使用自身 `components/` 外壳与样式。
- **FR-M.6** 路由与 `DockNav.vue` 菜单扩展为 §3 全量菜单；激活项高亮。
- **FR-M.7** API 调试页（`ApiDebug.vue`）复用 `lib/apiCatalog.js`（142 接口）做原始请求面板，保持与 `/cc/` 一致。
- **FR-M.8** 构建校验：`npm run build -- --mode admin` 产出 `dist-admin`，且不含 kawaii CSS 引用；发布沿用 `scripts/deploy.py`（→ `/admincc/`）。

---

## 6. 验收标准

- [ ] **功能对等**：admincc 各页可完成与 `/cc/` 相同的读写操作（对拍关键用例：智能体增改删、音色试听/CRUD、聊天删会话、记忆增删反馈、模型启停/测试、设备绑定/解绑、参数保存、用户禁用、OTA/字典/替换词增删、服务器列表、MCP 地址/工具、链路模拟出声）。
- [ ] **接口一致**：admincc 发起的请求路径/方法/参数与 cc-console 契约一致（可抓包比对）。
- [ ] **无样式泄漏**：grep `fade-in-up|stagger-item|hover-glow|kawaii` 在 `console-v2/src` 零命中。
- [ ] **构建产出**：`dist-admin/index.html` 基准路径为 `/admincc/`。
- [ ] **部署可达**：`https://sandyun.top/admincc/` 返回 200 且功能可用。

---

## 7. 风险与待确认

1. **范围确认**：是否要求 100% 功能对等（含 API 调试 142 接口、链路模拟器、MCP 页）？本文默认**全量迁移**；若只需核心 16 页可裁剪。
2. **已存在页对齐**：Users/Templates/Knowledge/Home 已在 admincc 部分实现，需做**功能对齐审计**（而非覆盖），确保与 cc-console 行为一致；其中 cc-console 的 Templates 仅列表，admincc 已有 CRUD——保留 admincc 更全实现。
3. **接口盲区**：§4 部分端点（如 `device/manual-add`、`asrRecognize`、`agent/mcp/test`）需确认 manager-api 实际路由与 cc-console 完全一致（契约基线已声明 173 接口，预期一致）。
4. **部署耦合**：admincc 与 cc-console 将**并行存在**于服务器（`/admincc/` 与 `/cc/`）；迁移期可接受双台共存，验收后再决定是否下线 `/cc/`（见 `PROJECT-HANDOFF.md` 原控制台停用方案）。
5. **样式边界**：顾客端 `views/customer/*` 不在本次范围，仅管理端。

---

## 8. 验收总表

| 编号 | 验收点 | 状态 |
|---|---|---|
| M.1 | 全量 admin 视图建成（见 §3）| ☐ |
| M.2 | adminApi 补齐 §4 全部方法 | ☐ |
| M.3 | 关键用例与 /cc/ 行为对等 | ☐ |
| M.4 | console-v2/src 无 kawaii CSS 泄漏 | ☐ |
| M.5 | dist-admin 基准 /admincc/ 且线上可达 | ☐ |

> 下一步：确认 §7 范围（全量 vs 核心 16 页）后，按「补齐 adminApi → 逐页建视图（对齐已存在页）→ 扩展菜单 → admin 构建部署」顺序实施。

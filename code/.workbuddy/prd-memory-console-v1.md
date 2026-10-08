# PRD：hermes 记忆模块接入小智控制台（v1 增量）

| 项 | 内容 |
|---|---|
| 版本 | v1.0（增量 PRD，基于现有小智后台） |
| 作者 | 许清楚（Xu，产品经理） |
| 状态 | 待评审 |
| 关联任务 | #2 架构设计 / #3 双引擎移植 / #4 记忆管理 API / #5 控制台页面 / #6 测试 / #7 部署 |
| 源码依据 | hermes-agent-main `plugins/memory/holographic`、`plugins/memory/mem0`；xiaozhi-server `core/providers/memory/*`；manager-api（Spring Boot, 8002）；manager-web（Vue） |

---

## 1. 背景与问题

小智（ESP32 语音设备）后台 xiaozhi-server 已有 `MemoryProviderBase` 抽象（`save_memory` / `query_memory` / `init_memory`），现有实现为 mem0ai（平台版）、mem_local_short（900 字压缩档案，全文一块、不可条目化管理）、mem_report_only、nomem。真实场景中，服务器需按 Agent 记住设备用户的姓名、习惯与历史，但存在三个问题：

1. **记忆不可见**：mem_local_short 是一整段 YAML 档案，管理员看不到"小智到底记住了什么"，无法逐条纠错（ASR 误识别的名字一旦写入会长期污染对话）。
2. **记忆不可管**：控制台（manager-web）没有任何记忆管理页面；无法删除错误记忆、无法切换/配置记忆引擎。
3. **记忆不可信**：没有质量信号。ASR 噪声、抽取幻觉与真实偏好混在一起，无法区分、无法过滤。

hermes 记忆模块（移植源）提供了成熟解法：holographic 引擎（SQLite + FTS5 + 信任分 + 实体消解 + HRR 组合检索，零外部依赖）与 mem0 引擎（LLM 语义抽取）。本 PRD 定义将其接入小智并在控制台提供"可见、可管、可信"的记忆管理全家桶。

**已拍板决策**（主理人确认，不再讨论）：
- 双引擎：holographic 为主力（本地零依赖），mem0 为可选 provider（需平台账号）。
- 控制台全家桶：管理页 + 引擎配置切换 + 记忆时间轴 + 低信任分审核工作流。
- 镜像开发（`G:/demo/21_xiaozhi/code-server-mirror`）→ 远程部署（sandyun.top，测试通过后同步）。
- 试点 Agent：demo（`03532a34...`，已绑定真实设备用户）。

## 2. 产品目标与用户故事

### 2.1 产品目标

| 目标 | 衡量 |
|---|---|
| 记忆可见：管理员能看到每个 Agent 下每一条记忆 | 管理页可 100% 列出、搜索 holographic 全部记忆条目 |
| 记忆可管：增删改查、引擎切换均可在控制台完成 | 全部管理操作无需登录服务器改配置/文件 |
| 记忆可信：低质量记忆有信号、可审核、可过滤 | 信任分 < 阈值的条目进入待审池；驳回后不再影响设备回答 |

### 2.2 用户故事

- **US1（管理员·纠错）**：作为管理员，我想在控制台按 Agent 查看、搜索、编辑、删除设备用户的记忆条目，以便纠正 ASR 误识别（"张三"被记成"张山"）和清理过期信息，而不必登服务器改文件。
- **US2（设备用户·被记住）**：作为设备用户，我希望隔天再和小智聊天时，它仍记得我的名字和偏好，不用每次重新自我介绍。
- **US3（管理员·质量把关）**：作为管理员，我想让低信任分的记忆自动进入审核队列，通过/驳回后决定它是否参与小智的回答，避免噪声记忆污染对话。
- **US4（管理员·引擎适配）**：作为管理员，我想在控制台为不同 Agent 切换记忆引擎（holographic / mem0 / mem_local_short）并调整参数（默认信任分、自动抽取开关），以适配"数据不出本地"与"云端语义"两种场景。
- **US5（管理员·溯源）**：作为管理员，我想通过时间轴查看某 Agent 的记忆形成过程，以便理解"小智为什么会记住这些"、向用户解释记忆来源。

## 3. 需求池

### P0（本期必做，缺一不可上线）

| # | 需求 | 说明 |
|---|---|---|
| P0-1 | holographic 引擎移植（provider 名 `mem_holographic`） | 按 xiaozhi `MemoryProviderBase` 接口封装 hermes holographic：SQLite + FTS5 + 信任分 + 实体消解；`auto_extract` 从对话自动抽取事实；检索走"FTS5 + Jaccard（+HRR 可选）+ 信任分加权" |
| P0-2 | 记忆命名空间与多 Agent 隔离 | holographic 原为单用户库；接入后必须按 Agent 隔离（建议每 Agent 一个 SQLite 文件，见 4.1），试点 demo Agent 生效 |
| P0-3 | mem0 引擎接入与优雅降级 | 保留/规范现有 mem0ai 平台版接入；未配置 api_key 时控制台明示"不可用"、服务端仅告警、不阻塞对话 |
| P0-4 | 记忆管理页基础 CRUD | 按 Agent 查看/搜索/筛选/新增/编辑/删除记忆条目，字段见 4.2 |
| P0-5 | 引擎配置与切换 | 沿用 `ai_model_config`（type=memory）+ Agent 绑定机制，控制台可视化配置 holographic/mem0 参数并切换 |
| P0-6 | 记忆注入链路验证 | 设备对话 `query_memory` → `get_llm_dialogue_with_memory` 注入，跨会话记忆可感知（验收 A1） |

### P1（本期尽力，允许顺延）

| # | 需求 | 说明 |
|---|---|---|
| P1-1 | 记忆时间轴可视化 | 管理页内时间轴视图，交互见 4.4 |
| P1-2 | 低信任分审核工作流 | 待审池 + 通过/驳回/删除 + 侧边栏角标，规则见 4.5 |
| P1-3 | 信任分人工反馈 | 管理页对条目标记"有用/无用"（+0.05 / −0.10），与运行时反馈同源 |
| P1-4 | 实体聚合视图 | 按实体（人名/事物）聚合查看相关记忆（对齐 hermes probe/related 能力） |

### P2（本期不做，记录备选）

- 记忆导出/导入（JSON/CSV）、批量操作
- 矛盾检测可视化（hermes contradict 工具）
- holographic ↔ mem0 记忆迁移工具
- 记忆统计看板（检索 Top 榜、活跃实体、增长趋势）
- mem0 条目编辑（v1 仅查看/删除，见 4.3）
- 全局/跨 Agent 共享记忆

## 4. 功能规格

### 4.1 总体架构与概念模型

**记忆命名空间（关键设计决策）**：现状 xiaozhi `init_memory(role_id=self.device_id)` 按设备隔离记忆；产品目标是"按 Agent 记住用户偏好"。v1 规定：

- 记忆命名空间 = **Agent**（`agent_id`）。同一 Agent 绑定的多台设备共享记忆（家人换设备/换房间仍被记住）。
- holographic 建议每 Agent 一个 SQLite 文件（如 `data/memory/{agent_id}.db`），最大程度复用 hermes 单用户 store 代码、天然隔离、便于按 Agent 备份；备选单库加 `agent_id` 列。**由架构师在 #2 确认，两种方案对本 PRD 字段与交互无影响。**
- mem0 的 `user_id` 同步取 `agent_id`（替换现有 `role_id`）。
- 兼容性：mem_local_short 保持现状（按 role_id 存 YAML），不在本期改造范围。

**记忆条目数据模型**（在 hermes `facts` 表字段基础上，标注 ●新增）：

| 字段 | 类型 | 说明 |
|---|---|---|
| fact_id | int | 主键，Agent 库内自增 |
| content | text | 记忆内容，**Agent 库内唯一**（重复写入幂等返回已有 id） |
| category | text | 类型：`preference`（偏好）/ `profile`（个人档案）/ `habit`（习惯）/ `event`（事件）/ `general`（默认） |
| tags | text | 标签，逗号分隔 |
| trust_score | real | 信任分 0~1，新建默认 0.5；有用 +0.05 / 无用 −0.10，钳制在 [0,1] |
| status | text | ● `active`（生效）/ `rejected`（已驳回，不参与检索）——仅 holographic |
| agent_id | text | ● 所属 Agent（每 Agent 一库时隐含，单库时为列） |
| device_id | text | ● 产生该记忆的设备 |
| session_id | text | ● 来源会话（对应 xiaozhi `session_id`，时间轴/溯源用） |
| retrieval_count / helpful_count | int | 检索次数 / 被标记有用次数（沿用 hermes） |
| created_at / updated_at | timestamp | 创建/更新时间（沿用 hermes） |
| 实体（entities/fact_entities） | 关联表 | 内容中抽取的人名/事物及别名，详情页展示 |

**检索生效规则**（复用 hermes 语义）：仅 `status=active` 且 `trust_score ≥ min_trust_threshold`（默认 0.3，可配）的条目参与 `query_memory`；FTS5 + Jaccard（NumPy 存在时加 HRR）重排后按 相关性 × 信任分 取 Top N 注入对话。

### 4.2 记忆管理页（P0，manager-web 新增 `MemoryManagement.vue`）

**入口**：控制台新增一级菜单"记忆管理"（菜单位置与图标待确认，见 §7-Q3）。参考 KnowledgeBaseManagement 的布局风格。

**页面结构**：

1. **Agent 选择器**（顶部下拉）：仅列出绑定了记忆引擎且有记忆数据的 Agent，显示条目数；默认选中有数据的第一个 Agent（试点为 demo）。切换 Agent 即切换数据源。
2. **引擎徽标**：当前 Agent 所选引擎（holographic / mem0 / mem_local_short / 无），mem0 未配 key 时显示灰色"未配置"徽标（见 4.3）。
3. **筛选区**：
   - 关键词（走 FTS5 全文匹配，命中内容与标签，结果高亮）
   - 类型（category 下拉）、状态（active/rejected/全部）、信任分区间（滑杆 0~1）
   - 时间范围（创建时间起止）
4. **条目列表**（表格，默认按创建时间倒序，可切信任分排序，20 条/页）：

| 列 | 展示 |
|---|---|
| 内容 | 超长省略号，悬浮显示全文；关键词高亮 |
| 类型 | category 中文标签 |
| 标签 | 0~n 个 tag，超省略 |
| 信任分 | 进度条 + 数值；<0.3 红、0.3~0.7 黄、>0.7 绿 |
| 来源 | 设备名（无则"—"），悬浮显示 session_id |
| 检索次数 / 有用次数 | 数值 |
| 创建时间 | yyyy-MM-dd HH:mm |
| 状态 | active=生效 / rejected=已驳回 |
| 操作 | 编辑 / 删除 / 有用 / 无用（P1-3）/ 送审（P1-2） |

5. **新增/编辑抽屉**：内容（必填、Agent 内唯一校验）、类型、标签、信任分（0~1 步进 0.05）。编辑内容后系统重新抽取实体（沿用 hermes `update_fact` 语义）。
6. **删除**：二次确认弹窗，文案明示"删除后小智将不再引用该记忆，不可恢复"。

**mem0 引擎下的自适应**：管理页字段按引擎自适应——mem0 无信任分/状态/检索统计概念，隐藏相关列与操作，仅提供查看列表 + 删除（调 mem0 平台 API）；mem_local_short 引擎下显示引导文案"该引擎为压缩档案式记忆，暂不支持条目管理，可切换至 holographic"。**mem0 只读列表若因排期顺延，P0 允许降级为"仅显示配置状态徽标"**，但降级提示（P0-3）不可缺。

### 4.3 引擎配置与切换（P0）

**配置模型**：沿用现有 `ai_model_config`（type=memory）+ Agent 绑定（`selected_module`）机制，不新造配置体系。

- **provider 列表**：`mem_holographic`（新增）、`mem0ai`（现有）、`mem_local_short`（现有）、`mem_report_only` / `nomem`（现有，保持不动）。控制台"模型配置-记忆"区可新增/编辑 provider 配置。
- **holographic 配置项**（对齐 hermes 参数，括号内默认值）：`db 根目录`（data/memory/）、`auto_extract`（开）、`default_trust`（0.5）、`min_trust_threshold`（0.3）、`review_threshold` 审核阈值（0.3，P1 生效）、`temporal_decay_half_life`（0=关，高级项折叠）。
- **mem0 配置项**：`api_key`（密码框，脱敏回显）、平台地址（默认官方）。
- **Agent 绑定**：Agent 编辑页增加"记忆引擎"选择（默认全局默认 provider，Agent 级可覆盖）。
- **切换生效**：配置保存后，**新建设备连接生效**（xiaozhi 按 connection 加载 private_config），存量连接维持原引擎直至重连。控制台保存成功提示需包含该说明。

**mem0 优雅降级（P0-3，验收 A6）**：
- api_key 缺失/无效：控制台 provider 卡片显示"未配置 API Key，该引擎不可用"黄色警示；Agent 若绑定 mem0，管理页引擎徽标置灰并提示。
- 服务端：`use_mem0=False` 时仅记录一次 error 日志，`save/query` 静默返回空，**对话主链路零阻塞、零异常**。
- 不做自动引擎回退（不悄悄切到 holographic），由管理员显式切换——避免记忆悄悄落到另一个存储。

### 4.4 记忆时间轴（P1-1）

- **入口**：管理页右上"列表 / 时间轴"视图切换（同页签复用当前 Agent 与筛选条件）。
- **形态**：纵向时间轴，按创建时间倒序，按自然日分组（日期吸顶）。节点 = 记忆条目：图标按 category（偏好♥/档案👤/习惯🔁/事件📅/通用📌），颜色同信任分红黄绿。
- **节点交互**：悬浮显示内容摘要 + 信任分；点击展开详情卡（内容全文、标签、实体列表、来源设备/会话、检索/有用次数、创建&更新时间、"查看前后记忆"锚点）。
- **筛选**：与列表视图共用筛选器；时间轴支持日/周/月三种密度切换。
- **性能**：单 Agent 超过 500 条时分段懒加载（滚动加载）。

### 4.5 低信任分审核工作流（P1-2，仅 holographic）

**规则**：
- **进入待审**：满足其一即入待审池——① 新抽取/新建事实 `trust_score < review_threshold`（默认 0.3）；② 运行时或人工"无用"反馈使信任分跌破 `review_threshold`。
- 待审条目仍保留在库中，但因低于 `min_trust_threshold` 天然不参与检索（与 hermes 语义一致），无需额外屏蔽逻辑。
- **操作与语义**：
  - **通过**：`status=active` 且信任分提升至 `review_threshold + 0.2`（即 0.5，恢复为"默认可信"水位），立即参与检索；
  - **驳回**：`status=rejected`，永久退出检索与待审池，可在列表"已驳回"筛选下查看/恢复（恢复=通过语义）；
  - **删除**：物理删除。
- **入口与提醒**：管理页内"待审核(n)"页签（n 为当前 Agent 待审数）；控制台侧边栏"记忆管理"菜单显示待审总数角标。v1 不做站外推送/邮件。

### 4.6 API 概要（供 #4 后端实现参考，路径以架构师最终设计为准）

| 方法与路径 | 用途 |
|---|---|
| `GET /memory/agents` | 有记忆数据的 Agent 列表（id、名称、引擎、条目数、待审数） |
| `GET /memory/facts?agent_id&keyword&category&status&trust_min&trust_max&start&end&page&size` | 分页列表（keyword 走 FTS） |
| `GET /memory/facts/{fact_id}` | 详情（含实体列表） |
| `POST /memory/facts` | 新增（agent_id、content、category、tags、trust_score） |
| `PUT /memory/facts/{fact_id}` | 编辑（内容变更触发实体重抽取） |
| `DELETE /memory/facts/{fact_id}` | 删除 |
| `POST /memory/facts/{fact_id}/feedback` | `{helpful: bool}` 信任分 ± |
| `POST /memory/facts/{fact_id}/review` | `{action: "approve" \| "reject"}`（P1） |
| 引擎配置 | 沿用现有模型配置/Agent 绑定接口，不新增 |

权限沿用 manager-api 现有管理端鉴权，不新增角色。

### 4.7 数据与生效性约束（供 #2 架构设计输入）

- **同源实时**：管理端写操作必须作用于设备对话读取的同一数据源（SQLite/每 Agent 库），删除/驳回后下一次对话立即不引用；不允许"MySQL 镜像 + 定时同步"这类有延迟窗口的方案。
- **并发安全**：hermes store 使用 WAL + 进程内 RLock；Java 侧（若直读 SQLite，sqlite-jdbc 需开 WAL）或 Python 侧提供内部管理 API，均不得破坏该约束。架构二选一由 #2 决策。
- **部署**：SQLite 文件落 xiaozhi-server 数据目录（随代码同步至 sandyun.top），纳入现有备份策略；不引入新中间件。
- **降级依赖**：NumPy 缺失时 holographic 自动退化为 FTS+Jaccard（hermes 原生行为），功能可用，仅相似度精度下降，控制台不需要感知。

## 5. 边界与不做项

- **不改固件**：ESP32 固件、设备端逻辑零改动；记忆完全在服务端生效。
- **不动 YH 协议**：设备 WebSocket 协议（含 YH 私有协议）不动，记忆通过现有服务端 LLM 注入链路生效。
- **不动既有 provider 行为**：mem_local_short / mem_report_only / nomem 保持原样，保证随时可回退；mem0ai 仅做规范化接入与降级提示，不重写其平台调用逻辑。
- **不做用户端记忆管理**：设备用户不能自己查看/删除记忆（语音交互不适配，法律合规另立项）；仅管理员在控制台操作。
- **mem0 深度管理不做**：mem0 无信任分/状态体系，v1 只读列表 + 删除；编辑、审核流仅 holographic 适用。
- **不做自动引擎回退**（见 4.3）。
- **不引入向量数据库/外部服务**：holographic 保持零外部依赖（NumPy 可选）；不上 MySQL 存记忆条目。
- **不做跨 Agent 记忆共享/全局记忆**（P2 备选）。

## 6. 验收标准（用户可感知行为）

| # | 场景 | 通过标准 |
|---|---|---|
| A1 跨会话被记住 | 设备用户对 demo Agent 说"我叫张三，我喜欢听粤语歌"，结束会话；新会话问"你还记得我吗？我喜欢听什么？" | 回答包含"张三"与"粤语"相关信息；控制台该 Agent 记忆列表出现对应条目（类型偏好/档案、信任分≈0.5、来源设备与会话非空） |
| A2 管理页 CRUD | 管理员编辑"张三"→"张三丰"、调低信任分、删除各操作一次 | 编辑后条目更新且新会话称呼"张三丰"；删除后新会话不再引用该条目；全程无需登服务器 |
| A3 搜索与筛选 | 关键词搜"张三"、类型筛"偏好"、信任分筛 0~0.3 | 命中条目且关键词高亮；各筛选维度结果正确；空结果有友好提示 |
| A4 引擎切换 | 控制台将 demo Agent 记忆引擎由 mem_local_short 切到 holographic，保存 | 保存提示"新连接生效"；设备重连后日志显示 provider=mem_holographic，对话记忆正常（A1 复测通过） |
| A5 双引擎可选 | 为另一 Agent 配置 mem0（有效 key）并对话 | 记忆写入 mem0 平台；控制台显示 mem0 引擎徽标与只读列表；删除条目后不再被引用 |
| A6 mem0 降级 | mem0 未配 key 的 Agent 发起多轮对话 | 对话正常无报错；控制台 provider 卡片与引擎徽标显示"未配置 API Key，不可用"黄色警示；服务端仅一条告警日志 |
| A7 低信任分审核（P1） | 构造 trust<0.3 条目（连续"无用"反馈或手动调低） | 出现在待审池且角标 +1；设备对话不引用该条目；通过后恢复引用、驳回后列表转"已驳回"且永不引用 |
| A8 时间轴（P1） | demo Agent 切时间轴视图 | 按日分组倒序展示；筛选联动；节点点击出详情卡（含实体与来源会话） |
| A9 性能 | 试点 Agent 记忆 ≤500 条时对话 | `query_memory` 引入的额外首响延迟 ≤ 300ms（本地 SQLite 检索） |
| A10 回退安全 | 切回 mem_local_short | 原压缩档案行为不变（holographic 数据保留在库文件中，不丢失） |

P0 验收 = A1~A6 + A9 + A10；P1 追加 A7、A8。

## 7. 待确认问题

| # | 问题 | 建议默认值 |
|---|---|---|
| Q1 | 记忆命名空间改为 Agent 级后，是否需要保留"按设备隔离"开关（家人共用 Agent 但记忆需分开的场景）？ | v1 仅 Agent 级；设备级开关列 P2 |
| Q2 | 审核阈值 `review_threshold` 与检索阈值 `min_trust_threshold` 是否合一（均 0.3）？ | 合一为一个配置项，减少理解成本 |
| Q3 | "记忆管理"菜单位置：一级菜单，还是挂在"智能体/Agent 管理"下的 Tab？ | 一级菜单（与知识库平级），便于角标提醒 |
| Q4 | 引擎配置粒度：全局默认 provider + Agent 覆盖，还是仅 Agent 级？ | 全局默认 + Agent 覆盖（与现有 selected_module 机制一致） |
| Q5 | Java 直读 SQLite（sqlite-jdbc + WAL）还是 xiaozhi-server 暴露内部管理 API？ | 倾向 Python 内部 API（复用 store 全部锁语义，Java 不重复实现信任分钳制/实体重抽取等规则），由 #2 架构师定 |
| Q6 | sandyun.top 服务器是否已具备 NumPy（HRR 增强）？ | 缺失可接受，自动降级 FTS+Jaccard，不阻塞上线 |
| Q7 | mem0 只读列表（P0 可降级项）本期是否保留？ | 若 #4 排期紧张，降级为仅配置状态徽标，列表功能顺延 P1 |

## 8. 里程碑对齐（非承诺，供排期参考）

- #3 双引擎移植完成 → 可先以配置文件直连方式跑通 A1（无控制台）。
- #4+#5 完成 → A2~A6 全通。
- P1（时间轴/审核流）在 P0 全部验收通过后启动，避免阻塞 #6/#7。
- #7 远程部署：A1/A4/A6 必须在 sandyun.top 真机复测。

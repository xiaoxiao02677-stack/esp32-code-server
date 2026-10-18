# 记忆模块不足点总清单（统一版）

> 本轮记忆系统专项审计交付物。由审计A（数据链路与存储层，14项）与审计B（接口与面板契约，13项）交叉合并去重而成。
> 审计范围：yuhe-server/core/api/memory_handler.py + core/providers/memory/（全部引擎）、manager-api modules/memory、console-v2 Memory.vue、服务器 /root/xiaozhi-server 实况（9 个 SQLite 库逐一核验）。
> 状态口径：已修（含部署验证）/ 修复中（有人认领实施或验证）/ 待排期。

## 零、核心结论："面板已有数据但不同步"三因叠加

| # | 根因 | 层 |
|---|------|-----|
| ① | facts 接口 500：Java `@RequestParam` 要 `agent_id`（下划线），前端传 `agentId`（驼峰）→ MissingServletRequestParameterException | 接口契约 |
| ② | mem_hybrid 条目门禁：`requireHolographic`/`getFactPage` 只认 `mem_holographic`；hybrid 与 holographic 同库同 schema（`{agent_id}.db`），却被拒"不支持条目管理"→ 面板永远空 + fact_count 恒 0（双审计交叉一致确认） | 业务分派 |
| ③ | 分页截断：前端硬编码 `page=1, size=50` 无分页控件，a8b7726 智能体 69 条事实后 19 条永不可见 | 前端 |

三因独立成立、相互叠加：修掉任意一个仍会看到"部分不同步"。

---

## 一、致命（3 项，全部修复中）

| 编号 | 问题 | 详情 | 修复建议 | 状态 |
|------|------|------|----------|------|
| F1 | facts 接口 500（参数名不匹配） | Java `MemoryFactController` 各端点 `@RequestParam("agent_id")`；console-v2 部分调用传 `agentId` 驼峰键 | 统一契约：Java 端补 `agentId` 别名或前端改传 `agent_id` | 修复中（agent-1，随 F2 一起） |
| F2 | mem_hybrid 条目门禁拦截 | `MemoryFactServiceImpl.requireHolographic`/`getFactPage`/`listAgents` 仅认 `mem_holographic`；hybrid 写同一个 `{agent_id}.db`（同 schema 同库），面板无法打开且 fact_count 恒 0。服务器实证：agent 88b87cfb 为 mem_hybrid，db 15 条事实面板显示 0 | `engine in (mem_holographic, mem_hybrid)` 放行条目管理与统计（同库直读） | 修复中（agent-1） |
| F3 | summarize 链路不可用 | 旧版 jar 缺 memory 类（summarize 404，22:49 部署后类已齐）；`AgentMemorySummarizeServiceImpl` 落库走 `saveFact` 仍被 holographic 门禁拦截，hybrid 智能体一键总结必失败；且 `category="summary"` 不在枚举白名单（见 L3） | 随 F2 放行 hybrid；category 校验与落库对齐 | 修复中（agent-1；任务板 #4 端到端验证中） |

## 二、高（5 项，待排期）

| 编号 | 问题 | 详情 | 修复建议 | 状态 |
|------|------|------|----------|------|
| H1 | 前端分页截断 | `Memory.vue loadFacts` 硬编码 `page=1, size=50` 且无分页/搜索控件；超过 50 条的记忆永不可见 | 加分页控件或 `size` 上限放开至 100（后端已支持 size≤100） | 待排期 |
| H2 | 记忆沉淀仅断线触发 | `connection.py` 在连接关闭 finally 才起守护线程 `save_memory`；连接期间（长连接常驻）永不沉淀，断线瞬间进程退出则丢失；面板无轮询须手动刷新 | 按轮次/空闲阈值增量沉淀 + 面板轮询或刷新提示 | 待排期 |
| H3 | summarize 权限不一致 | Controller `@RequiresPermissions("sys:role:superAdmin")`，而页面入口对 normal 用户可见 → 普通用户点击必 403 | 权限对齐（页面按钮按权限隐藏或接口放宽） | 待排期 |
| H4 | feedback 契约错位 | 接口返回 `{old_trust, new_trust, helpful_count}`，前端读 `trust_score` 字段 → 反馈后信任分显示不更新 | 前端读 `new_trust` 或后端补 `trust_score` | 待排期 |
| H5 | 命名空间回退产生设备库 | `agent_id` 未下发时回退 `device_id`：服务器存在 `b8:1f:3f:c3:96:20.db`（1 条"用户称呼助手为小智"），面板不可见、永不并入 agent 库 | 下发失败时拒绝写库，或提供 MAC→agent 迁移合并工具 | 待排期 |

## 三、中（7 项）

| 编号 | 问题 | 详情 | 修复建议 | 状态 |
|------|------|------|----------|------|
| M1 | hybrid 短期层不回写 | `_update_summary_and_distill` 只更新内存 `self.summary_memory`，不写 `.memory.yaml` 也不调 Java `/agent/chat-summary/{session}/save` → 重连即丢（Java `summaryMemory` 字段仅被 local_short 的 `save_to_file=False` 路径回写） | hybrid 增加短期层回写通道（复用 chat-summary 接口） | 待排期 |
| M2 | 删除智能体不清理记忆库 | `deleteAgent` 清理 7 类关联（设备/聊天/插件/上下文/纠错/标签/快照）但不删 `.db`；生产目录已有 `qa-memory-test-agent.db` 测试残留 | 删除 agent 时联动删库或归档；清理测试残留 | 待排期 |
| M3 | 引擎切换无迁移 | local_short ↔ hybrid 互切时 `.yaml` 与 `.db` 双向成孤儿；切回时旧库直接续读（无版本标记）；切换"重连生效"期间旧引擎继续写旧存储 | 切换时提示数据迁移/清理策略 | 待排期 |
| M4 | 统计口径漂移 | `pending_count` 阈值取全局 `mem_holographic` 配置，hybrid 自定义 `min_trust_threshold` 时漂移；`count_facts` 含 rejected（口径=全量而非 active） | 按 agent 模型配置取阈值；口径注释统一 | 待排期 |
| M5 | 列表不返 entities | `/memory/facts` 列表项无 entities 字段（仅详情有）→ 图谱视图大量孤点，须逐条拉详情 | 列表批量返回 entities | 待排期 |
| M6 | 引擎文案与实现不符 | 面板引擎说明与实际能力不符（hybrid 显示可用实则被门禁拦截；mem0ai/powermem 文案与降级行为不一致） | 随 F2 修复后统一文案 | 待排期 |
| M7 | 错误态与空态混淆 | 引擎不支持/接口报错时面板显示"还没有记忆，多聊聊天"空态文案，误导用户 | 区分错误态/空态展示 | 修复中（agent-6，任务板 #5 Memory.vue） |

## 四、低（5 项，待排期）

| 编号 | 问题 | 详情 | 修复建议 |
|------|------|------|----------|
| L1 | retrieval_count 死指标 | 列存在、前端展示 ↺N，但全代码库无任何自增逻辑（grep 验证），恒 0 | 检索命中时 +1 或下架展示 |
| L2 | 读路径建库 | facts 查询对无 db 的 agent 会 `get_store`→mkdir→建 schema，产生空库垃圾文件（服务器已有 2 个 0 条 db） | 只读路径改只读打开，不建库 |
| L3 | category 枚举渗漏 | Python create 不校验 category（summarize 写入 `"summary"`）；前端筛选器无此项且显示英文原文。`_normalize_category` 白名单已有未接入 handler | handler 接入白名单或扩枚举+前端补选项 |
| L4 | WAL 积压 | 共享连接常驻不主动关闭，`32ff…db-wal` 积压 486KB 未 checkpoint；仅拷 `.db` 备份会丢最新数据（经 API 读才准） | 定期 `PRAGMA wal_checkpoint`；备份含 -wal 文件 |
| L5 | /agents 不传 db_dir | 统计端点未按 agent 模型传 `db_dir`，自定义 db_dir 的 agent 统计遗漏 | /agents 支持逐 agent db_dir |

## 五、设计建议（非缺陷）

| 编号 | 建议 | 说明 |
|------|------|------|
| S1 | 短期记忆可见化 | 仿 chatHistoryConf 链路：local_short/hybrid 的短期总结在 Memory 页加预览卡片。数据源已确认：`ai_agent_chat_history` 表（demo 智能体 883 条，chat_type 1/2） |

## 六、已修复核验（本轮审计过程中的基线确认）

| 项目 | 结论 |
|------|------|
| 部署同步 | md5 核验：Python 5 文件（memory_handler / mem_holographic / store / retrieval / mem_hybrid）与 Java 3 class（jar 内）本地镜像 = 服务器，完全一致 |
| 旧 facts 500（不存在 db 无容错） | 当前版本已修复（容错已建），但暴露新 500（F1 参数名） |
| 旧 summarize 404（jar 缺类） | 22:49 部署后类已齐，现为 F3 门禁问题 |
| 数据实况 | 9 个 db：7 个 agent 库共 110 条事实（a8b7726=69、32ff=21、88b8=15 等）+ 1 个 MAC 库（H5）+ 1 个 QA 残留（M2）；`with_agent_id` 全部一致；活跃引擎 mem_hybrid 沉淀正常（日志实证"hybrid LLM 沉淀 N 条长期事实"） |

---

**汇总**：致命 3（均修复中）/ 高 5 / 中 7（1 项修复中）/ 低 5 / 设计建议 1 / 基线核验 4。合计 20 项待办 + 1 建议。
**审计分工**：审计A（general-purpose-4，数据链路与存储层）、审计B（agent-5，接口与面板契约）；根因实测（agent-7 侦查 + agent-5 参数名实测）。

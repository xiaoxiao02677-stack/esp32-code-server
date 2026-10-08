# 记忆链路 + 全站 API/按钮 + 前后端一致性 · 十路检测总报告
（2026-10-07 06:22-07:10，10 agent 并行，全部只读检测）

## 一、总评

| 检测面 | 结论 |
|---|---|
| 记忆模块通信链路 | ✅ **全通**（E2E 实证：说话→ASR→LLM→TTS→上报→MySQL→断连抽取→SQLite→回注对话，每跳有日志+数据双证据） |
| 全站 API 接口 | ✅ 无 404 级断链（Java 169 端点 / 前端 142 函数 171 调用点全对照） |
| 按钮接线 | ✅ 545 个事件绑定无硬死按钮，21 项确证问题（多为软性缺陷） |
| 前后端逻辑一致性 | ⚠️ 8 条核心链路 4 条完全一致、4 条存在漂移；7 项记忆语义 5 项一致、1 项文案错误 |

## 二、记忆链路（4 agent 交叉验证）

**E2E 实证**（mem-e2e-live + mem-ws-report）：
- Python 8003 八个 /api/memory/** 接口全 200：列表/详情/过滤/分页/校验（400/404/405 边界全对）
- 鉴权三层闭环：用户 token → Java Shiro → server.secret Bearer → Python 回环+恒时比较
- 今日真实会话完整走通：06:17 用户说"呃，我喜欢吃苹果" → 06:23:56 断连自动抽取 2 条事实入库 + 标题生成
- SQLite 4 库 integrity ok，WAL 正常，音频无堆积

**质量问题（记忆侧 5 项）**：
1. 问句被存成事实（"我叫什么名字？"）——抽取正则无疑问句过滤
2. 实体抽取对中文无效（正则只匹配英文人名）——entities 全 0
3. 衰减文案六语言全错：说"信任分衰减一半"，实际衰减的是检索权重（trust_score 存储值永不变）
4. default_trust 有 store 缓存例外：多设备场景重连不生效（get_store WeakValue 缓存命中时忽略新值）
5. 待审计数硬编码 trust_max=0.3 与可配置阈值脱节

## 三、重大发现（跨 agent 交叉确认）

### 🔴 P0 级：占位 key 事故的"前端制造源头"没堵
api-contract-audit 发现：**模型编辑对话框的"复制模式"会把敏感字段替换为中文占位串（"你的API密钥"）直接走 add 落库**——昨晚我们修的"你的api_key"事故，源头就是这个前端入口。Java resolveUsableModel 只是兜底，制造端还开着。

### 🔴 P0 级：voice_instruction 前端完全缺失
btn-wiring-scan + api-contract-audit 双确认：昨晚上线的音色级语气指令，后端全链路（DB列/Entity/DTO/下发覆盖/Python消费）已通，但**前端音色管理无输入控件、payload 不带该键、全站 0 引用**——目前只能改库管理。

### 🟡 P1 级（4 项）
- **db_dir 双源分裂**（mem-params-chain B1）：面板改的 db_dir 只进设备链路，控制台 facts API 读全局配置——改非默认值后该 agent 在记忆页"消失"（默认值掩盖）
- **记忆面板权限割裂**（B2/mem-page-chain W2）：记忆页 normal 可进，但参数面板 3 个接口要 superAdmin——普通用户面板永久"加载失败"
- **SidebarSearch 搜索断链**（btn-wiring b）：跳 /home 不读 query；$emit('globalAgentSearch') 全站无监听者——顶栏搜索只跳页不过滤
- **模型启停开关不回滚**（api-contract #3）：禁用被拒（新加的引用计数）后 UI 开关仍显示已禁用，刷新才复位

### 🟡 P1 级（补丁缺口）
- **模板应用绕过 LLM 校验**（api-contract #6）：roleConfig 页"应用模板→保存"不走 resolveUsableLlmOrDefault，坏 LLM 可经此再入库
- **启停/删除引用检查漏 config_json.llm**（#7）：Intent 的 llm 引用删除有查、禁用无查；Memory 的 llm 引用连删除都不查

### 🟢 P2/P3 级（摘要）
- 11 个 i18n key 六语言全缺（TtsModel×5、AgentTemplate/Feature/Ota/common.noData/voiceClone 等，错误时显示 key 原文）
- TtsModel cancelEdit 的 shift(row) 误删行 bug
- EditVoiceDialog 孤儿组件（死按钮+硬编码外链）；FunctionDialog 工具按钮无响应（待产品判断）
- 重复记忆静默成功（前端期待错误提示，后端幂等返回成功）
- 空会话标题生成必报"智能体未找到"（15 次日志噪音）
- 音频 BLOB 存 MySQL ~12MB/天 无清理策略
- 三色条黄段无图例/绿段文案排他歧义
- dist-new/dist-qtts/dist-kawaii-auth 三个旧构建目录并存（误部署风险）
- --kawaii-radius-lg 未定义（有 fallback 不崩）
- 3 个测试遗留记忆库未清理（控制台显示 4 个"agent"）
- agent-models 响应含明文 api_key（server.secret 保护内，建议纳入轮换计划）
- actuator health 被 Shiro 拦截（无公开探活端点，可用 /user/pub-config 替代）

## 四、完全通过的链路（点名表扬）

- **设备配置上报链（B线）**：Python body ↔ Java DTO 字段名/类型/命名全对齐，白名单双侧一致——8 条链路质量第一
- **智能体创建/编辑**：提交字段全部命中 DTO，null-跳过语义匹配
- **设备列表字段映射**：驼峰转换完整，时间戳双轨兼容
- **记忆 facts CRUD 13 条链路**：无 404、无幽灵字段、竞态令牌正确
- **Kawaii 回归**：dist 不落后 src（所有改动均进构建），路由/守卫/样式链完整

## 五、修复建议优先级汇总

| 优先级 | 项 | 位置 |
|---|---|---|
| P0 | 复制模式占位 key 前端拦截+后端 add 校验 | ModelEditDialog.vue:229 + ModelConfigServiceImpl:484 |
| P0 | 音色 voice_instruction 前端补齐（列+payload） | TtsModel.vue + timbre.js |
| P1 | db_dir 双源统一 | memory_handler.py:101 |
| P1 | 记忆面板权限降级/隐藏 | MemoryEngineParams.vue |
| P1 | SidebarSearch 跳转接通（query 或事件监听） | SidebarSearch.vue:89 + home.vue |
| P1 | 启停开关失败回滚 | ModelConfig.vue:519 + model.js:288 |
| P1 | 模板应用加 LLM 可用性校验 | roleConfig.vue:856 |
| P1 | 启停/删除引用检查扩展 config_json.llm | ModelController.java:139 |
| P2 | 衰减文案六语言修正 | i18n/*.js:1815 |
| P2 | 11 个 i18n key 补齐 | 各语言包 |
| P2 | 疑问句过滤/语气词清洗 | mem_holographic.py:177 |
| P3 | shift bug/孤儿组件/dist 清理/测试库清理等 | 见各报告 |

---
*十路检测 agent 原始报告存于会话记录；本报告为 team-lead 交叉合成。*

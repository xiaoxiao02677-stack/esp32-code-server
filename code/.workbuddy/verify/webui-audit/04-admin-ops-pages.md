# admin 运营/配置工具页审查报告（22 页）

> 审查标准：redesign-existing-projects skill
> 页面：ApiDebug, AuditLog, CorrectWords, CustomReview, Dicts, DisplayConfig, EntityGraph, Knowledge, LinkSimulator, Mcp, Memory, Ota, Params, PushScheduler, Roles, Servers, Templates, TimelineChart, UserDefaults, WakeWord, WeChatClaw, WeChatOpenClaw

## 总评

22 页明显分为**三代代码**：第一代（EntityGraph/TimelineChart/WeChatOpenClaw）是灰白扁平风 + 裸 hex 色 + `alert/confirm`，与设计系统完全脱节；第二代（大部分 CRUD 页）统一到「page-head + hero/stats + DataTable + modal」模板，质量稳定；第三代（WakeWord/PushScheduler/DisplayConfig/WallpaperDispatch）开始有引导文案、内联状态、进度条等高级模式。同质化是双刃剑：模板带来一致性，但也让 15+ 个页面长得一模一样（skill 的"everything centered and symmetrical"警告）。最大的硬伤是**违规模态**：5 处裸 `alert()/confirm()`，以及一个**整页 TODO 空壳**（WeChatOpenClaw）直接上线了生产导航。

## 统计

P0 × 4 ｜ P1 × 10 ｜ P2 × 5

## 发现明细

### P0

- **[P0] WeChatOpenClaw.vue:58-79 | 整页空壳上线生产（Code Quality→commented-out dead code + dead links）**
  `load()` 主体是注释掉的 TODO（62-64 行），`startBind()` 直接 `alert('绑定功能开发中')`（73 行），`unbind()` 用裸 confirm（77 行）。这个页面挂在 admin 导航（DockNav.vue:149 有入口「微信绑定」），用户点进去只能看到永远「未绑定」的死界面。建议：要么下线导航入口，要么至少把按钮置灰 + 用 toast 替代 alert 并明确"排期中"。

- **[P0] 5 处裸 alert/confirm 违反 skill（Interactivity→error states: Do not use window.alert）**
  - WeChatOpenClaw.vue:73 `alert('绑定功能开发中，请稍后使用')`
  - WeChatOpenClaw.vue:77 `confirm('确定解除微信绑定？')`
  - WeChatOpenClaw.vue:78 `alert('解绑功能开发中，请稍后使用')`
  - PushScheduler.vue:351 `if (!confirm('确定删除任务...')) return`——**删除任务用浏览器原生 confirm**，与全站 askConfirm 体系断裂
  - Mcp.vue:210 `if (!confirm('确认删除该智能体的 MCP Server 配置？...')) return`——同上
  全部改为 inject('askConfirm')（项目已有现成全局确认弹窗），视觉统一 + 可定制 danger 样式。

- **[P0] EntityGraph.vue:9-13 | 智能体下拉硬编码一个死值（Content→placeholder 数据 + 功能残缺）**
  `<option value="conversation.chatgpt">conversation.chatgpt</option>` 写死，未接智能体列表接口。页面只在「conversation.chatgpt」这个特定 ID 下才有意义。且 canvas 画的是纯圆形排布（82-103 行），无连线（"图谱"无图）、无缩放拖拽。建议：下拉接 agentList 接口；图谱连线（entities 里有关系字段则画边）。

- **[P0] 多页 | 危险操作缺确认（Interactivity→destructive action）**
  抽查：Dicts.vue / CorrectWords.vue / DisplayConfig.vue:62（`removeRow` 无确认直接删）/ Servers 重启有确认（合格）。DisplayConfig 的「✕」删除字段行无任何确认且删后即失（无 undo）。多数页删参数/字典有 askConfirm，但字段级删除没有。建议字段删除至少 toast 提示或加确认。

### P1

- **[P1] 15+ 页同质模板 | 「page-head + stats + DataTable + modal」十五连（Layout→everything centered and symmetrical）**
  Dicts/CorrectWords/Ota/Servers/Roles/Templates/Models/Voices/Users/AuditLog/Params 等页面结构完全相同，只有字段差异。skill 点名这是最泛的 AI 布局。渐进建议：按页面性质分型——审计日志页可改时间线视图（已有 TimelineChart 组件）、字典页可用两栏主从、OTA 页可加版本对比 diff 高亮。不必全改，挑 3-5 个高频页做出差异。

- **[P1] 7 处内联样式硬编码（Code Quality→Inline styles mixed with CSS classes）**
  Params.vue:9、ApiDebug.vue:9、AuditLog.vue:32-39、Orders.vue:37、Roles.vue:33、Users.vue:43、Templates.vue:39 等筛选输入框全用 `style="border:1.5px solid var(--border);border-radius:10px;..."` 内联。同一段样式复制 7 次。建议抽 `.filter-input` 进 global.css。

- **[P1] EntityGraph.vue:110-133 | 第一代样式残留（Color→灰阶/阴影脱节）**
  `background: white; border-radius: 8px; box-shadow: 0 1px 3px rgba(0,0,0,0.1)`——8px 圆角 vs 全站 16-24px 体系；#666/#999/#ddd 裸灰 vs 全站 --text-sub token。同问题 TimelineChart.vue:146-156。建议这两个 canvas 页整体对齐 token（--surface/--radius-md/--shadow-card）。

- **[P1] WeChatOpenClaw.vue:84-115 | 同上的第一代样式 + 独立 .btn-danger（Color→不一致）**——整页未用任何 token。

- **[P1] Params.vue:29 | 行内编辑 input 无 Enter/Esc 快捷键（Interactivity→inline editing）**——行内编辑是 skill 推荐模式（代替 modal），但没有 Enter 保存 / Esc 取消，且编辑态无 focus 自动进入。建议补快捷键。

- **[P1] DisplayConfig.vue:25-27 等 | chip 是 div @click（Code Quality→语义）**——`class="chip"` div 当 tab 用（DisplayConfig:25, Dicts:20, CustomReview:22, UserDefaults），不可聚焦不可键盘切换。建议 role="tab" + tabindex 或直接 button。

- **[P1] Ota.vue:55 | 版本排序用字符串 sort()（Content→数据正确性，非纯视觉但影响展示）**——`filter(Boolean).sort().pop()` 对 "2.9.0" vs "2.10.0" 字符串排序错误（2.9.0 > 2.10.0）。建议 semver 比较或 pad 后排序。

- **[P1] Knowledge.vue:31 | DataTable 分页 props 与真实分页脱节**——`pages: Math.ceil(datasets.length/4)` 但 pageSizeOptions 最小 4，切 50 条/页后 pages 不变，分页控件语义错乱（组件层问题，此页是受害者）。同问题多处。

- **[P1] PushScheduler.vue:26 | 加载态文字「加载中...」三点省略（Interactivity→loading 一致性）**——全站混用「加载中…」「加载中...」（半角三点）；建议统一文案+骨架。

- **[P1] ApiDebug.vue:157 | 响应框暗色块（Color→random dark sections）**——`.resp-box` #0F172A 深色代码块在浅色页面中突兀；skill 点名「浅色页里随机深色区块」。这是开发工具页可接受（代码编辑器惯例），但建议至少包一层浅色边框 + 标注"代码区"，或跟随主题（dark 主题下反白）。

### P2

- **[P2] EntityGraph.vue:23 | canvas 固定 800×500 无 devicePixelRatio 缩放**——高分屏字体模糊。建议 DPR 适配。
- **[P2] Ota.vue:9 | label 包裹 file input 的按钮（Code Quality→语义）**——`<label class="btn">` 做上传按钮可行但无键盘焦点样式（回接 P0 focus-visible 修复）。
- **[P2] WeChatOpenClaw.vue:13-35 | bind-card 布局单一**——就一张卡 + 说明，无过程步骤指示；若真做绑定流程建议 stepper。
- **[P2] Servers.vue:28-45 | 节点表无可操作列**——只有查看，编辑/启停走后端；如后端支持建议补启停开关（带确认）。
- **[P2] 多页 | page-head 副标题带「迁移自 /cc/」「契约对齐」等工程注释**——Params.vue:6、Ota.vue:6、Chat.vue:6、ApiDebug.vue:6 等把迁移说明直接当用户副标题展示，是内部注释泄露。建议移到代码注释或帮助入口。

## TOP3 修复优先级

1. **清除全部裸 alert/confirm（5 处→askConfirm）+ 下线/改造 WeChatOpenClaw 空壳**（P0）
2. **EntityGraph 接真数据 + TimelineChart/EntityGraph 样式 token 化**（P0+P1，两个第一代页面回炉）
3. **内联筛选框样式抽类（7 处）+ chip 语义化**（P1，纯前端低成本）

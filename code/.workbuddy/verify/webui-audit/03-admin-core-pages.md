# admin 核心业务页审查报告（8 页）

> 审查标准：redesign-existing-projects skill；页面：Home / Devices / Users / Agents / Models / Voices / Chat / Orders

## 总评

核心页的**状态机完整性**（loading/empty/error、危险操作二次确认、按钮 busy 态）整体扎实——askConfirm 危险确认、toast 反馈、busy 文案（"保存中…"）都到位，这在 AI 生成代码里少见。问题集中在两类：**文案"AI 味"残留**（「运营总览」「统一管理」式空泛表达 + 所有 hero blob 的英文装饰小标），以及**个别页面的视觉 bug**（Chat.vue 删除按钮无危险色、Home.vue 六统计卡密度失衡）。数据表格无骨架加载态的问题在组件层报告，此处从页面层补充证据。

## 统计

P0 × 2 ｜ P1 × 8 ｜ P2 × 5

## 发现明细

### P0

- **[P0] Chat.vue:46 | `btn-danger` 类不存在，删除会话按钮无危险色（Component→危险操作视觉）**
  全局确认：global.css 只有 `.btn.danger`（App.vue 确认弹窗专用），Mcp.vue / Chat.vue / CustomReview.vue / PushScheduler.vue 里各写各的 `.btn-danger`（有的本地定义有的没有）。**Chat.vue 本地无 `.btn-danger` 定义** → 「删除本会话」渲染成无边框无背景的文字按钮，危险操作毫无视觉警示。修复：global.css 补 `.btn-danger`（或在 Chat.vue 本地定义），并把散落各页的本地 `.btn-danger` 定义收敛到 global.css。

- **[P0] Chat.vue:46 同源 | 删除会话按钮旁边就是「播放语音」，两按钮同级别（Interactivity→危险操作确认）**
  有 askConfirm 确认（Chat.vue:152-165）说明功能安全，但视觉上删除键与普通操作同级。除补危险色外，建议「删除本会话」挪到消息流面板右上角（与内容区分隔），或至少与播放按钮拉开间距。

### P1

- **[P1] Home.vue:5 等 8 页 | 页头 slogan 千篇一律（Content→AI copywriting cliches）**
  「全局运营数据一览」「你的设备状态（改名 / 绑定 / 解绑）」「统一管理设备、智能体与服务」——功能罗列式副标题，无场景感。skill 要求 plain specific language。建议按角色改写：如设备页→「绑定设备、分配智能体、跟踪在线状态」这类具体动词；首页→「今天有 N 台设备在线」式的动态化描述。

- **[P1] Home.vue:14-38 | 六统计卡塞进 4 列网格（Layout→网格溢出）**
  本页用 `stats-grid { grid-template-columns: repeat(3, 1fr) }` 本地覆盖（Home.vue:201），6 卡两行 3 列。但 hero blob 只占左列，右侧 3×2 网格在 1280px 画布下每卡仅 ~260px，密度过高。建议精简到 4 卡（用户/设备/模板/会话），其余数据放表格区小字。

- **[P1] Home.vue:80 | 会话项点击是 div @click（Code Quality→语义 + 键盘）**——`.sess-item` div 有 cursor 无 tabindex/keyboard，无当前项指示。建议改 `<a>` 或 `<button>`。

- **[P1] Home.vue:174-194 | 导出报表无 loading、无错误分支（Interactivity→export 状态）**——`exportReport()` 同步生成 CSV 问题不大，但无导出中/失败反馈；CSV 内容只有 7 个指标，用户预期「报表」可能有分页明细。建议明确"运营快照 CSV"文案，或补全明细数据。

- **[P1] Devices.vue:26 | IP 用 `<br />` 拼行（Code Quality→语义）**——MAC/IP 用 br 拼两行，语义应为 dl 或两个 span 块；且 IP 为空时显示空行。建议 `d.ip || '—'`。

- **[P1] Devices.vue:35-37 | 行操作三按钮 ✎ ⇄ ⤫ 前缀字符（Iconography→emoji 同源问题）**——与组件层报告同源：改用统一 SVG。

- **[P1] Devices.vue:14-18 | 统计卡与 hero 缺失（Layout→一致性）**——其他核心页都有 hero-row 青绿区块，Devices 只有 3 张裸统计卡（StatsCard 直排）。视觉节奏断裂。

- **[P1] Chat.vue:27 | 空态文案「去跟设备说句话吧～」波浪号（Content→语气）**——与全站「敬请期待」同属轻浮语气残留（skill 的"confident, not loud"精神）。建议「暂无会话。设备对话开始后会自动出现在这里」。

### P2

- **[P2] Chat.vue:171-181 | 消息气泡样式可直接复用但缺时间戳**——消息流无发送时间，管理端查证场景需要。
- **[P2] Chat.vue:44 | `messages.length` 上限无虚拟滚动**——max-height 480px 滚动；单会话上千条时 DOM 压力大，可后续虚拟滚动。
- **[P2] Home.vue:56 | `d.appVersion` 加 `v` 前缀**——版本号展示 `v{{ d.appVersion }}`，若后端返回 "2.5.1" 显示 v2.5.1 正确；若已带 v 则 vv2.5.1，建议 normalize。
- **[P2] Devices.vue:5 | 页头副标题泄露契约细节**——「（改名 / 绑定 / 解绑）」是功能清单而非用户语言（见 P1 文案问题）。
- **[P2] 多页 | 表格列「最近连接」时间格式不一致**——`slice(5,16)`（Home.vue:149）vs `slice(0,16).replace('T',' ')`（Chat.vue:126）vs fmtTime 多套实现，建议抽 lib 统一。

## TOP3 修复优先级

1. **global.css 补 `.btn-danger` 并收敛各页散落定义**（P0 直接 bug）
2. **页头副标题文案重写（8 页）**——具体动词化，去功能罗列
3. **Home 概览卡密度 + Devices 视觉节奏**——对齐其他页的 hero 结构

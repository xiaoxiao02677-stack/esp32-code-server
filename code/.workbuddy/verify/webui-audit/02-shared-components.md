# 共享组件审查报告（6 个复用组件）

> 审查标准：redesign-existing-projects skill；项目：console-v2（Vue 3 + vanilla CSS）
> 组件：DataTable / DockNav / TopBar / StatCard / Toasts / WallpaperDispatch
> 背景：这些组件被 admin 30 页 + customer 6 页全部复用，组件层问题会被放大 36 倍

## 总评

组件层质量分化明显：Toasts（队列 + 双向过渡动画）、DockNav（六主题 + 折叠联动 + 状态持久化）、TopBar（全局 Ctrl+K 搜索）都超出了"模板后台"水平，是亮点。**真正的短板是 DataTable 太薄**——它是 36 个页面共用的骨架，但只有「标题 + 分页」两层功能：无表格加载态、无行内空态插槽、排序/筛选全靠页面自己拼。另外所有组件统一用 **emoji 当图标**（🔍🤖📡📦🎙…），这是全站最明显的"业余感"来源（skill 的 Iconography 章节整体命中）。WallpaperDispatch 是自研重组件（1183 行），交互完整度很高但视觉自成一套（z-index、色值、按钮类都不走 token）。

## 统计

P0 × 3 ｜ P1 × 9 ｜ P2 × 4

## 发现明细

### P0

- **[P0] 全部 6 组件 | 全站 emoji 图标（Iconography→Lucide/Feather 默认图标 + 渲染不一致）**
  DockNav 导航 28 个 emoji（🏠🤖💬🧠🎙…）、TopBar 搜索 🔍、StatCard 传值 🤖📡、空态 💬。问题：① Windows 彩色 emoji 与 macOS/安卓渲染完全不同，风格不统一；② 与"高级质感"目标冲突（skill 建议 Phosphor/Heroicons 统一 stroke 图标集）；③ 部分 emoji 在暗色背景下对比度差。项目无 UI 库、不允许引入重依赖——建议用 **内联 SVG 图标组件**（一个 `IcIcon.vue` + 20 个常用 path，或直接引 Phosphor 的 SVG 文件），工作量可控。这是"秒变高级"的最高杠杆项。

- **[P0] DataTable.vue:2-19 | 组件无 loading 态，36 页各自为战（Interactivity→No loading states）**
  组件只有 `total/page/pages` props，没有 loading 插槽/骨架。实际效果：设备列表加载时表格空白 1-3 秒，用户分不清"加载中/没数据"。页面层要么没做（Devices.vue 刷新按钮 disabled 但表格区无任何指示），要么文字「加载中...」硬凑。建议 DataTable 加 `loading` prop + 表格区骨架屏（skeleton 行，匹配列形状），全站一次性受益。

- **[P0] DataTable.vue:15 | 分页只有「当前页」无页码列表（Component→分页体验）**
  `‹ 1 › 下一页`——用户无法跳页、无法看到总页数（只有「共 N 条」）。设备/订单等大列表只能一页页点。建议补页码窗口（1 … 4 5 [6] 7 8 … 99）+ 可选跳页输入。

### P1

- **[P1] DataTable.vue:37 | pageSizeOptions 硬编码 [4, 8, 20, 50]（Code Quality→hardcoded）**——4/8 对管理后台偏小，常见 [10, 20, 50, 100]；且组件不认识业务场景，建议 props 化。
- **[P1] DataTable.vue:7 | `<slot />` 无空态插槽**——空态由各页面自己在 slot 里塞 `.empty-state` div（36 处复制粘贴，格式还略有差异：有的带 emoji 有的不带）。建议组件加 `#empty` 插槽 + 统一空态样式。
- **[P1] DockNav.vue:18-21 | 「固件烧录」是 `<a href="/firmware-flash/">` 硬编码（Interactivity→dead/隐藏链路）**——非 router-link、无 `target` 说明；导航菜单里混入一个外部/静态页入口，用户点击会离开 SPA。建议 router-link 或明确标识"外部"。
- **[P1] DockNav.vue:33-38 | 六主题色板是 16px 圆点排成一行（Component→主题切换 UX）**——无当前主题文字、不可达性差（16px 点击目标远小于 skill 建议的 44×44）。建议改为「主题色块条 + 文字说明」或至少加大热区。
- **[P1] DockNav.vue:5 | 收起按钮文字「«」/「☰」（Iconography→语义不清）**——「«」作为收起指示不直观；图标按钮无 aria-label（Code Quality→a11y）。建议 `aria-label` + 更明确的双箭头 SVG。
- **[P1] TopBar.vue:45 | avatar 是 div 不是 button（Code Quality→语义 + a11y）**——`.avatar` div 有 cursor:pointer 但不可聚焦、无键盘事件。若它只是展示（无菜单），建议改成纯 span 去掉 cursor；若将来挂菜单，改 button。
- **[P1] Toasts.vue:19-21 | 3 秒固定时长、无关闭按钮（Interactivity→toast UX）**——长文案 toast 读不完；建议 hover 暂停 + 手动关闭 X。
- **[P1] Toasts.vue:29 | `z-index: 200` 裸值（Code Quality→z-index scale）**——全站 z-index 无体系：modal 150、toast 200、force-mask 300、boot-bar 10000、PushScheduler modal 1000。建议 :root 定义 `--z-*` 变量并收敛。
- **[P1] StatCard.vue | 组件本身零交互（Interactivity→卡片 hover）**——统计卡片与页面无联动（不像 Home.vue 的会话项可点）；Dashboard 场景建议可点击卡片（hover 阴影加深 + 跳转详情），不可点击的去掉暗示。

### P2

- **[P2] DataTable.vue:13-17 | 分页按钮用 ‹ › 字符**——渲染不一致，建议 SVG 箭头。
- **[P2] WallpaperDispatch.vue | 自成一套样式体系（Color→一致性）**——z-index 140、`#16a34a/#dc2626` 硬编码色、`.wp-btn` 自定义按钮类，与 global.css token 并行。它是功能最完整的组件，建议抽空对齐 token。
- **[P2] Toasts.vue:4 | 图标 ✓/✕/ⓘ 与 emoji 混用**——与全站图标问题同源，换 SVG 时一并处理。
- **[P2] TopBar.vue:21 | 「Ctrl K」kbd 提示是死 UI**——点击它不能触发搜索（点击 ≠ Ctrl+K），建议可点击聚焦或改成纯视觉提示并 aria-hidden。

## TOP3 修复优先级

1. **内联 SVG 图标统一替换 emoji**（P0 全局杠杆；先 DockNav/TopBar/StatCard，空态后补）
2. **DataTable 加 loading skeleton + 空态插槽 + 页码窗口**（P0+P1 三合一，全站一次性受益）
3. **z-index 变量化 + 主题/收起控件可达性**（P1，顺手修复键盘用户）

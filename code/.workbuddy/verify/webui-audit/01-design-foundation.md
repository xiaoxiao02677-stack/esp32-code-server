# 设计基础层审查报告（global.css / App.vue / main.js / index.html / Login.vue）

> 审查标准：redesign-existing-projects skill（C:\Users\34808\.workbuddy\skills\redesign-existing-projects\SKILL.md）
> 项目：console-v2（Vue 3 + Vite + 纯手写 vanilla CSS，无 Tailwind / 无 UI 框架）

## 总评

基础层远高于典型"AI 生成后台"水准：有完整的 design tokens 体系（色彩/圆角/阴影 CSS 变量）、六套主题、深色主题专门覆盖、紧凑模式、dock 折叠联动。主要短板集中在：**键盘可达性系统性缺失**（全站无 focus-visible）、**typography 打磨缺位**（无字重层级策略、数字无 tabular-nums）、**meta/SEO 零配置**、**无 404 兜底路由**。设计语言本身（圆角画布 + 青绿 hero blob + pill 按钮）自洽且不是常见紫蓝 AI 渐变风，这是加分项。

## 统计

P0 × 3 ｜ P1 × 8 ｜ P2 × 6

## 发现明细

### P0

- **[P0] index.html:3-8 | 缺 description / og:image / 社交分享 meta（Strategic Omissions→Missing meta tags）**
  只有 charset/viewport/title/favicon。作为面向消费者的控制台（sandyun.top），分享到微信/QQ 无摘要卡片。建议补 `<meta name="description">` + `og:title/og:description/og:image`。

- **[P0] main.js:52-90 | 无 404 兜底路由（Strategic Omissions→No custom 404 page）**
  37 条路由无 catchAll。用户手输错误 hash（如 `#/admin/xyz`）会渲染空白页（router-view 无匹配）。建议加 `{ path: '/:pathMatch(.*)*', component: NotFound }`，做一个带品牌感的 404 页（回首页按钮）。

- **[P0] global.css 全文件 | 全站零 `:focus-visible`（Interactivity→Missing focus ring）**
  遍历 445 行无任何键盘焦点样式；且大量输入框写死 `outline: none`（如 Login.vue:130、App.vue:157、Dicts.vue:144 等 30+ 处）后只回填 `border-color`——按钮、dock 项、链接、分页按钮完全无焦点指示。键盘用户无法定位位置。建议在 global.css 加一段全局 `:focus-visible { outline: 2px solid var(--primary); outline-offset: 2px; }` 即可修复大半。

### P1

- **[P1] global.css:26 | 字体栈无个性、无字重策略（Typography→Browser default fonts）**
  `"PingFang SC", "HarmonyOS Sans SC", ..., system-ui` 是中文后台的"安全默认"。skill 指出全用默认字体是第一指纹。由于是内网管理台不能依赖 Google Fonts，建议：标题类引入一套有性格的开源字体（如 MiSans / OPPO Sans 本地 woff2 子集）或至少给 display 级标题加 `font-weight: 800 + letter-spacing` 的显式层级策略（目前 h1 26px/800 已做，但 h2/h3 层级差距不足）。

- **[P1] global.css:189 (.stat-value) 等 | 数字全用比例字体（Typography→Numbers in proportional font）**
  `.stat-value`（30px 统计大数字）、`.data-table` 内所有数字列、`.pager` 页码均无 `font-variant-numeric: tabular-nums`。数字变化时宽度抖动，表格列不对齐。数据密集界面建议全局 `.data-table td { font-variant-numeric: tabular-nums; }` + `.stat-value` 同样。

- **[P1] App.vue:1-37 | 语义化标签缺失：整个应用外壳是 div 套 div（Code Quality→Div soup）**
  `.app-canvas`、`router-view` 外层均无 `<main>`；TopBar 组件内倒是有 `<header>`，但主体内容区 `<main>` 缺失 + 无 skip-to-content 链接（Strategic Omissions→skip link）。建议：App.vue:4 `.app-canvas` 改 `<main class="app-canvas">`，并在其后加视觉隐藏的跳转链接。

- **[P1] App.vue:90 | booting 假加载 300ms（Interactivity→Loading states）**
  `setTimeout(() => { booting.value = false }, 300)` 是硬编码的假进度条，与真实资源加载无关。用户每次刷新白等 300ms。建议改为真实 token 校验/首路由解析完成即关，或删掉。

- **[P1] global.css:120 (.page-head h1) | 标题中文排版未收 letter-spacing（Typography→letter-spacing）**
  中文标题 `letter-spacing: 1px` 对 26px 标题偏松散；skill 建议 display 级用负/零 tracking。中文不适合负值，但 0.02em 内更紧凑。小问题，但影响"高级感"。

- **[P1] global.css:11-17 | 强调色偏多：teal 系 + orange + primary 三族并存（Color→More than one accent）**
  默认蓝作主色没问题，但 `--teal-1/2/3`（hero 专用）、`--orange`（avatar/告警）+ badge 色板让页面有效强调色达 3 族以上。skill：选一个。建议 hero blob 保留 teal 作为"品牌副色"可以，但 avatar 渐变（#FFB199→#FF7A45 橙色系，global.css:113）与主题无关且跳戏，建议 avatar 用中性色或 primary-soft。

- **[P1] index.html:7 | favicon 是 emoji 风笑脸圆（Iconography→cliche）**
  两个白点眼睛 + 微笑弧线的蓝圆 = 最常见的 AI 生成 favicon 模板。品牌名"屿禾工坊"（宇禾/屿禾，与硬件相关）建议用字母 monogram（Y）或产品剪影。

- **[P1] App.vue:9-20 | 确认弹窗无 ESC 关闭、无焦点圈定（Interactivity→modal states）**
  `askConfirm` 弹窗只能点击取消/遮罩关闭；打开后焦点仍在背景，Tab 会跑到背景元素。建议加 `@keydown.esc` 关闭 + 简单 focus trap。

### P2

- **[P2] global.css:39 (.app-shell) | `min-height: 100vh` 应改 `100dvh`（Layout→100vh）**——skill 明确点名 iOS Safari 视口跳动问题。
- **[P2] global.css:205-214 | 表格行 hover 有、但表头无排序指示（Component→表格可交互性）**——`.data-table th` 无 cursor/箭头，用户不知道能否排序（目前确实不能排序，见 02 报告）。
- **[P2] global.css:138 | boot-bar 用 linear-gradient(90deg, primary, teal)（Color→perfectly even gradients）**——标准 90° 线性渐变是 skill 点名的"均匀渐变"，小元素影响不大，可保留。
- **[P2] Login.vue:20 | 密码可见切换用 emoji 🙈/👁（Iconography→inconsistent）**——emoji 图标与全站 emoji 图标策略一致（见 02 报告的系统性问题），但 emoji 在 Windows/安卓渲染差异大，专业后台建议 SVG。
- **[P2] main.js:51 | hash 路由**——生产已定，仅提示：hash 路由导致 URL 带 `#`，分享链接观感差；若未来改 history 模式需同步 nginx 配置。
- **[P2] global.css:57 | `.app-canvas max-width: min(1280px, calc(100vw - 152px))`**——有 max-width 约束（skill 合规），但 152px 是按 dock 展开最大宽硬算的，dock 收起时画布不自适应变宽（--dock-w 联动只改了 padding 没改 canvas 上限）——细节 bug：`calc(100vw - 152px)` 应改 `calc(100vw - var(--dock-w) - 28px)`（900px 以下分支已这么做，桌面端没有）。

## TOP3 修复优先级（对照 skill Fix Priority）

1. **全局 `:focus-visible` 一段 CSS**（P0，五分钟修复，收益最大的可达性提升）
2. **404 兜底路由 + meta description/og 标签**（P0，一次性 30 分钟）
3. **表格/统计数字 `tabular-nums`**（P1，一行 CSS，数据界面专业感立涨）

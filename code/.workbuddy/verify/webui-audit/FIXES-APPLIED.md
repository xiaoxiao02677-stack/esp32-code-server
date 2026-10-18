# console-v2 WebUI 修复执行清单（2026-10-18）

> 依据：本目录 6 份审查报告（00-SUMMARY 四批路线图）。
> 全部修改位于 `yh/console-v2/src/`，`npm run build` 已验证通过（2.25s，0 error）。

## 第一批（P0 零风险）— 全部完成
- **键盘可达**：global.css 全局 `:focus-visible` 主色描边；App.vue 加 skip-link + `<main id="main-content">`
- **404 兜底**：新建 `views/NotFound.vue`，路由加 `/:pathMatch(.*)*`
- **meta/品牌**：index.html 加 description / theme-color / og 标签；新建 `public/favicon.svg`（蓝底白 Y）
- **真实渲染 bug**：Chat.vue 的 `.btn-danger` 无定义 → 收敛进 global.css（--danger 底色 + hover 加深）
- **z-index token 化**：`--z-dock/-dropdown/-modal/-toast/-force/-boot`，App.vue 六处硬编码清除
- **假 booting**：App.vue 改 `router.isReady()` 后撤进度条（去 300ms 假等）
- **ESC 关窗**：确认弹窗支持 Esc 关闭 + 打开时自动聚焦确认按钮（注意 watch 放在 runConfirmOk 之后避开 TDZ）

## 第二批（P1 交互信任）— 全部完成
- **裸 alert/confirm 清零**（5 处）：PushScheduler/Mcp 删除改 `askConfirm`（App.vue provide 的全局确认弹窗）
- **WeChatOpenClaw.vue**：TODO 空壳整页重写为规范占位页（empty-state + 「排期中」badge + 上线规划清单）
- **筛选框抽类**：AuditLog/Orders/Params/ApiDebug/Templates/Roles/Users 7 页内联样式 → `.filter-input` / `.filter-select`
- **危险按钮**：CustomReview 本地 `.btn-danger` 硬编码清除

## 第三批（P1 组件系统）— 全部完成
- **图标系统**：新建 `components/yh-icons.js`（56 个 24×24 描边 SVG）+ `components/YhIcon.vue`（未知名回落小圆点）
- **接入**：DockNav 28 项 / TopBar 品牌与搜索 / StatCard；批处理 71 处 emoji→图标名
- **空态升级**：26 处空态加 YhIcon 图标
- **chip 语义化**：13 处 div→`button type="button"`（可键盘聚焦）
- **DataTable 重写**：loading 骨架屏（5 行 sk-fade）+ 页码窗口算法（1/…/cur±1/…/末页）+ pageSize 选项 + ‹› 按钮 + aria；30 处页面接 `:loading`
- **Toasts 重写**：check/x/info 图标、右上关闭、hover 暂停倒计时、token 化层级
- **其他**：tabular-nums（表格/统计/分页）、100dvh 双声明回退、chip/btn-danger/filter-input 全局类

## 第四批（P2 打磨）— 全部完成
- **Knowledge.vue**：假分页表达式 `Math.ceil(len/4)` → 单页 `:pages="1"`
- **Points.vue**（customer）：假统计卡/空表格/死按钮 → 规范「即将上线」占位页
- **customer/Home.vue**：标题「智能体 管理」→「我的智能体」；第 4 卡「可用积分(—)」→「可用模型」真实计数（onMounted 拉 /user/resources）；toast「已创建」→「智能体「xx」已创建」
- **Login.vue**：🙈/👁 → YhIcon eye/eye-off + aria-label
- **admin/Home.vue**：6 统计卡→4（去 memoryAgentCount/ttsModelCount 及对应请求与 CSV 行）；sess-item div→button；appVersion 去 v 前缀 normalize（防 vv2.5.1）
- **杂项**：Devices IP 空 br 悬空；Chat 去波浪号；Params 行内编辑 Enter 保存/Esc 取消；DisplayConfig removeRow 加 askConfirm + emoji 图标名；Ota maxVersion 数值化 semver 排序（2.10.0 不再小于 2.9.0）；ApiDebug resp-box 加边框 + 状态色 token 化
- **EntityGraph.vue 重建**：假智能体下拉（conversation.chatgpt）→ adminApi.agentList 真数据；canvas DPR 适配（setTransform）；hub-spoke 连线（中心智能体节点 + 环绕实体 + 连线）；颜色读 CSS 变量随主题；resize 重绘
- **TimelineChart.vue 重写**：同款真下拉 + DPR + token 颜色 + Y 轴网格线 + 圆角柱；**去随机假数据兜底**（失败改错误态+重试）
- **页头文案**：12 页 `.sub` 去「迁移自 /cc/」「契约对齐」工程注释，改具体动词化描述（Agents/CorrectWords/ApiDebug/Chat/Dicts/Mcp/Models/Ota/Memory/Servers/Params/Voices）；Knowledge 文档弹窗工程话术清理

## 构建期发现并修复的自引入 bug
1. App.vue `<main>` 闭合标签写成 `</div>`（模板结构错误）→ 修正
2. 批处理脚本向 DisplayConfig.vue 的 DataTable hint 字符串中间误插 `:loading`（属性含引号导致解析错误）→ 手工还原该行

## 明确不做（设计决策项，留给后续）
- 字体个性替换（现 Inter/system 栈可用）
- admin 页面布局差异化（统一栅格是当前风格决策）
- chat 虚拟滚动（数据量未到瓶颈）

## 遗留风险
- 批处理插入的 `:loading` 若落位在合法位置但语义错位，Vue 编译不报错——已 grep 全库确认无 `hint="/title="` 内插入残留
- `yh-icons.js` 图标路径为手绘近似 lucide，个别图标视觉需人眼过一遍

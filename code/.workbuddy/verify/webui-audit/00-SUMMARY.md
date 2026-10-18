# console-v2 WebUI 设计审查总汇总

> 审查标准：redesign-existing-projects skill（原版安装于 C:\Users\34808\.workbuddy\skills\redesign-existing-projects\SKILL.md，来自 github.com/yasikvlad/redesign-existing-projects）
> 审查范围：G:\demo\21_xiaozhi\yh\console-v2\（Vue 3 + Vite + vanilla CSS，admin 30 页 + customer 6 页 + 6 组件，约 13,100 行）
> 分报告：01-design-foundation.md / 02-shared-components.md / 03-admin-core-pages.md / 04-admin-ops-pages.md / 05-customer-crosscut.md

## 执行说明

按原计划多开 5 个审查 agent（设计基础层 / 共享组件 / admin 核心页 / admin 运营页 / customer+横切），但**全部 8 个 agent（含 3 个探测）均在拉起后 1 秒内死于模型后端 406 错误**——agent 子系统当前不可用（系统性故障，与任务无关）。已改为在主会话内按原 5 个方向逐一完成同等审查，报告结构不变。skill 安装本身成功（原版 SKILL.md 已落位用户级 skills 目录）。

## 总体结论

**这是一套功能完整度很高、但"质感分层"明显的后台**。设计系统（design tokens + 六主题 + 深色模式 + 紧凑模式）比典型 AI 生成项目好得多，代码卫生（零 console.log、零死链、危险操作普遍有确认）也罕见地干净。真正拉低质感的是三件事：**emoji 图标当 UI 图标**（全站 100+ 处，Windows/macOS 渲染不一致）、**"敬请期待"假数据污染 customer 端**、**键盘可达性系统性为零**（0 个 focus-visible、21 处不可聚焦的 div 交互、7 个语义标签 vs 1071 个 div）。另有少量真实 bug：Chat 删除按钮无色、WeChatOpenClaw 空壳页上线、OTA 版本排序错误、无 404 路由。

## 统计

| 分报告 | P0 | P1 | P2 |
|--------|----|----|----|
| 01 设计基础层 | 3 | 8 | 6 |
| 02 共享组件 | 3 | 9 | 4 |
| 03 admin 核心页 | 2 | 8 | 5 |
| 04 admin 运营页 | 4 | 10 | 5 |
| 05 customer+横切 | 2 | 8 | 4 |
| **合计** | **14** | **43** | **24** |

（含部分跨报告重复项，如 focus-visible 在 01/02/05 各出现一次——合并后实际独立 P0 约 9 项）

## P0 汇总（按修复杠杆排序）

1. **全站 0 个 `:focus-visible`**（01/02/05）——一段全局 CSS 修复大半，键盘用户最大受益
2. **无 404 兜底路由**（01）——未知 URL 空白页
3. **index.html 缺 description/og 标签**（01）——分享无卡片
4. **全站 emoji 图标**（02）——最高杠杆的质感提升项，建议内联 SVG 图标组件
5. **DataTable 无 loading 态 / 无页码窗口 / 空态 36 处复制**（02）——全站一次性受益
6. **5 处裸 alert/confirm**（04，PushScheduler 删除任务/Mcp 删配置/WeChatOpenClaw×3）——改 askConfirm
7. **WeChatOpenClaw 整页 TODO 空壳上线**（04）——下线入口或补全
8. **Chat.vue 删除会话按钮无色**（03）——`.btn-danger` 未定义，真实渲染 bug
9. **Points 页空壳 + customer 端「敬请期待」假卡**（05）——下线或换真指标

## 修复路线图（对照 skill 的 Fix Priority）

- **第一批（30 分钟，零风险）**：focus-visible 全局 CSS + `.btn-danger` 收敛进 global.css + 表格/数字 `tabular-nums` + 404 路由 + meta 标签
- **第二批（半天）**：裸 alert/confirm → askConfirm（5 处）+ WeChatOpenClaw 下线/占位 + 内联筛选框 7 处抽类 + chip div → button
- **第三批（1-2 天）**：SVG 图标替换（DockNav/TopBar/StatCard 先行）+ DataTable loading 骨架/空态插槽/页码窗口 + customer 端「敬请期待」清零 + admin 页头文案重写
- **第四批（可选）**：EntityGraph 接真数据 + 两 canvas 页 token 化 + admin 页面差异化（审计时间线、字典两栏等）

## 附：skill 安装状态

- 仓库：https://github.com/yasikvlad/redesign-existing-projects（用户给的 URL 带 `.skill` 后缀会 404，实际仓库名无后缀）
- 已安装：C:\Users\34808\.workbuddy\skills\redesign-existing-projects\SKILL.md（原版 15,060 字节，用户级，跨项目可用）
- 已知镜像：Leonxlnx/taste-skill、elayadesign/redesign-skill、hayatelin/taste-skill-zh-tw（内容一致）

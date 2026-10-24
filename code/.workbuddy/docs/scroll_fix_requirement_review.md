# 需求修订版：模块大容器内容滚动修复（console-v2）

> 基于 2026-10-21 代码扫描的执行版需求。原通用需求文档的问题：无范围清单、
> "移除 overflow: hidden" 表述会误伤 A10 滚动架构、验收标准不可操作。
> 本文档为可直接派发给执行 agent 的版本。

## 0. 结论摘要（先读）

真正的 P0 问题只有一个：**弹窗 `.modal` 基类无高度约束无滚动**。
页面级滚动、侧栏滚动、Chat 内部滚动都已是正常状态，**不要动**。

## 1. 现状架构（红线：以下均为刻意设计，不得修改）

| 层 | 代码位置 | 设计意图 |
|---|---|---|
| `body { overflow: hidden }` | global.css:55 | A10 体系：文档滚动锁定 |
| `.app-shell` 100dvh + overflow-y:auto + scrollbar-gutter:stable | global.css:81-101 | 页面滚动收进 shell，浏览器滚动条不出现 |
| `.app-canvas` overflow:hidden | global.css:113 | 服务 28px 圆角裁切，删掉圆角视觉即破 |
| `.dock` overflow-y:auto + hover 显影滚动条 | global.css:366-384 | 侧栏 26 项菜单滚动（窄屏需要） |
| 统一滚动条样式（软色圆角 thin） | global.css:57-68 | 全站滚动条已统一，新增滚动区自动继承 |
| Chat.vue grid + min-height:0 + 内部滚动 | Chat.vue:248-334 | 已实现的内滚样板，可作参考 |

**禁改清单**：上述任何一条都不属于本需求范围。尤其不要把 `body` 的
overflow: hidden 改回文档滚动——那会推翻 A10 并引入画布跳动回归。

## 2. 待修问题清单（按优先级）

### P0-1 弹窗基类无滚动（核心修复，一处改动收敛全部）

- **问题**：`.modal` 基类（App.vue:152）只有 `width: min(440px, 92vw)`，
  无 `max-height` 无 `overflow`。modal-mask（App.vue:151）是
  `display:grid; place-items:center`，内容超高时上下同时出屏、无法滚动。
- **波及**（裸用 `class="modal"` 无内联约束的弹窗）：
  - `views/admin/Devices.vue:62,76,104,134`
  - `views/admin/Dicts.vue:49`
  - `views/admin/Knowledge.vue:68`
  - `views/admin/CorrectWords.vue:39`
  - `views/admin/CustomReview.vue:126,142`
  - `views/admin/Agents.vue:70`（width 有、高度无）
  - `views/customer/` 下同款用法（执行时全量 grep `class="modal"`）
- **另有两处重复定义的 `.modal`，同样无滚动**：
  `Orders.vue:443`、`WeChatClaw.vue:578` —— 这两处是局部重定义，应一并清理。
- **修法**（收敛到基类，不逐页面打补丁）：
  ```css
  /* App.vue .modal 基类追加 */
  .modal {
    /* 现有样式保留 */
    max-height: min(88dvh, 88vh);
    overflow-y: auto;
    overscroll-behavior: contain;   /* 防滚动穿透到 .app-shell */
  }
  ```
  同时删除各页面重复定义的 `.modal`（Orders/WeChatClaw），统一走基类；
  已带内联 `max-height:88vh;overflow:auto` 的 7 个文件
  （Agents/AuditLog/Models/PushScheduler 等）内联样式可保留（不冲突），
  逐步收敛即可。
- **注意**：`88vh` 在移动端地址栏收展时会跳，用 `dvh` 优先、`vh` 兜底
  （与 .app-shell 的写法一致）。

### P0-2 弹窗内滚动体验（基类修复后顺手验证）

- 弹窗内容含长列表（如 Agents 编辑弹窗、Knowledge 弹窗）时，确认
  底部操作按钮随内容滚动可达（当前无 sticky footer，属可接受现状，
  若执行成本低可加 `position:sticky; bottom:0; background:var(--surface)`
  的 footer 区，非必须）。

### P1 横向溢出排查（低频）

- 全站 grep `white-space: nowrap` 无 ellipsis 的长文本场景（表格列为主）。
  现状 `.data-table` 已有合理约束，仅排查新增页面。
- 不做横向滚动条——按设计换行/截断优先。

## 3. 明确不做的事（防执行跑偏）

1. ❌ 不改 `body` / `.app-shell` / `.app-canvas` / `.dock` 的任何 overflow 规则
2. ❌ 不新造滚动条样式（全局 thin 软色圆角体系自动生效）
3. ❌ 不实现自定义"滚动链传递"逻辑——浏览器默认行为（内层滚完传外层）
   已满足需求；弹窗防穿透用 `overscroll-behavior: contain` 一行解决
4. ❌ 不引入虚拟滚动/滚动库
5. ❌ 移动端 iOS `-webkit-overflow-scrolling` 不需要（iOS 13+ 默认原生滚动）

## 4. 验收用例（可操作版）

| # | 用例 | 通过标准 |
|---|---|---|
| 1 | 打开 设备管理 → 任一编辑弹窗，缩放浏览器窗口至 600px 高 | 弹窗内容可滚到底，底部按钮可见可点 |
| 2 | 打开 订单管理 / WeChatClaw 弹窗，同上 | 同上（验证重复定义清理后基类生效） |
| 3 | 弹窗内容滚动到顶/底后继续滚动 | 外层 .app-shell 不跟着滚（overscroll-behavior 生效） |
| 4 | 触摸设备（或 Chrome DevTools 模拟触摸）滑动弹窗内容 | 惯性滚动流畅，无卡死 |
| 5 | 键盘 Tab 聚焦弹窗内表单元素后按 ↓/PageDown | 弹窗内容随焦点滚动 |
| 6 | 普通页面（Home/Devices 列表）滚动行为回归 | 与修复前一致（A10 架构未被破坏） |
| 7 | 弹窗滚动条样式 | 与全站软色圆角一致（无需额外样式） |

## 5. 实施建议

- 改动集中 3 个文件：`App.vue`（基类）+ `Orders.vue` / `WeChatClaw.vue`
  （清理重复定义）→ 一次提交。
- 其余裸用 `class="modal"` 的页面**零改动**自动受益——这正是收敛到基类的价值。
- 回归风险低：纯 CSS 追加，无 JS 逻辑变更。

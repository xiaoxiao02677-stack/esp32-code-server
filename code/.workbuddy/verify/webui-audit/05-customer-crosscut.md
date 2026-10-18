# customer 用户端 + 全局横切审查报告（6 页 + 12 项全局扫描）

> 审查标准：redesign-existing-projects skill
> customer 页面：Home / Devices / Voices / Points / MyModels / Profile
> 横切扫描：全 src/（47 个 .vue + index.html，约 13,100 行）

## 总评

customer 端是消费者直接面对的部分，但**严重营养不良**：几乎每页都有一个「敬请期待」假指标卡（Home 积分、Points 四连「—」、Devices 无 hero），形成"半成品感"。文案系统性地写"我"（「我的设备」「我的模型」）但视觉模板与 admin 完全同构——用户端应该更温暖更轻。技术层面横切扫描结果喜忧参半：**零 window.alert（除 admin 5 处）、零 href="#" 死链、零 console.log 残留**（非常干净），但**零 focus-visible、零语义化标签（7 个 vs 1071 个 div）、无 404、无 skip-link、无 description/og meta**——可达性与 SEO 是系统性空白。

## 统计

P0 × 2 ｜ P1 × 8 ｜ P2 × 4

## customer 页面发现

### P0

- **[P0] Points.vue:9-42 | 整页是空壳（Content→placeholder + Interactivity→dead buttons）**
  积分页两个主按钮（商城兑换/兑换码）**永久 disabled**，四张统计卡全部「—」+「敬请期待」，表格 tbody 空。这是给真实客户看的页面却没有任何可用功能。skill：dead buttons 应删或下线页面。建议：要么从 DockNav 摘除积分入口，要么把"即将上线"页做成说明型 coming-soon 页（统一模板，别用表格骨架假装功能存在）。

- **[P0] Home.vue:31 等 | 「敬请期待」出现在客户首页（Content→fake data）**
  首页可用积分卡 `value="—" note="敬请期待"`——客户第一眼看到"这平台什么都没做完"。如果积分未上线，这卡应删掉换真实指标（如会话数/最后活跃时间）。

### P1

- **[P1] Home.vue:31, Points.vue:24-27 | 假数据感（Content→fake round numbers / placeholder）**——同上延伸：把「—」卡全部换成有值指标或移除。
- **[P1] Home.vue:5 | 页头「智能体 管理」——customer 端叫"管理"太 admin（Content→文案语气）**——用户端建议「我的智能体」；页头副标题「智能体与设备管理」同理。
- **[P1] Home.vue:128 | 创建智能体后 toast「已创建」**——成功反馈太干（skill: 具体自信而非冷漠）。建议「智能体「xxx」已创建」。
- **[P1] Home.vue:35 | 智能体清单无编辑/删除入口**——客户创建后只能看不能改（详情/改名在设备端也没有）。若契约限制，至少把「查看设备」改成能跳详情。
- **[P1] Devices.vue:13-31 | 与 admin 同构的 hero+stats 模板（Layout→同质化）**——客户设备页复用 admin 的运营型 hero blob（英文装饰标 DEVICES/ONLINE + 大标题 + 3D 漂浮物），消费者场景建议更轻的列表式首页。
- **[P1] Voices.vue:43-49 | 不可试听按钮禁用态无解释（Interactivity→empty/disabled states）**——禁用按钮只靠 title 提示（hover 才有），手机端无 hover 永远不知道为什么灰。建议旁边加"原因"小字或可点击后 toast 解释。
- **[P1] Profile.vue:63 | 「加载中…」文字 vs 骨架（Interactivity→loading）**——quota 卡片加载用文字；建议骨架或至少固定高度防跳动。
- **[P1] Profile.vue:90 | 「自定义模型的 API Key 全程 AES-256-GCM 加密存储」**——安全细节写进客户可见文案，属于技术泄漏 + 增加不必要的科普负担。建议简化「密钥加密存储，仅展示掩码」。

### P2

- **[P2] MyModels.vue:37,73 | Base URL/参考音频列 ellipsis 靠 title 提示**——移动端无法查看完整值；建议点击复制。
- **[P2] MyModels.vue:45 | 「健康检查」按钮检测中态与结果无历史**——检测结果只 toast，错过就没了；建议行内结果徽标。
- **[P2] Voices.vue:26 | 「不可试听」统计卡 note「到管理端试听」**——客户看"到管理端"是角色混乱；普通用户根本去不了管理端。建议改为"该音色暂不支持试听"。
- **[P2] 6 页 | customer 端没有退出登录以外的账号菜单**——Profile 页够用，但导航底部无「账号」聚合（帮助/退出分散在 TopBar）。可后续。

## 全局横切扫描结果（12 项）

| # | 扫描项 | 结论 | 证据 |
|---|--------|------|------|
| 1 | window.alert/confirm | **5 处违规（全在 admin）** | WeChatOpenClaw×3、PushScheduler:351、Mcp.vue:210（customer 端 0 处 ✓） |
| 2 | href="#" 死链 | 0 处 ✓ | 唯一外部 a 是 DockNav 固件烧录（真实路径） |
| 3 | console.log 残留 | 0 处 ✓ | 全仓无 |
| 4 | img 缺 alt | 0 处违规 ✓ | 仅 2 个 img（Login 验证码 title 替代、Wallpaper 有 alt） |
| 5 | focus-visible | **全站 0 处（系统性缺失）** | 30+ 处 input 写死 outline:none 只回填 border-color |
| 6 | 语义化标签 | **严重缺失：7 个 vs 1071 个 div** | nav×2（DockNav/TopBar header）、main×0、section×1、footer×1、aside×1 |
| 7 | skip-to-content | **不存在** | 无 |
| 8 | 404 路由 | **不存在** | main.js 37 路由无 catchAll，未知 hash 空白页 |
| 9 | index.html meta | **仅 charset/viewport/title** | 无 description / og:image / og:title |
| 10 | 注释死代码 | 3 处 | WeChatOpenClaw.vue:62-64（整块 TODO 注释掉的接口调用）、WallpaperDispatch.vue:244/564（契约暂缺说明，属技术债注释非死代码） |
| 11 | transition 0s/none | 0 处 ✓ | 交互元素均有 0.12-0.3s 过渡 |
| 12 | div/span @click（不可达） | 21 处 | Home.sess-item、Chat.chat-agent×2、PushScheduler.task-card、Knowledge/Agents 等 modal-mask 遮罩（遮罩可接受）、CustomReview/Dicts/DisplayConfig chip×4、Devices/customer 等——chip 与列表项需键盘可达 |

## TOP3 修复优先级

1. **全站 `:focus-visible` 一段 CSS + chip/列表项改 button**（修复 12 项扫描里最重的 5/12 两项）
2. **customer 端「敬请期待」清零**：Points 页下线或改 coming-soon 模板；首页假卡换真指标
3. **404 路由 + meta 标签 + 语义化（main/skip-link）**（SEO + 可达性一次性补齐）

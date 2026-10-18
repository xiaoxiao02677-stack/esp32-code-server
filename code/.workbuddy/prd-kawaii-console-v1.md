# PRD：小智控制台 Kawaii 大改 + 设备配置云端记忆 + 记忆 API 可视化（v1）

| 项 | 内容 |
|---|---|
| 版本 | v1.0（整站改版 PRD，基于现有 manager-web 增量改造） |
| 作者 | 许清楚（Xu，产品经理） |
| 状态 | 待评审 |
| 关联任务 | #2 架构设计 / #3 设计系统 / #4 布局框架 / #5+#6 页面改造 / #7 配置同步后端 / #8 配置同步固件 / #9 QA / #10 部署 |
| 源码依据 | manager-web（Vue 2.6 + Element UI 2.15 + vue-router 3 + vuex 3 + vue-i18n 六语言 + PWA，views/ 22 页，导航为 HeaderBar 顶栏）；yuhe-server `core/providers/tools/unified_tool_manager.py` execute_tool 统一入口、`core/connection.py` hello 后 private_config 下发（agent_id/device_max_output_size/chat_history_conf/mcp_endpoint 等先例）；固件 `main/mcp_server.cc`（self.audio_speaker.set_volume / self.screen.set_brightness / self.screen.set_theme，现仅设内存不落盘）；manager-api MySQL `ai_device` 表（id/user_id/mac_address/agent_id/board/alias/app_version/... 无任何配置字段）；hermes 记忆模块已上线（holographic 引擎 + MemoryManagement 页 + 8 端点 REST） |

---

## 1. 背景与产品目标

### 1.1 背景

1. **控制台形态过时**：manager-web 沿用小智开源后台的顶栏导航 + 内容区布局，功能塞进 2 个下拉菜单（"参数字典"下挂 9 项），层级深、找不到、信息密度高、视觉风格与"小智"产品的可爱气质完全脱节。
2. **设备配置不跨开机**：用户对 ESP 说"音量调到 100"，固件 MCP 工具 `self.audio_speaker.set_volume` 只写内存——重启即丢；下次开机回到固件默认值，用户需要重复调教。设备虽绑定 agent_id，但服务端没有任何"每设备配置"的存储与下发机制。
3. **记忆参数不可见**：hermes 记忆模块已上线（条目管理、时间轴、审核流），但引擎 API 参数（db_dir / auto_extract / default_trust / min_trust_threshold / temporal_decay_half_life）藏在"模型配置"页的 JSON 编辑里，记忆页看不到、改不动，管理员无法在记忆语境下理解与调参。

### 1.2 产品目标

| # | 目标 | 衡量 |
|---|---|---|
| G1 控制台焕新 | 全站迁移为 Kawaii Minimal 双栏控制台，功能零丢失 | 22 个页面全部可从侧边栏 ≤2 次点击到达；无任何功能入口被砍；六语言与权限可见性与改版前一致 |
| G2 配置跨开机 | 设备硬件参数云端记忆，开机自动恢复 | 用户调音量/亮度 → 重启设备 → 参数保持；服务器日志可观测"记录/下发"两跳 |
| G3 记忆透明化 | 记忆引擎 API 参数在记忆页可视化 | 5 个引擎参数在记忆管理页可见、可改、改后生效有提示，无需去模型配置页翻 JSON |

### 1.3 用户故事

- **US1（管理员·找得到）**：作为管理员，我想一眼从左侧模块栏看到全部功能分区，点击即达对应页面，不再在下拉菜单里翻找"参数管理藏在哪"。
- **US2（管理员·看得舒服）**：作为管理员，我希望后台是可爱极简的粉彩风格（暖白底、粉紫青黄点缀、大圆角卡片、软软的果冻动效），长时间管理设备不视觉疲劳。
- **US3（设备用户·被记住的习惯）**：作为设备用户，我第一次开机把音量调到 100、亮度调到 80，下次开机小智应该直接用这套设置，不用我再调一遍。
- **US4（管理员·配置可见可控）**：作为管理员，我想在设备详情里看到"服务器记住的这台设备的配置"（音量/亮度/更新时间），并可手动修改，出问题时能一键复位默认。
- **US5（管理员·记忆调参不迷路）**：作为管理员，我想在记忆管理页直接看到引擎参数（自动抽取开关、信任分阈值、时间衰减等），理解每个参数对"小智记什么、信什么"的影响，就地调整并立即明白生效时机。
- **US6（手机用户·随时管理）**：作为管理员，我偶尔用手机查看设备状态，希望侧边栏在手机上折叠成抽屉，功能照样能用。

## 2. 需求池

### P0（本期必做，缺一不可上线）

| # | 需求 | 说明 |
|---|---|---|
| P0-1 | 双栏布局框架 | 左侧固定模块栏 + 右侧内容主面板的整体框架（含 HeaderBar 顶栏信息重组），路由与权限结构不变 |
| P0-2 | Kawaii 设计系统落地 | 色板/圆角/阴影/边框/字体/间距 tokens 化（CSS Variables），全局样式统一（见 §4.2），覆盖 Element UI 表现层 |
| P0-3 | 全部页面迁移 | 22 个页面全量进入新布局与设计系统，功能零丢失、六语言零缺失 |
| P0-4 | 设备配置同步全链路 | 固件参数（音量/亮度）经 execute_tool 拦截 → MySQL 持久化 → hello 握手 private_config 下发 → 固件开机恢复（见 §4.4） |
| P0-5 | 记忆引擎参数面板 | 记忆管理页内嵌"引擎参数"卡片：5 个参数可视化展示 + 编辑 + 生效说明（见 §4.5） |
| P0-6 | 按钮/图标主题适配 | 全站操作按钮、导航图标、状态徽标配色适配 Kawaii 色板；替换现有 `brightness(0) invert(1)` 黑色反白 hack |
| P0-7 | 可访问性基线 | 文本对比度 WCAG AA；`prefers-reduced-motion` 降级（关闭果冻动效） |

### P1（本期尽力，允许顺延）

| # | 需求 | 说明 |
|---|---|---|
| P1-1 | 果冻动效全家桶 | hover:scale-105 悬浮放大 + squash-and-stretch 果冻挤压回弹 + active:scale-95 按压反馈，spring 缓动 cubic-bezier(0.34,1.56,0.64,1)，统一 motion tokens |
| P1-2 | 移动端侧边栏折叠 | <768px 侧边栏收起为抽屉（Drawer）+ 右上/左上唤起按钮（爪印/汉堡），带遮罩 |
| P1-3 | Logo 与插画粉彩化 | 品牌区 logo、空状态插画、页面装饰元素按 Kawaii 风格重绘（粉彩描边、圆润造型） |
| P1-4 | 设备配置管理界面 | 设备管理页展示每台设备的云端配置（音量/亮度/更新时间），支持手动编辑与"恢复默认" |
| P1-5 | 记忆参数联动提示 | 参数修改后显示"对新连接生效"提示 + 当前引擎运行状态徽标（db 路径、条目数、引擎健康） |

### P2（本期不做，记录备选）

- 主题切换（薄荷/奶黄等 Kawaii 变体）：本期仅做 CSS Variables tokens 化预留接口，不做切换 UI
- 控制台内嵌实时设备状态流（音量/亮度实时回显）
- 配置同步扩展到更多固件参数的 UI 开关管理（本期仅数据结构预留，见 §4.4 扩展行）
- 骨架屏/加载动画 Kawaii 化定制（保持现有骨架屏即可）
- 品牌吉祥物动效彩蛋

## 3. 信息架构：模块栏设计

### 3.1 布局总览

```
┌────────────────────────────────────────────────────────┐
│ 顶栏：logo+品牌 | （搜索/面包屑） | 用户名·语言·头像        │  h-16
├──────────────┬─────────────────────────────────────────┤
│ 模块栏 w-64/72│  主面板（弹性）                          │
│ rounded-3xl   │  rounded-3xl bg-white p-6/8             │
│ bg-white p-6  │  内容 = 路由视图                         │
│ 分组标题+模块项│                                         │
│ 模块项:        │                                         │
│  rounded-2xl  │                                         │
│  p-4          │                                         │
│  选中 bg-pink-100                                    │
│  hover:scale-103                                        │
└──────────────┴─────────────────────────────────────────┘
背景整体 #FFF7ED 暖白
```

- 模块栏与主面板之间留 16~24px 间距，两栏均为白底圆角卡片浮在暖白背景上（border border-pink-200、shadow-sm/md）
- 移动端（<768px，P1）：模块栏折叠为抽屉，唤起按钮固定于顶栏左侧

### 3.2 22 页面 → 模块栏分组映射

侧边栏按权限与功能开关条件渲染（沿用现有 `userInfo.superAdmin` 与 `featureStatus.*` 判断，规则不变）：

| 分组 | 模块项（→ 现路由） | 可见性 |
|---|---|---|
| 总览 | 我的小智（/home） | 登录用户 |
| 智能体 | 智能体配置（/role-config）、设备管理（/device-management）、智能体模板（/agent-template-management）、模板快速配置（/template-quick-config） | 模板两项 superAdmin |
| 语音 | 音色克隆（/voice-clone-management）、音色资源（/voice-resource-management）、声纹管理（/voice-print） | 克隆：普通用户开开关即见 / 资源：superAdmin；声纹按现状 |
| 知识与记忆 | 记忆管理（/memory-management）、知识库（/knowledge-base-management） | 记忆 superAdmin；知识库按 featureStatus |
| 模型与参数 | 模型配置（/model-config）、服务商管理（/provider-management）、参数管理（/params-management）、字典管理（/dict-management）、替换词管理（/replacement-word-management）、功能配置（/feature-management） | 均 superAdmin（对齐现状） |
| 通讯 | 通讯录管理（/address-book-management） | featureStatus.addressBook |
| 系统 | 服务端管理（/server-side-management）、OTA 管理（/ota-management）、用户管理（/user-management） | superAdmin |
| 账号（不走双栏布局） | 登录（/login）、注册（/register）、找回密码（/retrieve-password） | 未登录态，保持全屏独立页 |

- **零丢失核对**：上表覆盖 views/ 全部 22 个页面（home、roleConfig、DeviceManagement、UserManagement、ModelConfig、ParamsManagement、KnowledgeBaseManagement、KnowledgeBaseItem、ServerSideManager、OtaManagement、VoiceResourceManagement、VoiceCloneManagement、DictManagement、ProviderManagement、AgentTemplateManagement、TemplateQuickConfig、FeatureManagement、ReplacementWordManagement、AddressBookManagement、MemoryManagement、VoicePrint + 3 个账号页）。KnowledgeBaseItem 作为知识库子页保留其页面内跳转关系，入口收敛在"知识库"模块下。
- **要求**：原 HeaderBar 顶栏的"参数字典"9 项下拉全部平铺进"模型与参数/系统"分组，任何功能从模块栏 ≤2 次点击（含展开分组）可达；现有搜索、用户菜单、修改密码、语言切换功能保留在顶栏右侧。
- **分组可折叠**：分组标题常显（小字号粉灰色），分组默认全展开；若未来模块增多可折叠，本期不做。

## 4. 功能规格

### 4.1 设计系统（Kawaii Minimal）

**色板 tokens**（CSS Variables，全局唯一色值来源）：

| Token | 值 | 用途 |
|---|---|---|
| `--kawaii-bg` | #FFF7ED | 页面背景（暖白） |
| `--kawaii-primary` | #F9A8D4 | 主色粉：选中态、主按钮、强调 |
| `--kawaii-secondary` | #A78BFA | 辅助紫：次级强调、图标点缀 |
| `--kawaii-accent-cyan` | #67E8F9 | 青色：信息态、链接点缀 |
| `--kawaii-accent-yellow` | #FDE68A | 黄色：警示、待办徽标 |
| `--kawaii-surface` | #FFFFFF | 卡片/面板底色 |
| `--kawaii-border` | #pink-200 系 | 粉彩边框（border-pink-200） |
| `--kawaii-text-primary` | 深灰棕系（如 #4A4139） | 正文，对 #FFF7ED 对比度 ≥ 4.5:1 |
| `--kawaii-text-secondary` | #8A7E76 系 | 次要文字，对比度 ≥ 4.5:1（小字号场景仍需 AA） |

**形态 tokens**：圆角 rounded-2xl（按钮/输入框/模块项）、rounded-3xl（卡片/面板/侧边栏）、rounded-full（头像/徽标/胶囊）；阴影 shadow-sm（静态卡片）/ shadow-md（悬浮/弹出）；边框 1px 粉彩（border-pink-200），无黑色粗边框、无硬朗分割线（分隔用浅粉背景块或留白）。

**交互动效（P1 全家桶，P0 仅保静态样式 + active:scale-95）**：
- hover:scale-105（卡片/按钮悬浮放大）
- 果冻挤压回弹（squash-and-stretch）：按压时 scaleX 略增 scaleY 略减，释放弹回，缓动 cubic-bezier(0.34,1.56,0.64,1)（spring 过冲）
- active:scale-95（按压缩小）
- 侧边栏模块项 hover:scale-103
- `prefers-reduced-motion: reduce` 时：所有 scale/回弹动效禁用，仅保留颜色/透明度过渡

**禁项清单（验收时逐条检查）**：深色/黑色背景、霓虹发光（glow/box-shadow 彩色光晕）、荧光高饱和色、黑色粗边框、硬朗分割线（1px 深灰线）、terminal 风格（等宽字体满屏/黑底绿字）、信息过密（卡片间距 < 12px、字号 < 12px 的密集表格）。

**Element UI 适配原则**：不动组件库本体源码；通过全局覆盖样式（主题变量 + 覆写类）统一 el-button / el-input / el-table / el-dialog / el-dropdown / el-message 等的表现层为 Kawaii tokens；组件行为（表单校验、分页、下拉逻辑）零改动。

### 4.2 双栏布局与响应式

- **桌面端（≥1024px）**：左 w-64（内容多时 w-72）侧边栏 sticky 定位，右侧主面板弹性铺满（max-w 建议 1440px 居中）；模块项结构：图标（粉彩线性图标 20~24px）+ 文字 + 可选徽标（如记忆待审数，沿用记忆 PRD 角标）。
- **平板（768~1023px）**：侧边栏收窄为仅图标（w-20），悬浮显示文字气泡。
- **移动端（<768px，P1-2）**：侧边栏隐藏，顶栏左侧出现唤起按钮（爪印形），点击滑出抽屉（bg-white rounded-r-3xl）+ 遮罩；点击遮罩/选中模块后自动收起。
- **路由切换**：主面板内容路由过渡动画（淡入 + 4px 上移，150ms，spring 缓动；reduced-motion 时禁用）。

### 4.3 按钮与图标（P0-6 / P1-3）

- 主按钮：bg 粉 #F9A8D4 → hover 加深 10% + scale-105；次按钮：白底 + border-pink-200 + 粉字；危险按钮：粉彩红系（如 #FCA5A5 底），不用纯黑纯红。
- 导航/操作图标：统一粉彩线性风格（粉/紫/青三色系分配到分组），替换现有 assets/header/*.png 与 `filter: brightness(0) invert(1)` 反白 hack；选中态图标用主题色实底或加深。
- 品牌 logo：保持小智 IP 辨识度前提下粉彩化适配（圆角、暖色调），P1 完成重绘，P0 先做配色适配（不加黑边、不加发光）。

### 4.4 设备配置云端记忆（P0-4，跨 #7 后端 + #8 固件）

**链路设计**（技术方案以 #2 架构设计为准，PRD 锁定产品行为）：

```
用户："音量调到 100"
 → LLM 调用 MCP 工具 self.audio_speaker.set_volume(volume=100)
 → 固件立即生效（现状不变）
 → 服务器 execute_tool 统一入口拦截识别（工具名+参数白名单校验、范围钳制 0~100）
 → 写入 MySQL（ai_device 维度）
 → 设备下次开机 hello 握手
 → 服务器经 private_config 下发 device_config（沿用 agent_id / device_max_output_size 同一通道）
 → 固件在音频/屏幕初始化后应用配置
```

**配置同步场景表**：

| 场景 | 触发（固件工具） | 参数与范围 | 服务端记录 | 下发与恢复 | 用户可感知 |
|---|---|---|---|---|---|
| S1 音量 | `self.audio_speaker.set_volume` | volume: int 0~100 | 记录 volume + updated_at | hello 下发 `device_config.volume`，固件 SetOutputVolume | 重启后音量保持 |
| S2 屏幕亮度 | `self.screen.set_brightness` | brightness: int 0~100 | 记录 brightness + updated_at | hello 下发，固件 SetBrightness | 重启后亮度保持 |
| S3 屏幕主题（扩展预留） | `self.screen.set_theme` | theme: "light" / "dark" | 结构预留（本期可不记） | 结构预留 | 本期不承诺 |
| S4 未来扩展 | 新 MCP 工具出现时 | 以 JSON schema 约定 | `ai_device` 配置字段建议 JSON 列（如 `device_config`）天然扩展 | 同通道追加 key | 按需 |

**行为细则**：

- **存取粒度 = 设备（device_id/mac）**，不是 Agent：不同设备硬件不同（有无屏幕），配置必须每设备独立。
- **只记"用户显式调整"**：拦截点在工具调用（即用户主动说/手动调），固件默认值不上报；同一参数多次调整覆盖取最后值（幂等）。
- **范围与容错**：服务端对参数做范围校验（0~100 钳制），非法值丢弃并记日志，不影响工具本身执行结果。
- **老固件兼容**：private_config 下发的 `device_config` 老固件不认识即忽略（现有 private_config 处理机制天然忽略未知 key），不产生错误；固件侧只在收到合法值时应用，收不到用本地默认。
- **服务器异常**：配置读取失败时按"无配置"处理（固件用默认值），不阻塞 hello 握手与对话主链路。
- **用户清除**：控制台设备管理页"恢复默认"（P1-4）= 删除该设备 device_config 记录，下次开机回固件默认。
- **可观测性**（QA 验收依赖）：服务器日志记录"工具拦截→写库"（含 device_id、参数、值）与"hello 下发 device_config"两跳；固件串口日志打印"应用云端配置 volume=xx"。

### 4.5 记忆引擎参数面板（P0-5）

**位置**：记忆管理页（MemoryManagement.vue）顶部或侧边新增"引擎参数"卡片，与条目列表同页展示；数据仍走现有 `ai_model_config`（type=memory）+ Agent 绑定机制，不新造配置体系（对齐记忆 PRD §4.3 的既定决策）。

**字段表**：

| 参数 | 类型 | 默认值 | 展示控件 | 说明文案（面板内提示） |
|---|---|---|---|---|
| db 根目录（db_dir） | string | data/memory/ | 只读文本 + 复制按钮 | 记忆数据库存放位置，修改需运维（防误改，只读） |
| 自动抽取（auto_extract） | bool | 开 | 开关（el-switch 粉色） | 开启后小智自动从对话中记住事实 |
| 默认信任分（default_trust） | number 0~1 | 0.5 | 滑杆（步进 0.05）+ 数值 | 新记忆的初始信任分 |
| 检索阈值（min_trust_threshold） | number 0~1 | 0.3 | 滑杆（步进 0.05）+ 数值 + 三色条 | 低于该分值的记忆不参与回答 |
| 时间衰减半衰期（temporal_decay_half_life） | number（天） | 0=关 | 数字输入 + "关闭"说明 | 0 表示不衰减；高级项默认折叠 |

**交互规则**：
- 面板顶部显示当前 Agent 所绑引擎徽标与参数作用域（全局默认 or Agent 覆盖）。
- 修改后保存：走现有模型配置保存接口；成功提示必须包含"新建设备连接生效，存量连接重连后生效"（对齐记忆 PRD 既有语义）。
- 参数变更有即时语义说明（如调低检索阈值 → "更多低置信记忆将参与回答"），帮助管理员理解后果。
- 引擎为 mem0 / mem_local_short / nomem 时，面板显示对应引导文案（参数仅 holographic 适用），不显示无关字段。
- 面板展示引擎运行状态徽标（P1-5）：库文件路径、条目数、引擎健康（可用/未配置）。

### 4.6 主题切换预留（P2-0）

- 全部色板/圆角/阴影 tokens 走 CSS Variables 且集中在单一主题文件（如 `src/assets/styles/kawaii-tokens.scss`），组件只引用 token 不写死色值——这是 P0 的实现要求，为 P2 多主题（薄荷绿/奶黄等 Kawaii 变体）预留切换接口。
- 本期不做切换 UI、不做暗色主题（禁项）。

## 5. 验收标准（可观测行为）

| # | 场景 | 通过标准 |
|---|---|---|
| A1 全页面可达 | 以 superAdmin 登录遍历模块栏 | §3.2 表列出的全部模块项可见、可点、路由正确；普通管理员/开关键隐藏逻辑与改版前一致（对照改版前逐角色截图清单） |
| A2 风格合规 | 逐页走查 22 页 | 背景暖白 #FFF7ED；卡片白底 rounded-3xl；边框粉色系；§4.1 禁项清单逐条为 0 违例；无任何页面残留旧顶栏导航样式 |
| A3 功能零回归 | 抽查核心操作：新增智能体、改模型配置、记忆条目 CRUD、知识库上传、OTA 触发 | 操作全部成功，行为与改版前一致；六语言切换后新布局无缺译、无溢出 |
| A4 可访问性 | 浏览器对比度插件 + 系统开启减弱动态 | 正文/按钮文字对比度 ≥ 4.5:1（WCAG AA）；开启 prefers-reduced-motion 后无 scale 弹跳动效 |
| A5 音量跨开机 | 设备说"音量调到 100"→ 服务器日志出现拦截记录与 device_config 写入 → 重启设备 | 重启后音量为 100；串口日志打印应用配置；控制台（P1-4，若顺延则查库）可见该记录 |
| A6 亮度跨开机 | 设备说"屏幕亮度调到 80" → 重启 | 重启后亮度 80，同 A5 观测点 |
| A7 配置容错 | 服务器注入非法值（volume=200）/ 老固件版本连接 | 非法值被钳制或丢弃且工具调用本身仍成功；老固件忽略 device_config 正常对话，无报错崩溃 |
| A8 配置互不干扰 | 两台设备分别设不同音量后重启 | 各自保持各自值（按设备隔离，不串） |
| A9 记忆参数面板 | 记忆管理页打开"引擎参数" | 5 个参数正确回显当前值；修改 default_trust 保存成功且提示"新连接生效"；db_dir 只读；切换引擎时面板自适应引导文案 |
| A10 移动端（P1） | 375px 宽度打开控制台 | 侧边栏折叠为抽屉，唤起按钮可见可点；抽屉内模块可导航；主面板内容不横向溢出 |
| A11 动效（P1） | 桌面端悬浮/点击卡片与按钮 | hover 放大、按压果冻回弹、active 缩小，缓动为 spring 曲线；全程无布局抖动（transform-only，不触发 reflow） |
| A12 性能 | 首页冷加载 | 构建产物体积相对改版前增长 ≤ 15%；首屏可交互时间不劣化超过 500ms（PWA 缓存仍生效） |

P0 验收 = A1~A9 + A12；P1 追加 A10、A11。

## 6. 边界与不做项

- **不动 Element UI 组件库本体**：不 fork、不改 node_modules 源码；只用全局样式覆盖与包装组件。
- **不换框架**：Vue 2.6 + vue-router 3 + vuex 3 + vue-i18n 保持；不上 Vue 3 / 不引入新 UI 库 / 不引入 Tailwind 运行时（tokens 若用 Tailwind 风格命名仅为语义约定，样式落地方式由 #3 定）。
- **不动后端业务逻辑**：除 P0-4 配置同步链路（拦截 + 存储 + 下发）与 P0-5 参数面板复用既有配置接口外，manager-api / yuhe-server 业务逻辑零改动。
- **不动固件业务逻辑**：除配置恢复应用点（开机应用 device_config）外，ESP32 固件功能逻辑零改动；MCP 工具签名不变。
- **不动 YH/WebSocket 协议**：device_config 走既有 hello private_config 通道，不新增消息类型。
- **不做用户端（设备侧）配置管理**：设备用户不能用语音"查看/重置云端配置"（本期范围外，语音交互复杂度高）；只有固件自动应用。
- **不做暗色主题**：禁项清单明确禁止深色背景，P2 主题切换也仅限浅色 Kawaii 变体。
- **不迁移历史数据**：改版是纯 UI 层迁移，无数据库迁移（配置同步是新增字段/表，不动存量数据语义）。
- **不做后端管理页之外的新页面**：22 页全量迁移，不新增除"引擎参数卡片"（页面内嵌）以外的页面。

## 7. 待确认问题

| # | 问题 | 建议默认值 |
|---|---|---|
| Q1 | `ai_device` 加 JSON 列（device_config）还是独立表 `ai_device_config`？ | 倾向 JSON 列（扩展免 DDL），由 #2 架构师定 |
| Q2 | 拦截点放 Python execute_tool 还是 Java 侧订阅工具事件？ | 倾向 Python execute_tool（单一入口、实时、零新链路），由 #2 定 |
| Q3 | 固件应用 device_config 的时机（板级初始化后 / MCP server 启动后）？ | 越早越好但不阻塞开机；由 #8 工程师定，PRD 只锁"开机后生效、日志可观测" |
| Q4 | 侧边栏分组是否可折叠、默认展开态？ | 本期全展开不折叠（22 页 7 组不超一屏）；超出时再加折叠 |
| Q5 | 图标方案：现 PNG 重绘粉彩 vs 引入线性图标库（如 iconify）？ | 倾向图标库 + 少量定制（品牌 logo/吉祥物手绘），由 #3 定 |
| Q6 | P1-4 设备配置管理界面若顺延，控制台是否需要最小化替代（只读展示）？ | 顺延则查库验收，UI 随 P1 一起上 |
| Q7 | 现有顶栏全局搜索是否保留在顶栏（不进侧边栏）？ | 保留顶栏（搜索是跨模块能力，不属于任何分组） |

## 8. 里程碑对齐（非承诺，供排期参考）

- #2 架构设计完成 → 锁定 Q1/Q2/Q3 技术方案 → #7（后端）与 #8（固件）可并行启动。
- #3 设计系统完成 → #4 布局框架 → #5/#6 页面批次改造（建议批次：#5 = 总览+智能体+语音（高频页面），#6 = 知识记忆+模型参数+系统）。
- P0-5 记忆参数面板依赖 #3 tokens 但不依赖 #4 双栏（卡片可先在旧布局验证），可提前。
- #9 QA：A1~A4、A9~A11 为前端走查项；A5~A8 为全链路真机项（需 #7+#8 完成后在 sandyun.top 复测）；A12 构建对比在 #10 部署前完成。

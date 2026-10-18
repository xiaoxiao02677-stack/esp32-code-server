# 架构设计：Kawaii 控制台 + 设备配置云端记忆 + 记忆参数面板（v1）

| 项 | 内容 |
|---|---|
| 版本 | v1.0（任务 #2 交付） |
| 作者 | 高见远（Gao，架构师） |
| 状态 | 定稿（三线方案均已拍板；待明确事项见 §6） |
| 上游 | PRD（PM 任务 #1，若冲突以 team-lead 同步为准） |
| 下游 | #3 设计系统 / #4 布局框架 / #5 批次1 / #6 批次2 / #7 配置同步后端 / #8 配置同步固件 |

> 引用事实均基于实际侦察：`G:/demo/21_xiaozhi/code-server-mirror/`（manager-web / manager-api / yuhe-server 三仓镜像）与 `G:/demo/21_xiaozhi/code/yuhe-esp32/`（固件）。实施者发现偏差以实际代码为准并回报 team-lead。

---

## 0. 侦察事实修正（重要，影响 B 线设计）

任务简报中"固件工具设内存不落盘"**不准确**，实测：

1. **音量已持久化**：`main/audio/audio_codec.cc:40-46` `AudioCodec::SetOutputVolume` 写 NVS（namespace `audio`，key `output_volume`）；构造函数 `audio_codec.cc:31` 开机读回。
2. **亮度已持久化**：`main/boards/common/backlight.cc:46-53` `SetBrightness(b, permanent=true)` 写 NVS（namespace `display`，key `brightness`）；`RestoreBrightness()` 开机读回（`backlight.cc:33`）。`mcp_server.cc:70` 的 `self.screen.set_brightness` 已传 `permanent=true`。
3. **真正的固件缺陷**：`main/boards/my-s3-tft/my_s3_tft_board.cc:91` 开机构造里硬编码 `GetAudioCodec()->SetOutputVolume(50)`——**每次开机都把 NVS 恢复值覆盖回 50 并写盘**。这是 B 线固件侧必改点。
4. **设备不直连 Java**：Python 服务器经 `config/manage_api_client.py`（httpx 单例，`Authorization: Bearer {manager-api.secret}`）调 Java。所有 server 间接口走 Java `ShiroConfig.java:93` 的 `/config/**` → `server` 过滤器。
5. **App.vue 无全局布局**：`App.vue` 只有 `<router-view/>`；每个管理页自己 `<HeaderBar/> + el-main`（20 页嵌入 HeaderBar，23 页用 VersionFooter）。双栏改造必须新建布局骨架 + 嵌套路由，无法只改一处。
6. **Element UI 是整包 CSS**：`main.js` `import 'element-ui/lib/theme-chalk/index.css'`；生产可开 CDN（`VUE_APP_USE_CDN`，vue.config.js 从 unpkg 注入同一份 theme-chalk css）。SCSS 主题重编译方案与 CDN 模式冲突。
7. **工具名 sanitize**：`core/utils/util.py:570` `sanitize_tool_name` 把 `.` 替换为 `_`（`self.audio_speaker.set_volume` → `self_audio_speaker_set_volume`）。LLM function call 到达 `execute_tool` 时已是**下划线名**，拦截白名单必须按下划线名匹配（MCPClient.tools 的 key 是 sanitized 名）。
8. **服务器 hello（welcome_msg）在连接建立即发**（`connection.py:250` 后 `async for` 前）；`_background_initialize` 拉取 private_config 是异步后台任务，完成时间晚于设备收到 server hello——设备配置下发是一条**独立的后续 JSON 消息**，设备侧在 `application.cc OnIncomingJson` 加分支处理，不依赖 MCP ready。
9. **C 线权限一致**：`/models/{id}` GET 为 `sys:role:superAdmin`（ModelController.java:117），而记忆管理菜单本身 `v-if="userInfo.superAdmin"`（HeaderBar.vue:78）——直接复用 `/models/**` 现有接口无权限冲突。

---

## 1. 三线架构

### 1.1 A 线：控制台 Kawaii Minimal 改造

#### 1.1.1 Element UI 主题覆盖策略：拍板「CSS 变量 + 后置覆盖层」，弃用 element-variables.scss 重编译

**方案对比**：

| 维度 | 方案1：element-variables.scss 全量重编译 | 方案2：CSS 变量 + 后置覆盖层（拍板） |
|---|---|---|
| 原理 | import element-theme-chalk SCSS 源码 + 覆盖 `$--color-primary` 等变量，dart-sass 重编译整包 | 新建全局非 scoped `kawaii-theme.scss`，用 `--kawaii-*` CSS 自定义属性 + 组件选择器后置覆盖 |
| CDN 模式 | ✗ 冲突：unpkg 注入的仍是原版 theme-chalk css，本地重编译 css 双份加载、顺序不稳 | ✓ 兼容：覆盖层在 bundle 内，选择器优先级设计上不依赖加载顺序（specificity + 必要时 `!important`，项目 global.scss 已有此惯例） |
| 构建影响 | 全量 SCSS 编译，构建变慢；dart-sass 对 element 2.15 SCSS 有大量 deprecation 噪音 | 零影响，不动 vue.config.js |
| 维护 | element 升级需同步变量表；重编译产物 diff 巨大 | 单文件选择器清单，按组件枚举，增量收敛 |
| 运行时能力 | 无 | 支持未来运行时换肤/深色模式（改根 class 切 token 值即可） |
| 覆盖盲区 | 无（编译期替换） | JS 内计算色不可达（el-color-picker 推荐色等，管理台未用）；弹层挂 body 需全局选择器（本方案天然覆盖） |

**论证**：决定性因素是 CDN 双模式兼容与改动收敛。管理台实际使用的 Element 组件面有限（button/input/select/option/table/table-column/pagination/dialog/form/form-item/tabs/tab-pane/dropdown/dropdown-menu/dropdown-item/message/message-box/tag/switch/radio/checkbox/date-picker/loading/popover/tooltip/collapse ~22 类），选择器清单一次枚举后长期稳定。方案1 的重编译产物与 unpkg 原版 css 并存反而引入"哪份生效"的不确定性。

**落地约定**：
- `src/styles/kawaii/tokens.scss`：`:root` 级 token 定义（命名见 §5.3）；
- `src/styles/kawaii/element-overrides.scss`：按组件分节的选择器覆盖（唯一允许写 `.el-*` 全局覆盖的文件）；
- `src/styles/kawaii/index.scss`：入口，main.js 在 `element-ui/lib/theme-chalk/index.css` 与 `global.scss` 之后 import；
- 页面 scoped 样式**禁止**再写裸 `.el-` 覆盖（现状各页有少量 `::v-deep`，改造批次顺带收敛到 element-overrides.scss，不强制一次清零）。

#### 1.1.2 双栏布局组件树（嵌套路由）

```
src/App.vue（不变，仅 router-view）
└─ KawaiiLayout.vue（新，layout/）——嵌套路由父组件
   ├─ 左栏 232px 固定：KawaiiSidebar.vue
   │   ├─ 品牌 logo + 版本号徽标
   │   ├─ SidebarMenu.vue（el-menu 垂直分组导航；吸收 HeaderBar 的权限可见性逻辑
   │   │    v-if superAdmin / featureStatus.*，分组：工作台/内容/资源/系统管理）
   │   └─ 用户卡片（头像+昵称+退出，吸收 HeaderBar 右区）
   ├─ 右侧自适应：
   │   ├─ KawaiiTopbar.vue（56px：全局设备搜索[原 HeaderBar 搜索能力迁移，含搜索历史]、
   │   │    语言切换、当前页面标题/面包屑、右侧用户下拉兜底）
   │   ├─ <router-view/>（页面内容；页面根自己滚动，el-main 容器化）
   │   └─ VersionFooter（底部 35px 保留现状组件）
   └─ 响应式：<1024px 侧栏折叠为 64px 图标栏（P1 可选，P0 固定展开）
```

**路由改造**：`router/index.js` 引入嵌套路由——父路由 `path: '/'`（name `console`，component KawaiiLayout，redirect `/home`），17 个管理页作为 children（原 path 不变，URL 兼容）；`/login`、`/register`、`/retrieve-password`、`/voice-print`（免登录/独立全屏页）平级放外层。`protectedRoutes` 判断逻辑不变（by name）。

**HeaderBar 处置**：不物理删除文件（home.vue 搜索历史等逻辑迁移到 SidebarSearch/Topbar 时逐步搬运），但管理页全部不再引用；#4 完成后 HeaderBar 退役归档（删除或留作 legacy）。`featureManager` 与 6 语言 i18n 菜单文案沿用。

#### 1.1.3 页面迁移策略：拍板「嵌套路由 + 每页最小模板手术」，弃用逐页包裹

**对比**：逐页 `import KawaiiLayout` 包裹不动 router，但 20 页每页加 wrapper 标签 + slot 传参，且页面骨架重复渲染、后续新页面容易漏包。嵌套路由一次性重构 router，页面只做**删除**（删 `<HeaderBar/>`、`<VersionFooter/>` 标签与 import、删各自 scoped 里的 `min-width:900px`/`height:100vh` 根样式），模板手术是纯减法，机械可 grep 验证（改造后 `grep -l HeaderBar src/views` 应为 0）。

**22 页工作量评估**（views 共 22 文件 + auth.scss，17,188 行）：

| 批次 | 页面 | 行数规模 | 手术内容 |
|---|---|---|---|
| 免布局（不动） | login / register / retrievePassword / VoicePrint | 443/376/324/309 | 不进骨架，仅吃主题 token（P1 可选粉彩化） |
| 批次1（#5） | home / roleConfig / DeviceManagement / MemoryManagement / KnowledgeBaseManagement / KnowledgeBaseItem / TemplateQuickConfig | 905/2419/554/1244/1269/622/481 | 模板手术 + 记忆参数面板（C 线并入 MemoryManagement）+ 细节粉彩化 |
| 批次2（#6） | 其余 11 个管理页（ModelConfig/Params/Dict/Provider/ServerSide/AgentTemplate/Ota/User/Feature/ReplacementWord/AddressBook/VoiceClone/VoiceResource） | 437~1064 | 纯模板手术 + 冒烟 |

- 单页手术：删 2 标签 + 2 import + 根样式 3-5 行，10-20 分钟/页；roleConfig（2419 行）与 home（设备网格自适应）额外各 0.5d。
- 预估：#4 框架 2.5d（Layout/Sidebar/Topbar/搜索迁移/router 重构）；#5 批次1 约 3d（含 C 线面板）；#6 批次2 约 2.5d（含回归）。

### 1.2 B 线：设备配置云端记忆（音量/亮度等）

#### 1.2.0 目标语义（先定义再设计）

- **单源真相**：设备配置（volume/brightness/未来 theme 等）持久化于**云端 `ai_device_config`**；设备 NVS 是本地缓存。
- **双通道同步**：① 用户对设备说话（LLM 工具调用）→ 实时生效 + 服务器拦截上报云端；② 设备开机/重连 → 云端配置下发覆盖本地。
- **冲突规则**：最后写入者胜（last-write-wins）。运行期以设备实时状态为准，开机以下发的云端值为准（有值才覆盖）。

#### 1.2.1 全链路时序

**链路① 开机恢复（云端 → 设备）**：

```
设备开机
 └─ WS/MQTT Connect → 发 hello（features.mcp=true, audio_params）
     └─ Python connection.open()
         ├─ 立即 send welcome_msg（server hello，含 audio_params/session_id）   [connection.py:250 附近]
         └─ create_task(_background_initialize())                              [L250]
             └─ _initialize_private_config_async()
                 └─ HTTP → Java POST /config/agent-models（Bearer server.secret）
                     └─ ConfigServiceImpl.getAgentModels（改）
                         ├─ 原有：模型/提示词/agent_id/plugins…
                         └─ 新增：deviceService.getDeviceConfig(device_id)
                              → result.put("device_config", {...} or 不put)
                 ← private_config 含 device_config
             ├─ self.device_config = private_config.get("device_config")（存 conn）
             └─ 若非空：await websocket.send({"type":"device_config","payload":{...}})
设备侧
 └─ websocket_protocol.cc OnData：type≠hello → on_incoming_json_            [L186-192]
     └─ application.cc OnIncomingJson（改：新增 "device_config" 分支）
         └─ Schedule([]{ Board::ApplyDeviceConfig(payload) })   // 主任务执行，防阻塞
             ├─ volume 有值且 ≠ codec->output_volume() → SetOutputVolume(v)（写 NVS）
             └─ brightness 有值且 ≠ backlight->brightness() → SetBrightness(b, true)
```

- **固件必改点（顺带修复）**：删除 `my_s3_tft_board.cc:91` 的 `SetOutputVolume(50)` 硬编码（该行每开机覆盖 NVS 恢复值；`AudioCodec` 构造已从 NVS 恢复，无记录时基类默认 70，首次烧录语义可接受）。`RestoreBrightness()` 保留不动。
- **幂等**：设备侧对比当前值再应用，重连重复下发无闪变；NVS 键沿用 `audio/output_volume`、`display/brightness`（NVS 键是持久 API，不改名——AGENTS.md 约定）。
- **MQTT 路径**：MQTT 网关透传 JSON 到同一 `OnIncomingJson`，设备侧改动天然覆盖双 transport；Python 侧 `connection.py` 为 ws 直连实现，mqtt gateway 转发路径是否透传自定义 type 需验证（§6 待明确④）。
- **未绑定设备**（`need_bind=True`）：private_config 为空 → 不下发，设备维持 NVS 本地值。

**链路② 说话改配置（设备执行 + 云端记账）**：

```
用户："音量调到 80"
 └─ LLM function call: self_audio_speaker_set_volume(volume=80)   ← 注意下划线名（sanitize 后）
     └─ unified_tool_handler.handle_llm_function_call
         └─ ToolManager.execute_tool(tool_name, arguments)        [unified_tool_manager.py:73]
             ├─ get_tool_type → ToolType.DEVICE_MCP
             └─ DeviceMCPExecutor.execute（改：入口处新增钩子）
                 ├─ 【新】DeviceConfigSync.on_tool_call(conn, tool_name, arguments)
                 │    ├─ 白名单匹配（§5.2）命中 self_audio_speaker_set_volume → {volume:80}
                 │    ├─ 参数校验（int, 0-100，越界丢弃）
                 │    └─ asyncio.create_task(fire-and-forget 上报，不阻塞设备调用)
                 │        └─ ManageApiClient.report_device_config(mac, {"volume":80})
                 │            └─ Java POST /config/device-config（server 过滤器）
                 │                └─ DeviceConfigService.upsert → ai_device_config（JSON merge）
                 └─ （原有逻辑）call_mcp_tool → 设备执行 SetOutputVolume(80) → 写 NVS
```

- **拦截点选在 `DeviceMCPExecutor.execute` 入口**而非 `ToolManager.execute_tool`：前者是所有设备端工具的必经点且持有 `conn`（可取 mac），后者混入 server 函数/MCP endpoint 工具，需再判类型；钩子独立成模块，失败（网络/Java 不可用）只记日志不影响工具执行——**记账失败不阻塞设备控制**。
- **乱序**：同一连接内工具调用串行发起，上报 task 并发但目标都是同 device 的 upsert merge；极端乱序最终一致（后续任何一次说话/开机都会再同步）。可接受，不做版本号。
- **管理台手动改配置（P1 预留）**：`ai_device_config` 由 Java 直接 upsert，下次开机生效；若设备在线想即时生效，复用链路①的消息（Python 侧开放内部 API 主动 push —— 本期不做，接口预留见 §3.4）。

#### 1.2.2 拦截规则表（设备配置类工具白名单）

| 工具名（设备注册原名） | sanitize 后（拦截匹配名） | 提取参数 | config key | 值域 | 固件应用点 |
|---|---|---|---|---|---|
| `self.audio_speaker.set_volume` | `self_audio_speaker_set_volume` | `volume:int` | `volume` | 0-100 | `AudioCodec::SetOutputVolume` |
| `self.screen.set_brightness` | `self_screen_set_brightness` | `brightness:int` | `brightness` | 0-100 | `Backlight::SetBrightness(b, true)` |
| `self.screen.set_theme`（预留） | `self_screen_set_theme` | `theme:string` | `theme` | `light`\|`dark` | LVGL ThemeManager（P1） |

**扩展接口设计**：白名单在 Python 侧以模块级 `DEVICE_CONFIG_TOOL_RULES` 字典声明（`core/providers/tools/device_config_sync.py`），结构 `{tool_name: {key, type, min, max, extractor?}}`；新增设备配置项 = 固件加 MCP 工具 + 此表加一行 + 固件 `ApplyDeviceConfig` 加一个 case，三栈协议只增不改。Java 侧对上报 config 的 key 做同样的白名单校验（防注入任意键），两端白名单以本文 §5.2 为契约源。

### 1.3 C 线：记忆引擎参数可视化（复用现有接口）

**原则：零新增后端接口**（除 VO 加一个透传字段），全部复用 `/memory/agents` + `/models/**`。

**数据流**：

```
MemoryManagement.vue（#5 批次1 改造时并入）
 ├─ 现有：Api.memory.getMemoryAgents() → agents（VO 新增 memModelId 字段）
 ├─ 选择 Agent → computed: engineParamsVisible = engine === 'mem_holographic'
 │    （mem_local_short/nomem/mem0 等无本地参数可调 → 显示引导文案，mem0 展示平台侧参数为 P1 可选）
 ├─ 新组件 components/memory/MemoryEngineParams.vue
 │    ├─ mounted：Api.model.getModelConfig(agent.memModelId)
 │    │    → ModelConfigDTO { id, modelType:'Memory', modelCode:'mem_holographic',
 │    │       modelName, configJson:{type,db_dir,auto_extract,default_trust,
 │    │       min_trust_threshold,temporal_decay_half_life} }
 │    ├─ 字段元数据：Api.model.getModelProviders('Memory')
 │    │    → provider.fields[]（key/label/type/default，202610051800.sql 种子）
 │    │    → 按 type 映射控件：string→el-input / boolean→el-switch / number→el-input-number
 │    ├─ 编辑保存：Api.model.updateModel（PUT /models/Memory/mem_holographic/{id}，
 │    │    configJson 全量回传——复用模型配置编辑语义）
 │    └─ 保存后提示："参数已保存，对该智能体的新对话生效（设备重连或新会话后加载）"
 └─ 生效语义（写明到 UI）：Memory provider 在 connection 建立时 init_memory 读 config，
    修改后**不热更新**当前连接；下一次设备连接/会话生效。
```

- **Java 改动仅 2 处**：`MemoryAgentVO` 加 `memModelId` 字段；`MemoryFactServiceImpl.listAgents` 组装时 `vo.setMemModelId(agent.getMemModelId())`（AgentDTO 已含该字段）。
- **布局**：参数面板放在 Agent 选择器下方、记忆列表上方，用 `el-collapse`（默认收起，标题"引擎参数"），避免挤压列表首屏；或右侧抽屉（编辑态才展开）——交给 #5 实施时按视觉稿定，组件独立成文件两种皆可插。
- **权限**：MemoryManagement 菜单 superAdmin 限定，`/models/{id}`、`PUT /models/...` 均 superAdmin——一致，普通用户不可见此面板（页面本身就不可见）。
- **i18n**：6 语言补 `memoryManagement.engineParams.*` 文案（`npm run check:i18n` 通过）。

---

## 2. 文件清单（三栈新增/修改全列表）

> manager-web 路径前缀 `manager-web/src/`；manager-api 前缀 `manager-api/src/main/java/yuhe/`（changelog 除外）；yuhe-server 前缀 `yuhe-server/`；固件前缀 `main/`（yuhe-esp32 仓库根）。

### 2.1 Vue（manager-web）——A 线 + C 线前端

| # | 文件 | 新/改 | 说明 |
|---|---|---|---|
| V-1 | `styles/kawaii/tokens.scss` | 新 | `--kawaii-*` CSS 变量定义（§5.3 命名） |
| V-2 | `styles/kawaii/element-overrides.scss` | 新 | Element 组件粉彩覆盖（唯一 `.el-*` 全局覆盖文件，按组件分节） |
| V-3 | `styles/kawaii/index.scss` | 新 | 入口（tokens + overrides + 公共皮肤类 .kawaii-card 等） |
| V-4 | `main.js` | 改 | element css 与 global.scss 之后 import kawaii/index.scss（1 行） |
| V-5 | `components/layout/KawaiiLayout.vue` | 新 | 双栏骨架（侧栏+顶栏+router-view+VersionFooter） |
| V-6 | `components/layout/KawaiiSidebar.vue` | 新 | 左栏容器（品牌、用户卡片、折叠态） |
| V-7 | `components/layout/SidebarMenu.vue` | 新 | 分组导航（吸收 HeaderBar 菜单项与 superAdmin/featureStatus 可见性） |
| V-8 | `components/layout/KawaiiTopbar.vue` | 新 | 顶栏（页面标题/搜索入口/语言切换/用户下拉） |
| V-9 | `components/layout/SidebarSearch.vue` | 新 | 设备搜索（从 HeaderBar/home.vue 迁移，含搜索历史 localStorage 逻辑） |
| V-10 | `router/index.js` | 改 | 嵌套路由重构（父 `/` → KawaiiLayout + children；4 个免登录页外置）；protectedRoutes 语义不变 |
| V-11 | `components/HeaderBar.vue` | 改(退役) | #4 完成后删除（菜单/搜索/用户逻辑迁移至 V-6~V-9） |
| V-12 | `views/home.vue` | 改 | 批次1：删 HeaderBar/VersionFooter 引用 + 根样式；设备网格适配 |
| V-13 | `views/roleConfig.vue` | 改 | 批次1：同上（2419 行，重点回归） |
| V-14 | `views/DeviceManagement.vue` | 改 | 批次1：同上 |
| V-15 | `views/MemoryManagement.vue` | 改 | 批次1：同上 + 嵌入 V-16 参数面板 |
| V-16 | `components/memory/MemoryEngineParams.vue` | 新 | C 线引擎参数表单（读 /models/{id} + provider fields，写 PUT /models/...） |
| V-17 | `views/KnowledgeBaseManagement.vue`、`KnowledgeBaseItem.vue`、`TemplateQuickConfig.vue` | 改 | 批次1：模板手术 |
| V-18 | `views/ModelConfig.vue`、`ParamsManagement.vue`、`DictManagement.vue`、`ProviderManagement.vue`、`ServerSideManager.vue`、`AgentTemplateManagement.vue`、`OtaManagement.vue`、`UserManagement.vue`、`FeatureManagement.vue`、`ReplacementWordManagement.vue`、`AddressBookManagement.vue`、`VoiceCloneManagement.vue`、`VoiceResourceManagement.vue` | 改 | 批次2（#6）：纯模板手术 |
| V-19 | `apis/module/model.js` | 改 | 确认/补齐 `getModelConfig`、`updateModel` 导出（已有 L221/L255，仅核对入参形态） |
| V-20 | `i18n/zh_CN.js` + `zh_TW/en/de/vi/pt_BR.js` | 改 | 菜单重组 + engineParams 文案 6 语言 |
| V-21 | `views/login.vue`、`register.vue`、`retrievePassword.vue`、`VoicePrint.vue` | 改(可选P1) | 免布局页仅吃 token 粉彩化，不进骨架 |

### 2.2 Java（manager-api）——B 线 + C 线

| # | 文件 | 新/改 | 说明 |
|---|---|---|---|
| J-1 | `modules/device/entity/DeviceConfigEntity.java` | 新 | `ai_device_config` 实体（MyBatis-Plus，@TableName） |
| J-2 | `modules/device/dao/DeviceConfigDao.java` | 新 | Mapper（继承 BaseDao，无 XML 或一个 upsert XML） |
| J-3 | `modules/device/service/DeviceConfigService.java` + `impl/DeviceConfigServiceImpl.java` | 新 | `getByDeviceId` / `upsertByMac(mac, configMap)`（key 白名单+范围校验、JSON merge、查 mac→device_id） |
| J-4 | `modules/config/controller/ConfigController.java` | 改 | 新增 `POST /config/device-config`（server 过滤器链内，入参 {macAddress, config}） |
| J-5 | `modules/config/service/impl/ConfigServiceImpl.java` | 改 | `getAgentModels` 组装 device_config（约 +8 行：查表→有值 put，无值不 put） |
| J-6 | `modules/memory/vo/MemoryAgentVO.java` | 改 | +`memModelId` 字段（C 线） |
| J-7 | `modules/memory/service/impl/MemoryFactServiceImpl.java` | 改 | listAgents 填 memModelId（1 行） |
| J-8 | `resources/db/changelog/2026xxxx_device_config.sql` + `db.changelog-master.yaml` | 新/改 | `ai_device_config` 建表 changeSet（DDL 见 §3.1） |

### 2.3 Python（yuhe-server）——B 线

| # | 文件 | 新/改 | 说明 |
|---|---|---|---|
| P-1 | `core/providers/tools/device_config_sync.py` | 新 | `DEVICE_CONFIG_TOOL_RULES` 白名单 + `on_tool_call(conn, tool_name, arguments)` 钩子（匹配/校验/异步上报） |
| P-2 | `core/providers/tools/device_mcp/mcp_executor.py` | 改 | `DeviceMCPExecutor.execute` 入口调用钩子（try/except 包裹，失败仅日志，~6 行） |
| P-3 | `config/manage_api_client.py` | 改 | +`report_device_config(instance, mac_address, config)`（仿 report()，api_guard 装饰，POST /config/device-config） |
| P-4 | `core/connection.py` | 改 | `_initialize_private_config_async`：消费 `private_config.get("device_config")` 存 `self.device_config` 并 send `{"type":"device_config","payload":...}`（~10 行；在 `chat_history_conf` 消费块附近追加） |

### 2.4 固件（yuhe-esp32/main）——B 线

| # | 文件 | 新/改 | 说明 |
|---|---|---|---|
| F-1 | `application.cc` | 改 | `OnIncomingJson` 新增 `"device_config"` 分支 → `Schedule` 调 `ApplyDeviceConfig`（~25 行） |
| F-2 | `application.h` | 改 | 声明 `void ApplyDeviceConfig(const cJSON* payload)`（或放 Board 层，见下） |
| F-3 | `boards/common/board.cc` + `board.h` | 改 | `Board::ApplyDeviceConfig(payload)`：读 volume/brightness → 对比当前值 → `SetOutputVolume` / `SetBrightness(b,true)`；放 Board 层符合 AGENTS.md"最窄拥有层"（音视频硬件能力属 Board） |
| F-4 | `boards/my-s3-tft/my_s3_tft_board.cc` | 改 | **删除 L91 `SetOutputVolume(50)` 硬编码**（NVS 恢复由 AudioCodec 构造负责），同步更新注释 |
| F-5 | `mcp_server.cc` | 不改 | set_volume/set_brightness 工具已存在且落 NVS（音量经 AudioCodec 基类落盘） |

---

## 3. 接口设计

### 3.1 `ai_device_config` 表结构（J-8 DDL）

```sql
CREATE TABLE `ai_device_config` (
    `device_id`   VARCHAR(32) NOT NULL COMMENT '设备ID（关联 ai_device.id）',
    `config_json` JSON        NOT NULL COMMENT '设备配置（schema 见 design §5.1，如 {"volume":80,"brightness":60}）',
    `creator`     BIGINT      COMMENT '创建者',
    `create_date` DATETIME    COMMENT '创建时间',
    `updater`     BIGINT      COMMENT '更新者',
    `update_date` DATETIME    COMMENT '更新时间',
    PRIMARY KEY (`device_id`),
    CONSTRAINT `fk_ai_device_config_device` FOREIGN KEY (`device_id`) REFERENCES `ai_device`(`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='设备云端配置表（B线：配置云端记忆）';
```

- 一设备一行，config_json 整体覆盖式 merge（upsert 时读旧值 → 白名单键合并 → 写回）。
- 外键按项目惯例评估（ai_device 系列表未见外键约束则去掉 FK，只留索引语义——主键即 device_id，无需额外索引）。

### 3.2 Java 对外/服务间接口

**POST `/config/device-config`**（server 过滤器，Python→Java 回写）：

```json
// 请求
{ "macAddress": "AA:BB:CC:DD:EE:FF", "config": { "volume": 80 } }
// 响应 Result<Void>：code=0 成功
```
校验：mac 必须能定位设备（否则 PARAMS_GET_ERROR）；config 非空对象；每个 key 必须在白名单（volume/brightness[+theme P1]）且值过范围校验（int 0-100）；非法键忽略并告警日志（宽松策略：合法键照常落库，不让一次脏数据丢整包）。

**getAgentModels 下发字段**（J-5，private_config 新增 key）：

```json
// 有配置时：
"device_config": { "volume": 80, "brightness": 60 }
// 无配置时：整个 key 不出现（Python 侧 get 判空跳过，设备维持本地 NVS 值）
```
- 仅 `getAgentModels(macAddress, ...)` 设备分支注入；`getConfig(true)` 管理控制台分支**不注入**（tmp register 流程无设备上下文）。

### 3.3 Python 侧消费与下发（P-4）

```python
# connection.py _initialize_private_config_async 内，chat_history_conf 消费块后追加：
device_config = private_config.get("device_config")
if isinstance(device_config, dict) and device_config:
    self.device_config = device_config
    payload = json.dumps({"type": "device_config", "payload": device_config})
    await self.websocket.send(payload)   # mqtt_gateway 连接：conn_from_mqtt_gateway=True 时跳过（待明确④）
```

### 3.4 内部推送 API（P1 预留，本期不实现）

`yuhe-server` 内部管理 handler（复用 memory_handler 的 AuthToken 模式）：`POST /api/device-config/push {mac_address, config}` → 定位活跃 conn → send device_config 消息（在线即时生效）。本期管理台改配置仅落库、开机生效；此接口在 `http_server.py` 路由表预留注释。

### 3.5 固件消费点（F-1~F-3）

```cpp
// application.cc OnIncomingJson 新增分支（与 "mcp"/"system" 平级）：
} else if (strcmp(type->valuestring, "device_config") == 0) {
    auto payload = cJSON_GetObjectItem(root, "payload");
    if (cJSON_IsObject(payload)) {
        Schedule([this, payload_str = std::string(cJSON_PrintUnformatted(payload))]() {
            Board::GetInstance().ApplyDeviceConfig(/* parse payload_str */);
        });
    }
}

// board.cc：
void Board::ApplyDeviceConfig(const cJSON* payload) {
    auto volume = cJSON_GetObjectItem(payload, "volume");
    if (cJSON_IsNumber(volume)) {
        int v = volume->valueint;
        if (v >= 0 && v <= 100 && GetAudioCodec()->output_volume() != v) {
            GetAudioCodec()->SetOutputVolume(v);      // 基类实现内含 NVS 落盘
        }
    }
    auto brightness = cJSON_GetObjectItem(payload, "brightness");
    if (cJSON_IsNumber(brightness)) {
        int b = brightness->valueint;
        if (b >= 0 && b <= 100) {
            if (auto backlight = GetBacklight()) {
                if (backlight->brightness() != b) backlight->SetBrightness((uint8_t)b, true);
            }
        }
    }
    // theme 等扩展 case 预留
}
```
- cJSON 所有权：`OnIncomingJson` 回调持有的 root 在回调返回后释放（`websocket_protocol.cc:195` cJSON_Delete），`Schedule` 异步执行必须**先打印成字符串**再进闭包（示例已如此）。
- MQTT：mqtt 网关透传 JSON 同走 `OnIncomingJson`，固件侧无需区分 transport。

---

## 4. 任务分解（映射 #3~#8 边界与依赖）

| 任务 | 边界（做什么/不做什么） | 依赖 | 验收要点 |
|---|---|---|---|
| #3 设计系统 | V-1/V-2/V-3/V-4 + 公共皮肤类；产出 token 表与组件覆盖清单；**不动任何页面** | #2 本文档 | tokens/overrides 编译通过；在临时 demo 页（或直接批次1首页联调）验证 22 类组件粉彩化；CDN 开/关两模式视觉一致 |
| #4 布局框架 | V-5~V-11 + V-10 路由重构 + 搜索迁移；HeaderBar 退役；**页面内容零改动**（除删引用） | #3 | 全路由可达、URL 不变；grep 无页面再引用 HeaderBar；superAdmin/featureStatus 菜单可见性与旧版一致；6 语言 check:i18n 通过 |
| #5 批次1 | V-12~V-17 + V-16/V-19/V-20（C 线面板并入 MemoryManagement） | #3 #4（可并行开发，合入需 #4 完成）；C 线数据依赖 #7 的 J-6/J-7 | 7 页手术完成 + 记忆参数面板读/编/存全链路（可先用 mock memModelId） |
| #6 批次2 | V-18 全部 13 页模板手术 + 冒烟回归 | #3 #4 | grep 校验 + 逐页冒烟清单（表格/弹窗/分页/表单四类交互） |
| #7 配置同步后端 | J-1~J-8 + P-1~P-4（Java 与 Python 可拆两人并行，契约=§3+§5.2 白名单） | #2 | ①curl 模拟 getAgentModels 含/不含 device_config；②模拟 execute_tool 白名单工具→ai_device_config 落库；③非法键/越界值被拒；④与固件联调前置：本地 ws 客户端收到的 device_config 报文正确 |
| #8 配置同步固件 | F-1~F-4（board 层 ApplyDeviceConfig + 删音量硬编码） | #2（与 #7 并行，联调需 #7） | my-s3-tft 构建 + 烧录：①改音量→重启保持；②服务器改库→重启设备自动应用；③device_config 与本地相同值不重复应用（日志验证） |
| QA 全链路（#9） | 三线集成验证 | #5 #6 #7 #8 | 见 §6 风险清单逐项 + PRD 验收标准 |

**并行度**：#3/#4（前端线）、#7（后端线）、#8（固件线）三线并行；#5/#6 在 #3/#4 后接力；C 线前端（V-16）数据字段依赖 J-6/J-7，可先 mock。

---

## 5. 共享约定（跨栈契约）

### 5.1 设备配置 JSON schema（唯一契约源）

```jsonc
// ai_device_config.config_json & device_config payload & 上报 config 三处同构
{
  "volume":    <int 0-100>,      // 音量（self.audio_speaker.set_volume）
  "brightness": <int 0-100>      // 亮度（self.screen.set_brightness）
  // P1 预留: "theme": "light" | "dark"
}
```
- 三栈（Java 存储/校验、Python 透传/提取、固件应用）以此为准；键缺省=不管理该项；值以最后一次写入为准。

### 5.2 工具名白名单（Python 拦截 + Java 校验共用）

| 原始工具名 | 拦截匹配名（sanitize 后） | 参数 | config key | 校验 |
|---|---|---|---|---|
| `self.audio_speaker.set_volume` | `self_audio_speaker_set_volume` | `volume` | `volume` | int, 0≤v≤100 |
| `self.screen.set_brightness` | `self_screen_set_brightness` | `brightness` | `brightness` | int, 0≤v≤100 |
| `self.screen.set_theme` | `self_screen_set_theme` | `theme` | `theme` | enum light/dark（P1） |

- 扩展流程：固件加 MCP 工具 → 本表加行（Python `DEVICE_CONFIG_TOOL_RULES` + Java `DeviceConfigServiceImpl` 校验表）→ 固件 `ApplyDeviceConfig` 加 case。**双端白名单不一致时以交集生效**（Python 不上报的键永远不会到 Java）。
- 消息类型名固定为 `device_config`（WS JSON `type` 字段），负载固定 `payload` 对象。

### 5.3 主题 token 命名（kawaii/）

```
--kawaii-bg                页面底色        #FFF7FA（奶白粉）
--kawaii-surface           卡片/面板       #FFFFFF
--kawaii-surface-2         表头/次级面板   #FFF0F4
--kawaii-primary           主色            #FF8FAB（蜜桃粉）
--kawaii-primary-hover     主色悬停        #FF7A97
--kawaii-primary-light     主色浅底        #FFE3EA
--kawaii-text              主文字          #4A3B40
--kawaii-text-secondary    次文字          #9C8A90
--kawaii-border            边框            #F5D8E0
--kawaii-radius            大圆角          14px
--kawaii-radius-sm         小圆角          8px
--kawaii-shadow            软阴影          0 4px 16px rgba(255,143,171,.14)
--kawaii-success/--kawaii-warning/--kawaii-danger/--kawaii-info   状态色粉彩化
```
- 全部前缀 `--kawaii-`，定义于 `:root`；Element 映射只写在 element-overrides.scss（如 `.el-button--primary{background:var(--kawaii-primary);border-color:var(--kawaii-primary)}`）；业务组件只允许消费 `var(--kawaii-*)`，禁止裸色值。

---

## 6. 风险与待明确

| # | 项 | 分析与对策 | 归属 |
|---|---|---|---|
| 1 | **PWA/SW 缓存迁移** | InjectManifest precache 随构建 hash 变化自动更新，SW 已有 SKIP_WAITING；旧 tab 停留旧版属 workbox 正常行为，CacheViewer（Alt+C）可排障。真正风险：CDN 模式下 unpkg element css 与 bundle 覆盖层的**加载顺序**——对策：element-overrides 选择器按 specificity≥原版设计（类叠加以 `.el-button.el-button--primary` 级别写），必要时 `!important`，不依赖顺序；#3 交付前双模式截图比对 | #3 |
| 2 | **22 页回归成本** | 模板手术是纯减法可 grep 验证；真正的回归点是各页 scoped 根样式（min-width:900px/height:100vh）与双栏滚动容器的冲突 → #4 出"根样式手术规范"（删哪些保留哪些）供 #5/#6 机械执行；roleConfig（2419 行）单列 0.5d 专项回归 | #4/#5/#6 |
| 3 | **固件 NVS 写入时机** | `ApplyDeviceConfig` 在 Schedule 主任务执行，`SetOutputVolume`/`SetBrightness(permanent=true)` 内部写 NVS——均为短写（<10ms 单 key），不阻塞事件循环；风险点是 device_config 到达时设备可能正在播放 TTS，音量突变体验可接受（用户改配置本意）；亮度 SetBrightness 有渐变定时器（5ms tick），在主任务跑无冲突 | #8 |
| 4 | **MQTT 网关透传待验证** | mqtt gateway（独立部署组件）转发 ws 消息是否原样透传自定义 `type:"device_config"` 未验证；对策：P-4 先按 `conn_from_mqtt_gateway=True` 跳过下发（保守），#7 联调期用网关环境实测后再放开 | #7 |
| 5 | **getAgentModels 管理台分支** | `getConfig(true)`（tmp register）不注入 device_config——已设计排除；回归确认管理台"模拟设备连接"功能不受影响 | #7 |
| 6 | **上报竞态/乱序** | 同连接工具调用串行、上报 fire-and-forget，极端乱序 LWW 最终一致；不做版本号（复杂度不值）；上线后观察日志若有频繁抖动再加 debounce | #7 |
| 7 | **C 线参数生效语义** | config 修改对新连接生效、不热更新当前连接——UI 必须明示（"设备重连或新会话后生效"）；P1 可选做 push 通知（复用 §3.4 思路触发 provider 重建） | #5 |
| 8 | **MemVendor 参数面板范围** | 本期仅 mem_holographic 有可视化参数；mem0 平台参数（API Key 等）继续在模型配置页管理，不在记忆页重复；nomem/mem_local_short 显示引导文案 | #5 |
| 9 | **主题与品牌图冲突** | HeaderBar 品牌区（yuhe-ai 六语言图）迁 Sidebar 后浅底适配；login 页 P1 才粉彩化，避免首期范围膨胀 | #4 |
| 10 | **固件其他板卡** | ApplyDeviceConfig 放 Board 基类，全部板型自动获得；但 zhengchen 等板也有开机 `SetOutputVolume(60/100/0)` 硬编码（唤醒/静音场景，属瞬时设置非默认值，语义不同）——**不改**，仅 my-s3-tft 的"上电默认值"硬编码必须删 | #8 |

---

## 附：关键侦察坐标（供实施者直达）

- 拦截注入点：`core/providers/tools/device_mcp/mcp_executor.py:31` `DeviceMCPExecutor.execute`；工具分发：`core/providers/tools/unified_tool_manager.py:73` `execute_tool`；LLM 调用入口：`unified_tool_handler.py:150+` `handle_llm_function_call`（含 `% {function_name}` 显示消息）
- 下发注入点：`core/connection.py:800` `_initialize_private_config_async`（device_max_output_size 消费在 L917-919，device_config 消费紧随其后追加）
- Java 组装点：`modules/config/service/impl/ConfigServiceImpl.java:118` `getAgentModels`（agent_id 注入先例 L207）
- 服务间 HTTP：`config/manage_api_client.py`（report() 是上报范式，L273-293；api_guard 装饰器 L192）
- 固件：`main/mcp_server.cc:52-70`（两个工具注册）；`main/audio/audio_codec.cc:31/40-46`（NVS 音量）；`main/boards/common/backlight.cc:33/46-53`（NVS 亮度）；`main/boards/my-s3-tft/my_s3_tft_board.cc:91`（硬编码删除点）；`main/application.cc:600+`（OnIncomingJson 分支插入位，"mcp" 分支在 L716 附近）；`main/protocols/websocket_protocol.cc:186-192`（非 hello 消息转发设备 JSON）
- 前端：`src/main.js`（css import 顺序）；`src/App.vue`（无布局）；`src/router/index.js:244`（protectedRoutes）；`src/components/HeaderBar.vue`（菜单可见性逻辑源）；`src/views/MemoryManagement.vue:445-480`（agents 加载，memModelId 消费点）；`src/apis/module/model.js:221/255`（getModelConfig/updateModel）；`202610051800.sql`（mem_holographic provider fields 种子，C 线字段元数据来源）

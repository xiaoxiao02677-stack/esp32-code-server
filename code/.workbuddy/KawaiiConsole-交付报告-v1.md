# 小智 · Kawaii 控制台大改造 + 设备配置云端记忆 + 记忆参数可视化
## 项目交付报告 v1（2026-10-06）

---

## 〇、一句话结论

三线（Kawaii 控制台 / 设备配置云端记忆 / 记忆参数面板）**代码交付全部落盘并通过各栈编译校验**；P0 安全契约全部闭合；**尚未做真机三栈联调与部署上线**（两处前置阻塞 + 一个可选项）。

---

## 一、A 线 · Kawaii 控制台改造（前端）

### 1.1 设计系统（kawaii-minimal）

| 文件 | 内容 |
|---|---|
| `manager-web/src/styles/kawaii/tokens.scss` | 63 个 `--kawaii-*` CSS 变量（primary #FF8FAB / bg #FFF7FA / radius 14px …） |
| `manager-web/src/styles/kawaii/element-overrides.scss` | **唯一允许写 `.el-*` 全局覆盖**的文件，22 类组件粉彩化（button/input/table/dialog/switch/slider/tabs/message/card/form/select/checkbox/radio/pagination/collapse/tooltip/progress/tag/drawer/date-picker/upload） |
| `manager-web/src/styles/kawaii/index.scss` | `@import tokens + element-overrides` 聚合入口 |
| `manager-web/src/main.js` L11 | `import './styles/kawaii/index.scss';`（置于 global.scss 之后，满足 V-4 序位） |

关键设计决策：
- **不走 `element-variables.scss` 重编译**：Element UI 整包 CSS 决定，改用后置 CSS 变量覆盖层。CDN 双模式（dev/build）均兼容，specificity 不依赖加载顺序。
- `prefers-reduced-motion: reduce` 下所有 spring 回弹降级为无 transform。
- 禁用项已落：无深色底、无霓虹/荧光、无黑粗边框、无 terminal 风格。

### 1.2 双栏布局（嵌套路由）

父路由 `path:'/'` / name `console` → component `KawaiiLayout`，redirect `/home`；原 22 个管理页全部作为 children（**path 不变，URL 100% 兼容**，protectedRoutes by name 语义不变）。4 个免登录页外置不进侧边栏。

| 组件 | 说明 |
|---|---|
| `components/layout/KawaiiLayout.vue` | 左栏 232px sticky + 右侧 `flex:1;min-height:0` 内容区（overflow-y:auto）+ VersionFooter |
| `KawaiiSidebar.vue` | 侧边栏容器 |
| `SidebarMenu.vue` | PRD 七分组；模块项 `rounded-2xl p-4`，选中 `bg #FFE3EA`、hover `scale(1.03)` |
| `KawaiiTopbar.vue` | 56px 顶栏 |
| `SidebarSearch.vue` | 设备搜索完整迁移（含 localStorage 历史），修复 `home.vue` 中 `SEARCH_HISTORY_KEY=undefined` 隐性 bug → `'agentSearchHistory'` |

**calc 遗留方案统一**：原 `.main-wrapper` 硬编码 `calc(100vh-63px-35px)` → 全量改为 `flex:1;min-height:0`，由 KawaiiLayout 主内容区承载滚动。22 页口径一致。

### 1.3 22 页手术 + 构建

- 22 个管理页全部删除 `<HeaderBar />`（import / components / 模板标签）与根级 `min-width:900px`、`height:100vh` 锁定。
- 校验结果：`grep -rl HeaderBar src/views`（排除免登录 3 页）→ **22/22 ALL CLEAR（0 残留）**。
- `npm run build --no-clean` → **DONE**，dist 可部署。

---

## 二、B 线 · 设备配置云端记忆（ESP 配置持久化）

### 2.1 全链路（说话 → 记住 → 开机沿用）

```
用户"音量调到100"
  → LLM function call
  → unified_tool_manager.py:73 execute_tool
  → DeviceMCPExecutor.execute  ← mcp_executor.py:30 入口钩子
  → device_config_sync.py:on_tool_call  ← 白名单校验 + 范围钳制
  → manage_api_client.py:306 report_device_config（httpx + Bearer server.secret）
  → Java POST /config/device-config
  → DeviceConfigService.upsert → MySQL ai_device_config（device_id PK + config_json JSON）
设备开机 hello
  → connection.py:925 读 private_config['device_config']
  → 下发 {"type":"device_config","payload":{...}}
  → 固件 application.cc OnIncomingJson device_config 分支
  → Schedule → Board::ApplyDeviceConfig（对比当前值、幂等、写 NVS）
```

### 2.2 交付文件

**Python（`yuhe-server`）— 4 文件**

| 文件 | 改动 |
|---|---|
| `core/providers/tools/device_config_sync.py` | 新增。白名单 `DEVICE_CONFIG_TOOL_RULES`（`self_audio_speaker_set_volume`→volume / `self_screen_set_brightness`→brightness，均为 int 0-100）+ `Semaphore(8)` + `need_bind`/`read_config_from_api` 双 gate |
| `core/providers/tools/device_mcp/mcp_executor.py` | L12 import、L30 挂载 `on_tool_call` 钩子（双重 try/except） |
| `config/manage_api_client.py` | L306 新增 `report_device_config()`（api_guard 装饰，POST /config/device-config） |
| `core/connection.py` | L112-113 初始化 `self.device_config=None`；L925-935 下发（need_bind + conn_from_mqtt_gateway 双跳过） |

**Java（`manager-api`）— 5 新 4 改**

新：`DeviceConfigEntity` / `DeviceConfigDao` / `DeviceConfigService` / `DeviceConfigServiceImpl` / `DeviceConfigDTO`；
改：`ConfigServiceImpl`（下发白名单纵深）、`MemoryAgentVO` + `MemoryFactServiceImpl`（C 线 memModelId）、`202610060030.sql`（建表 `ai_device_config`）+ `master.yaml` 追加、`ConfigController`（POST /config/device-config）。

**固件（`yuhe-esp32`）— 4 文件 +135/-6**

| 文件 | 改动 |
|---|---|
| `main/application.cc` | L719 `device_config` 分支；L726-739 RAII `cJSON_PrintUnformatted` 判空后 `Schedule` 交线程 |
| `main/boards/common/board.cc` | L62-105 `Board::ApplyDeviceConfig`：valuedouble 整性判断 + 0-100 + 幂等（≠当前值才写 NVS） |
| `main/boards/…/my_s3_tft_board.cc` | 删 L91 开机 `SetOutputVolume(50)` 硬编码（**真缺陷根因**） |
| `board.cc` / `application.cc` | 补 `#include <cmath>`（floor 整性判断依赖） |

**架构侦察修正（重要）**：音量/亮度固件侧**原本已**持久化 NVS（`audio_codec.cc:40-46`、`backlight.cc:46-53`）；真缺陷是 `my_s3_tft_board.cc:91` 开机硬编码强制回 50；工具名早已 sanitize（点→下划线）；server hello 先于 private_config，故 `device_config` 必须是**独立 JSON 消息**而非并入 hello。

---

## 三、C 线 · 记忆 API 参数可视化

`manager-web/src/components/memory/MemoryEngineParams.vue`（**905 行**，fe-page3 交付）

- 位置：记忆管理页 `el-collapse` 内，默认**收起**的「引擎参数」面板。
- 5 个参数：
  | 参数 | 控件 | 说明 |
  |---|---|---|
  | `db_dir` | 只读 + 复制按钮 | 路径直显 |
  | `auto_extract` | `el-switch` | 自动抽取总开关 |
  | `default_trust` | 滑杆 step 0.05 + 数值框 | 默认信任度 |
  | `min_trust_threshold` | 滑杆 + 三色条 + 即时语义反馈 | 最小信任阈值 |
  | `temporal_decay_half_life` | number | 0 表示衰减关闭（面板折叠条件） |
- 非 holographic 引擎时给出引导文案；竞态令牌防并发串数据。
- i18n 六语言 `engineParams`，每语言 35 keys。
- 测试：`test:contract` **9/9**、`test:unit` **7/7** 通过。

---

## 四、P0 安全契约闭合清单（全部已验证）

| 栈 | 契约 | 状态 |
|---|---|---|
| 固件 | `cJSON_PrintUnformatted` 返回 NULL 判空（避免解引用崩溃） | ✅ RAII unique_ptr 承载 |
| 固件 | `valuedouble` 整性判断，拒绝 100.5 / 80.9 类小数 | ✅ `dv == floor(dv)` + `<cmath>` |
| Python | `isinstance(v,int) and not isinstance(v,bool)`（bool 是 int 子类，必须显式排除） | ✅ |
| Python | `need_bind` / `read_config_from_api` gate（防 MAC 伪造持久化） | ✅ |
| Python | `Semaphore(8)` 上报并发上限（防 DoS） | ✅ |
| Java | Jackson `instanceof Integer` 严格校验（拒绝 80.9 而非截断为 80） | ✅ `toIntValue` L99-111 |
| Java | 下发侧白名单纵深（ConfigServiceImpl L218-225 sanitized HashMap） | ✅ |
| 网关 | `conn_from_mqtt_gateway=True` 时下发与上报**均跳过**（透传未验证，保守） | ✅ |

---

## 五、跨栈验证结果

| 项 | 命令 | 结果 |
|---|---|---|
| 前端 | `npm run build --no-clean` | **DONE**（dist 就绪） |
| 前端 | `grep -rl HeaderBar src/views`（排除免登录 3 页） | **22/22 ALL CLEAR** |
| Python | `py_compile` + 全量单测 | **OK / 29-29 通过** |
| Java | `mvn compile` | **EXIT 0** |
| 固件 | 静态走查（含 `#include <cmath>` 补刀后） | **无解引用风险** |
| AOCI | 固件仓索引（1068 条）终态 verify/check/guide | **aligned / complete** |

---

## 六、待办与阻塞（按优先级）

### 🔴 P0 阻塞（部署前必须处理）
1. **`yuhe-server/data/.config.yaml:9` 含生产 secret（2d7b6bde-…）已入库**。
   → 上线前必须：① 两端同步轮换 `server.secret`；② 清除该文件版本历史/出库；③ 加 `.gitignore` + 部署模板化。
2. **QA #9 三栈真机联调未跑**（A5-A8 未验证）：说话改音量 → 服务器落库 → 重启设备 → 沿用新值。**这是本次交付唯一未证的功能闭环**。

### 🟡 P1 顺延（本期不做）
- 果冻动效全家桶细则（squash-and-stretch 交互细节补齐）
- 移动端侧边栏抽屉（当前仅桌面双栏）
- 按钮/Logo 粉彩化重绘（token 已就位，图形资产未重画）
- 设备配置管理 UI（P1-4，管理后台查看/清库入口）
- MQTT 网关透传实测
- `JSON_MERGE_PATCH` 原子 upsert（现为非原子读改写 LWW）
- theme P1（绿/粉主题切换）+ PWA 双模式截图比对

### 🟢 工具沉淀（已完成）
- `.workbuddy/qa_memory/` — 上项目测试资产
- `manager-web/scripts/qa/tag-balance-check.js` — Vue 模板标签配平可复用脚本
- AOCI 三量认知索引工具链：`.workbuddy/aoci_tmp/`（mcp_aoci.py / authoring_lib.py / drive2.py / batch_loop.py / batch_gen.py / author_fw.py）

---

## 七、交付物索引

| 类别 | 路径 |
|---|---|
| 需求文档 | `.workbuddy/prd-kawaii-console-v1.md` |
| 架构设计 | `.workbuddy/design-kawaii-console-v1.md`（444 行） |
| 会话上下文 | `.workbuddy/memory/2026-10-06.md` |
| 设计系统 | `manager-web/src/styles/kawaii/{tokens,element-overrides,index}.scss` |
| 布局组件 | `manager-web/src/components/layout/*.vue`（5 个） |
| 记忆面板 | `manager-web/src/components/memory/MemoryEngineParams.vue` |
| B 线 Python | `yuhe-server/core/providers/tools/device_config_sync.py` 等 4 文件 |
| B 线 Java | `manager-api/modules/device/**`、`modules/config/**`、`resources/db/changelog/202610060030.sql` |
| B 线固件 | `yuhe-esp32/main/{application.cc,boards/common/board.cc,boards/…/my_s3_tft_board.cc}` |
| 固件索引 | `yuhe-esp32/aoci.code.txt`（1068 条 FRAS） |

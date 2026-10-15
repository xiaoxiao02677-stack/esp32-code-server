# LVGL 消息框组件需求文档

- 版本：v1.0
- 日期：2026-10-13
- 状态：待评审（仅需求规格，未改动任何代码）
- 范围：xiaozhi-esp32 固件（G:/demo/21_xiaozhi/code/small_secreen/xiaozhi-esp32），显示子系统
- 依据：本仓库现有代码（只读分析），关键文件与行为均注明出处

---

## 1. 背景与目标

### 1.1 需求原文

> LVGL 消息框组件，支持**文本自动换行**、**高度自适应**、**屏幕自适应**、**队列显示**。

### 1.2 目标（G1–G4）

| 编号 | 目标 | 一句话定义 |
|---|---|---|
| G1 | 文本自动换行 | 长文本在消息框内按宽度约束自动折行显示，任何长度下不溢出、不截断（除容量上限） |
| G2 | 高度自适应 | 消息框高度随折行行数动态变化（单行最小高度 ↔ 最大高度），无需人工设定 |
| G3 | 屏幕自适应 | 消息框几何参数（宽/高/边距/字号/最大行数）由屏幕分辨率与屏幕形态（方屏/圆屏）自动推导，换屏零硬编码 |
| G4 | 队列显示 | 多条消息按到达顺序排队展示，按序推进（自动超时推进 / 手动翻页），支持优先级与容量上限 |

### 1.3 定位

- 现有固件**已有三套并存的聊天消息 UI**，本组件不是从零造轮子，而是把散落的"消息框"能力**收敛为统一组件**，并补齐 G1–G4 中缺失的部分。
- 设计原则沿用圆屏皮肤注释中的既有约定（`round_screen_display.h:14-18`"不要影响原 api 功能"）：**渲染层可替换，Application/协议/MCP/音频链路零改动**。

---

## 2. 现状盘点（代码事实，只读分析结论）

### 2.1 三套并存的聊天消息 UI

由 `main/Kconfig.projbuild:874-895` 的 choice `MESSAGE_STYLE` 决定（三选一），编译期互斥：

| 模式 | Kconfig | 实现位置 | 换行 G1 | 高度自适应 G2 | 屏幕自适应 G3 | 队列 G4 |
|---|---|---|---|---|---|---|
| 默认模式 | USE_DEFAULT_MESSAGE_STYLE | `lcd_display.cc:854-1130`（`#else` 分支，即非微信分支） | 仅当 `USE_MULTILINE_CHAT_MESSAGE=y`（`lcd_display.cc:979-1001`，`LV_LABEL_LONG_WRAP`）；默认是单行 `LV_LABEL_LONG_SCROLL_CIRCULAR`（:1016-1033） | 仅多行分支（`bottom_bar_` 高 `LV_SIZE_CONTENT`，:983）；默认单行固定高 `line_height + spacing(8)`（:1005） | 部分：宽取 `LV_HOR_RES`、字号取主题字体（:996/:1019） | 无，单条最新覆盖（:1101-1102） |
| 微信模式 | USE_WECHAT_MESSAGE_STYLE | `lcd_display.cc:387-852`（`#if` 分支） | 有（`LV_LABEL_LONG_WRAP`，:642，气泡宽 ≤ 屏宽 85%） | 有（气泡 `LV_SIZE_CONTENT`，:646） | 部分：宽按 `LV_HOR_RES * 85/100`（:624） | 有：滚动列表（flex 列 + 垂直滚动，:492-509），容量 MAX_MESSAGES=20（P4 为 40，:537-541），超限删最旧（:558-575） |
| 表情模式 | USE_EMOTE_MESSAGE_STYLE | `emote_display.cc`（未使用 LVGL 消息框） | 不适用 | 不适用 | 不适用 | 不适用 |
| 圆屏皮肤（my-s3-tft 240×240） | 板级皮肤，与 choice 正交 | `boards/my-s3-tft/round_screen_display.cc` | 有（气泡 label 宽 180 + `LV_LABEL_LONG_WRAP`，:124-125） | **无**：气泡固定 200×50（:112），超长文本由 `SetChatMessage` **硬截断 96 字符**（:236-243），第三行起被裁掉 | **无**：全部坐标硬编码（:71/77/86/113/135） | 无：单气泡"只显示最新一条"（:230-244） |

> 说明：圆屏皮肤**继承 SpiLcdDisplay**（`round_screen_display.h:20`），但完全覆写 SetupUI（`round_screen_display.cc:30-51`），因此上述默认/微信两套布局代码对 my-s3-tft **均不生效**。这是 G1–G4 差距最大的场景。

### 2.2 消息数据流（消息框的所有"喂数"入口）

| 入口 | 调用点 | 消息框 API |
|---|---|---|
| 服务端 `{"type":"stt"}`（用户语音识别结果） | `application.cc:766-786` | `SetChatMessage("user", text)` |
| 服务端 `{"type":"tts","state":"sentence_start"}`（AI 回复逐句） | `application.cc:749-764` | `SetChatMessage("assistant", text)`（逐句覆盖） |
| 服务端 `{"type":"notify"}`（主动推送） | `application.cc:717-720` → `StartNotification`（:1362）→ `notify_player` 字幕回调 | 每命中一条字幕：`SetChatMessage("assistant", text)`（:1394） |
| MCP `{"type":"mcp"}` 内 JSON-RPC 工具 | `application.cc:795-799`（payload 经 McpServer）→ 内部再走上述通道 | 同上 |
| 本机状态/错误（system） | `application.cc:107/250/494/501/519/665/871/927/941/1285-1286` | `SetChatMessage("system", …)` |
| 通知条 | `application.cc:156/168/175/415` | `ShowNotification(msg, 30000)` |

结论：**消息框的输入源全部已经存在，是单条"最新覆盖"语义**；"队列显示"需要在 Display 层把多条消息接住并按序播放，协议层不动。

### 2.3 与"队列"相关的现成机制

| 机制 | 位置 | 与 G4 的关系 |
|---|---|---|
| `NotifyPlayer` 音频队列 | `notify/notify_player.h:74-75`（`kMaxQueueSize = 5`）、`notify_player.cc:53-73`（Urgent 打断 / Low 忙时丢弃 / Normal 入队）、:316-324（取最高优先级出队） | **音频层已有优先级队列**，但字幕显示仍逐条覆盖，无显示队列 |
| 微信模式滚动消息列表 | `lcd_display.cc:542-743` | 视觉上是"历史队列"，但无定时推进/翻页语义 |
| `ShowNotification` 超时机制 | `lvgl_display.cc:171-192`（`esp_timer_start_once` + 3s 默认） | 单条定时隐藏的先例，可作"自动推进"的模板 |
| `DisplayLockGuard` + `Schedule` 主任务串行化 | `display.h:104-126`、`application.cc:1428-1434` | 队列推进必须走这条路径，避免跨任务动 LVGL 对象 |

### 2.4 硬性环境约束（设计必须服从）

1. **LVGL 版本 v9.5.x**：`main/idf_component.yml:69`（`lvgl/lvgl: ~9.5.0`）+ `esp_lvgl_port: ~2.9.0`（:70）。API 用 v9（`lv_obj_set_size/remove_flag/clear_flag`、`LV_SIZE_CONTENT`、`lv_obj_update_layout`），不使用 v8 遗留 API（`round_screen_display.cc:20-22` 已注明两者差异）。
2. **内存**：SPI 屏 draw buffer 仅 `width_ * 20` 行（`lcd_display.cc:180`），无整帧缓冲；图片缓存走 PSRAM（≥8MB 时 2MB，:124-161）。消息框组件禁止引入大块常驻内存（多页文本缓冲、整屏快照除外）。
3. **线程模型**：LVGL 对象只能在持有 `DisplayLockGuard` 且由 `Application::Schedule` 回到主任务后操作（`lvgl_display.cc` 全部公共接口均为该模式）。队列的定时器回调用 `ESP_TIMER_TASK`（:32）再 `Schedule` 回主任务。
4. **字体/主题**：字号必须取自 `LvglTheme`（`text_font()->font()`、`spacing(scale)`、`line_height`），不允许硬编码像素字号；主题切换时所有消息框对象必须重绑字体，否则悬空指针崩溃（`round_screen_display.cc:271-296` 的 2026-10-08 事故注释）。
5. **多板卡并存**：Display 抽象（`display.h:38-102`）是唯一入口，组件必须落在抽象层，方屏（默认/微信模式）与圆屏皮肤必须都能消费。
6. **圆屏特有约束**：240×240 圆形屏，物理可视安全区半径约 100（`round_screen_display.h:5` 注释）；气泡当前占位 200×50 @ y=-55，与中心表情（120×120 @ y=-15）、底部提示（y=-12）存在空间竞争，高度自适应必须设**上限**防止盖住表情。

---

## 3. 需求定义（FR，逐条可验收）

### 3.1 FR-G1 文本自动换行

- FR-G1.1 组件内所有文本 label 一律 `LV_LABEL_LONG_WRAP`；宽度按 FR-G3.2 的宽度模型计算，不写死。
- FR-G1.2 支持中英文混排与 emoji/noto 字符合排；换行计算交由 LVGL v9 label 引擎，组件不自行分词（现有 `bubble_label_` 已证明可用，`round_screen_display.cc:125`）。
- FR-G1.3 超长文本策略显式化：**不再静默截断**。当前圆屏 `SetChatMessage` 的 96 字符硬截断（`round_screen_display.cc:235-243`）在组件模式下废弃，改为"折行 + 高度上限 + 溢出策略"（见 FR-G2.3）。
- FR-G1.4 单条消息文本长度上限由组件常量统一控制（建议沿用服务端字幕粒度，单条 ≤ 512 字节），超出部分按 FR-G2.3 处理并打 WARN 日志。
- 验收：240 宽下 100 个中文字符的 assistant 消息显示为多行完整文本，行尾无越界，行数 = 文本自然折行数（受最大高度裁剪的除外）。

### 3.2 FR-G2 高度自适应

- FR-G2.1 消息框高度 = `LV_SIZE_CONTENT`（v9），由内部 label 折行行数决定；单行时取最小高度 `line_height + 2×pad`。
- FR-G2.2 高度必须设定**上限**：
  - 方屏：≤ 屏高 40%（默认模式）/ 由聊天区 flex 布局自然约束（微信模式现有行为）；
  - 圆屏：≤ 100px（约 3–4 行 @14 号字），超出时启用 FR-G2.3。依据：中心表情下沿约 y=45，气泡顶部 y = 240-55-h 不得侵入 y<130 区域，h ≤ 55+（与现有 200×50 的视觉比例持平）。
- FR-G2.3 溢出策略（三选一，建议实现优先级从上到下）：
  1. 达到最大高度后内部滚动（label 外层容器 `LV_DIR_VER` 滚动 + 隐藏滚动条）；
  2. 分页（见 FR-G4）；
  3. 末行省略号（LVGL label 无原生省略，需自定义绘制，仅作备选）。
- FR-G2.4 高度变化时容器重新 `lv_obj_align` 到底部锚点（圆屏：`LV_ALIGN_BOTTOM_MID, 0, -55`），保证"从底部向上生长"，现有先例 `lcd_display.cc:1111-1117`。
- 验收：同一气泡分别显示 1 行 / 2 行 / 5 行文本，气泡高度递增且不超过上限；5 行场景可滚动看到第 5 行；表情与提示元素位置全程不被遮挡。

### 3.3 FR-G3 屏幕自适应

- FR-G3.1 建立**屏幕规格表**（编译期常量即可），组件所有几何量从表推导：

| 参数 | 推导规则 | 240×240 圆屏取值（示例） | 240×320 方屏取值（示例） |
|---|---|---|---|
| 气泡最大宽 | `screen_w × 0.85`（圆屏再减去左右安全边距，圆形边缘按 y 查表） | 180（= 现硬编码值） | 204 |
| 边距/内边距 | `theme->spacing(4)`（`lvgl_theme.h:36`，`spacing_ = 2`） | 8px | 8px |
| 字号 | `theme->text_font()` 不变 | 14 号（内置字体） | 14 号 |
| 圆角 | `min(spacing(4)×2, 16)` | 16 | 8 |
| 最小高 | `line_height + 2×pad` | 约 30 | 约 30 |
| 最大高 | 方屏：`screen_h × 0.4`；圆屏：100 | 100 | 128 |
| 底锚点 y 偏移 | 圆屏 -55；方屏 0 | -55 | 0 |

- FR-G3.2 组件提供 `MessageBoxStyle` 结构（见 §4.2），由构造参数/SetConfig 传入，**不允许在组件实现内出现 `LV_HOR_RES` 以外的裸数字坐标**。
- FR-G3.3 支持横竖屏与 offset（`lcd_display.cc:210-212` 的 `lv_display_set_offset`）——组件只依赖逻辑坐标系，不感知物理偏移。
- FR-G3.4 主题切换（`SetTheme`）后组件自动重取字号/spacing 并重布局，禁止要求调用方手动刷新。
- 验收：同一组件代码分别在 240×240 圆屏与 240×320 方屏编译运行，布局符合规格表；无任何编译期/运行期屏宽假设报错。

### 3.4 FR-G4 队列显示

- FR-G4.1 消息帧格式（与现有语义兼容）：

```
struct MessageBoxItem {
    std::string role;      // "assistant" / "user" / "system"（沿用现有三元组）
    std::string text;
    uint32_t    duration_ms;   // 0 = 自动（按字符数估算阅读时长），否则按指定时长展示
    NotifyPriority priority;   // 复用 notify/notify_player.h:16-20 枚举
};
```

- FR-G4.2 入队 API（Display 基类扩展，默认实现保持"最新覆盖"语义，见 §4.1）。
- FR-G4.3 队列行为：
  - 容量上限 5（对齐 `NotifyPlayer::kMaxQueueSize`，可配置）；
  - 队满时丢弃**最低优先级最旧**一条（对齐 `notify_player.cc:64-70` 现成策略）；
  - `priority == Urgent` 时清空队列立即显示（对齐 :53-56 打断语义）；
  - 顺序推进：当前条计时到期 → 取下一条；队列空 → 恢复默认文案（"我在呢"，对齐 `round_screen_display.cc:232` 语义）。
- FR-G4.4 推进计时：
  - 自动模式：`duration_ms = 0` 时按 `max(3000, min(15000, 200ms × 字符数))` 估算；
  - 计时器用 `esp_timer`（`ESP_TIMER_TASK`）→ `Application::Schedule` 回主任务再改 UI（对齐 `lvgl_display.cc:23-36` 模式）；
  - 手动翻页：预留接口（`Next()/Prev()`），my-s3-tft 可映射到 BOOT 键事件（`round_screen_display.cc:352-387` 三事件现有实现），本需求不强制实现。
- FR-G4.5 新消息到达时：`assistant` 逐句消息（tts sentence_start）默认**追加进队**而非覆盖，避免"逐句覆盖导致只看到最后一句"（现有 `application.cc:759-763` 行为在队列模式下变为逐句入队）。
- FR-G4.6 与 `ClearChatMessages()` 语义兼容：清空队列 + 恢复默认文案；与 `SetHideSubtitle`（`lcd_display.h:56`）兼容：隐藏时不显示但不丢队列。
- 验收：连发 3 条通知 + 1 条 Urgent → Urgent 立即显示，其余按序显示且不丢不重；队满 5 条后再入队 → 最旧低优先级被丢弃并有日志；无消息 30s 后气泡回到"我在呢"。

### 3.5 FR-G0 兼容性需求

- FR-G0.1 Application、协议解析、MCP、音频链路**零改动**（全部需求在 Display 层消化）。
- FR-G0.2 默认模式/微信模式/圆屏皮肤三者均可用组件替换其"消息区"，编译开关（Kconfig）不变。
- FR-G0.3 无屏板（`NoDisplay`，`display.h:128-132`）与表情模式（EmoteDisplay）不受影响：新接口给空实现/默认实现。
- FR-G0.4 现有崩溃防护经验必须保留：隐藏占位对象族（`round_screen_display.cc:138-204`）策略继续有效，组件创建/销毁不得绕过 SetTheme 的重绑路径。

---

## 4. 组件接口规格（建议，供评审）

### 4.1 Display 基类扩展（display.h）

```cpp
class Display {
public:
    // 新增（默认实现 = 现 SetChatMessage 的"最新覆盖"语义，保证存量皮肤行为不变）
    virtual void EnqueueChatMessage(const char* role, const char* text,
                                    uint32_t duration_ms = 0,
                                    NotifyPriority priority = NotifyPriority::kNotifyPriorityNormal) {
        SetChatMessage(role, text);   // 默认退化：单条覆盖
    }
    virtual void AdvanceMessageQueue() {}   // 手动推进（可选实现）
    virtual void SetMessageBoxConfig(const MessageBoxStyle& cfg) {}  // 屏幕自适应参数下发
    virtual int  PendingMessageCount() const { return 0; }
    // …… 其余接口不动
};
```

> `NotifyPriority` 定义在 `notify/notify_player.h:16`，display.h 引入该头即可（或前向声明枚举移到公共头，评审决定）。

### 4.2 MessageBoxStyle（屏幕规格表落点）

```cpp
struct MessageBoxStyle {
    int max_width_px   = 0;      // 0 = 自动按 screen_w*0.85 推导
    int min_height_px  = 0;      // 0 = line_height + 2*pad
    int max_height_px  = 100;    // 0 = 不设上限（方屏微信模式）
    int bottom_margin  = 55;     // 底锚点偏移（圆屏 55 / 方屏 0）
    int radius         = 16;
    int queue_capacity = 5;
    OverflowMode overflow = OverflowMode::Scroll;  // Scroll / Paginate / Ellipsis
};
```

### 4.3 组件内部结构（lvgl_message_box.h/cc 新文件，不触碰现有布局文件）

```
lv_message_box_create(parent, style) -> lv_obj_t* box
  ├─ lv_label（LV_LABEL_LONG_WRAP，宽 = max_width）
  ├─ 内部滚动容器（h ≤ max_height，LV_DIR_VER，滚动条 OFF）
  └─ 队列状态机（std::deque<MessageBoxItem> + esp_timer + Schedule 回调）
```

---

## 5. 影响面与兼容矩阵

| 改动点 | 文件 | 性质 | 风险 |
|---|---|---|---|
| 新增组件 | `main/display/lvgl_message_box.{h,cc}` | 新增 | 低（独立文件） |
| 基类扩展 4 个虚函数 | `main/display/display.h` | 增补 | 低（默认实现） |
| 圆屏皮肤接入组件 | `main/boards/my-s3-tft/round_screen_display.{h,cc}` | 替换 `bubble_/bubble_label_` 渲染实现 | **中**：SetTheme/占位族/KeyEvent/Tick1s 全部引用 `bubble_label_`（:143-204/:207-212/:287/:316-318/:342-344 等），需逐点回归 |
| 微信模式（可选接入） | `main/display/lcd_display.cc` `#if CONFIG_USE_WECHAT_MESSAGE_STYLE` 分支 | 可选 | 低（本模式已具备 G1/G2/G4 雏形） |
| 默认多行模式（可选接入） | 同文件 `USE_MULTILINE_CHAT_MESSAGE` 分支 | 可选 | 低 |
| 调用点 | `application.cc` 不强制改；如需逐句入队（FR-G4.5）则 `:762`/`:1394` 两处改调 `EnqueueChatMessage` | 极小 | 低 |

不涉及：协议（WebSocket/MQTT/YH）、MCP Server、音频服务、状态机、服务端。

---

## 6. 需求拆分与实施顺序（建议）

| 阶段 | 内容 | 依赖 |
|---|---|---|
| P0 | 组件骨架 + FR-G1 + FR-G2（换行、自适应高、溢出策略）+ 单元自测（host 模拟或 P4 板） | 无 |
| P1 | FR-G3 规格表 + MessageBoxStyle 下发通道 | P0 |
| P2 | FR-G4 队列状态机 + esp_timer 推进 | P0 |
| P3 | 圆屏皮肤接入（替换单气泡）+ 回归 2026-10-08 事故清单（SetTheme 重绑、占位族、KeyEvent、Tick1s） | P0–P2 |
| P4 | 默认/微信模式可选接入 + `application.cc` 两处逐句入队 | P2 |

---

## 7. 验收标准总表（QA 用例）

| # | 用例 | 预期 |
|---|---|---|
| 1 | 圆屏 240×240 显示 100 字中文消息 | 多行完整显示，无截断，气泡高度 ≤ 100px |
| 2 | 1/2/5 行消息切换 | 气泡高度逐步变化、自底向上生长、表情不被遮挡 |
| 3 | 5 条消息入队后第 6 条到达 | 最旧最低优先级被丢弃，日志可见 |
| 4 | Urgent 消息在队列播放中到达 | 立即清队显示 Urgent |
| 5 | 队列空 30s | 恢复默认文案"我在呢"，表情恢复 neutral |
| 6 | 运行时切换主题（display theme） | 无崩溃（无 0x0 字体访问），消息区重新布局 |
| 7 | 相同固件源码编出方屏与圆屏两板 | 布局各自符合规格表，无硬编码越界 |
| 8 | 字幕隐藏设置开启 | 气泡隐藏但队列继续推进，关闭后恢复显示 |
| 9 | 单条消息 512 字节超限 | 按溢出策略处理 + WARN 日志，无 OOM/崩溃 |

---

## 8. 风险与开放问题（评审项）

1. **圆屏高度上限与表情遮挡的平衡**：max_height=100 是推算值（§3.2 FR-G2.2），需实机确认 14 号字 4 行 + 滚动条在 200 宽气泡内的观感；若需更大高度，必须同步上移中心表情或缩小表情容器（120×120），属视觉取舍，需求文档不做决定。
2. **逐句入队 vs 单条覆盖**（FR-G4.5）：改 `application.cc:762` 调用语义会把 TTS 逐句字幕变成队列播放，需确认与"说话实时打断"（任务2）的交互——打断时队列应清空（`AbortSpeaking` 链路补一条 Clear 调用，评审确认）。
3. **通知字幕与消息队列的关系**：`NotifyPlayer` 已按音频时间轴驱动字幕（`application.cc:1391-1397`），若通知同时入显示队列会双轨驱动。建议：通知字幕继续走现有覆盖路径（它本身就是"队列"），组件队列只接管 TTS/STT/system 消息；或两者统一入队（评审二选一）。
4. **LVGL v9 末行省略号**无原生支持，若选 Ellipsis 溢出策略需自定义 `lv_draw_label` 回调，工作量需单独评估。
5. **P4/双核板**：MAX_MESSAGES 在 P4 为 40（`lcd_display.cc:537-541`），组件队列容量是否也按芯片分档，评审决定（建议统一 5，视觉语义与 notify 队列一致）。
6. **内存预算**：队列 5 条 × 512 字节上限 ≈ 2.5KB 常量内存，可接受；若提高容量/长度需重估（内部 SRAM 紧张，`lvgl_no_psram_pool.h` 板型尤甚）。

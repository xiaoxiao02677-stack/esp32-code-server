# 屿禾「小柚」LVGL 皮肤（hardware/sets）

> 代码：`hardware/sets/yuhe-esp32/main/display/yh_skin/`
> 视觉基准：`hardware/small_secreen/yuhe-esp32/main/boards/my-s3-tft/round_screen_display.{h,cc}`

四个 `yh-*` 版型的屏幕界面统一由这份共享皮肤渲染。**上电第一帧就是品牌开机画面**，
原生 yuhe 的状态栏 / 机器人 AI logo / 机型版本串在任何时刻都不会出现。

---

## 1. 为什么要自己做皮肤

原生 `LcdDisplay::SetupUI()` 在 240×240 圆屏上同时踩三个坑：

| 问题 | 现象 |
|---|---|
| 顶部状态栏（Wi-Fi 图标 + 电量 + 静音）挤在圆弧里 | 图标被圆角裁掉一半 |
| 开机居中画一个机器人 AI logo，并把 `SystemInfo::GetUserAgent()` 打进消息区 | 屏幕正中是「别人家的 AI」标识，下面还挂一行 `ESP32-S3-xxx/2.5.1` |
| 消息区是滚动列表，字号 14px | 配网 SSID、6 位激活码、升级百分比在 240 圆屏上根本读不清 |

所以：**只覆写渲染层**。`Application` 状态机、协议、MCP、音频链路一行不改；
`SetStatus/SetChatMessage/ShowNotification/SetEmotion/UpdateStatusBar` 的调用语义全部保留，
只是把它们画到圆屏该在的位置。

## 2. 为什么抽成共享层而不是 4 份复制

原来 `yh-n16r8-st7789` 目录里自带一份 `round_screen_display.cc` + `good_bg.c`（578KB 源码）。
如果再给 154 / cam / big 各复制一份：

- 4 份布局代码，改一个坐标要改 4 处，必然漂移；
- 4 份 578KB 背景图源码 = 4 份 flash 占用（每份 225KB 像素）；
- 圆屏（240×240）、横屏（320×240）、竖屏（240×320）本来就要参数化。

现在：`YhSkinProfile` 描述几何，`YhSkinDisplay` 一套实现，背景图只存一份。

## 3. 文件与职责

| 文件 | 职责 | 可改 |
|---|---|---|
| `yh_skin_types.h` | `YhSkinProfile`（几何画像）/ `YhSkinFonts`（字体集合）/ 背景图符号声明 | 契约，改前先看第 7 节 |
| `yh_skin_display.h/.cc` | 主界面：背景、时间、电量、表情、气泡、提示；协议钩子；按键三事件；1s 节拍；壁纸 | 主实现 |
| `yh_skin_boot.h/.cc` | 开机画面：品牌名 + 副标题 + 呼吸点 + 版本 + 状态行 + 进度条 | 独立 |
| `yh_skin_cards.h/.cc` | 系统态卡片：配网 / 激活码 / 升级 / 错误 | 独立 |
| `yh_skin_assets.c` | 240×240 RGB565 背景图（符号 `yh_skin_bg`），由脚本生成 | **不要手改** |

生成脚本与校验脚本：

```bash
# 重新生成背景资源（源数据只需换 --src）
python tools/gen_yh_skin_assets.py

# 单文件语法校验（不编译、不烧录；复用 build/compile_commands.json 的 flags）
python tools/yh_syntax_check.py --all-skin
python tools/yh_syntax_check.py main/boards/yuhe/yh-154tft-wifi/yh_set_154tft_wifi.cc
```

## 4. 视觉规格（240 基准，其他分辨率按短边等比缩放）

| 元素 | 240 基准坐标 | 圆屏处理 | 宽屏处理 | 字体 | 颜色 |
|---|---|---|---|---|---|
| 时间 `HH:MM` | 顶部居中 y=10 | 原样 | 原样 | 主题正文（20px） | `#C9B8D9` |
| 电量 | 顶部居中 y=28 | 原样 | 原样；无电池板整行隐藏 | 主题正文 | `#C9B8D9` |
| 表情头像 | 居中 120×120，y=-15 | 原样 | 原样 | noto emoji | `#FFF7FB` |
| 气泡 | 200×50，距底 55，圆角 16 | 原样 | 原样 | 主题正文 | 底 `#3A2440` 80%，边 `#FF7AA2` 1px |
| 气泡文字 | 宽 180，自动换行，最多 72 码点 | 原样 | 原样 | 主题正文 | `#FFF7FB` |
| 底部提示 | 「短按说话  长按菜单」距底 18 | 用 18（12 会被圆角裁） | 用 12 | 主题正文 | `#8B7A99` |
| 背景 | good.jpg 缩放铺满 | 原样 | 按长边放大后裁切 | — | 渐变兜底 `#2A1633 → #120B18` |

配色常量在 `yh_skin_display.h` 的 `kColor*`，开机画面与卡片各自复制了同一组常量
（三处必须同步改，注释里已标注）。

## 5. 开机时间线（「从开机就开始改变」）

| 阶段 | 屏幕上看到 | 代码路径 |
|---|---|---|
| 上电 → LVGL 起来 | 背光点亮，`SetupUI()` 立刻建主界面 + 盖一层不透明开机画面 | `YhSkinDisplay::SetupUI()` → `BuildSplash()` |
| 音频/网络初始化 | 深紫渐变 + 背景图 60% + 「屿禾工坊」+ 三点呼吸动画 + 右下版本号 | `yh_skin_boot.cc` |
| 连 Wi-Fi | 底部状态行出现「正在连接 xxx…」（不覆盖品牌字） | `SetStatus()` → `SplashAbsorbsStatus()` |
| 配网模式 | 全屏卡片：热点 / 密码 / 请连接后打开配网页面 | `ShowNotification()` → `ShowWifiCard()` |
| 激活 | 全屏卡片：6 位激活码逐位大字 + 说明 | `SetChatMessage("system", code…)` → `ShowActivationCard()` |
| 首次进待机（时间出现或收到真实对话） | 开机画面 300ms 淡出，交还主界面（时间/表情/气泡） | `DismissSplashIfNeeded()` |

**不再出现**：状态栏 Wi-Fi/电量图标、机器人 AI logo、`GetUserAgent()` 机型版本串
（`LooksLikeUserAgent()` 主动丢弃，日志里记 `Drop native user-agent banner`）。

## 6. 状态映射表

| 事件 | 屏幕表现 |
|---|---|
| `SetStatus("14:05")` | 顶部时间位；同时判定为「已进待机」→ 收起开机画面 |
| `SetStatus("正在连接…")` | 开机画面期间进状态行；之后再出现进气泡 |
| `SetChatMessage(role, text)` | 气泡显示最新一条，UTF-8 码点安全截断（≤72，超出补 `…`） |
| `SetChatMessage("system", "")` | 气泡复位为「我在呢」，并收起卡片 |
| `ShowNotification("进入配网模式…")` | 配网卡片 |
| `ShowNotification("升级中 42%")` | 升级卡片 + 进度条 |
| `SetEmotion("happy")` | 中心表情（走基类 emoji 资产/字符渲染；彩蛋期间不覆盖） |
| `UpdateStatusBar()` | 时间 + 电量；≤15% 非充电 → sad 表情 + 「我有点饿了，快充电」（每分钟一次） |
| `SetWallpaper(dsc)` | 背景换成用户壁纸（优先级：壁纸 > 主题背景 > good.jpg） |
| 短按 BOOT | laughing 表情 + 「我在听...」 |
| 双击 BOOT | 表情彩蛋轮播（5 组，10 秒后回 neutral）—— 仅 n16r8 支持 |
| 长按 BOOT | 待机：静音切换提示；聆听：回到「我在呢」 |
| 1s 节拍 | 彩蛋超时恢复；23:30「该睡啦，别熬夜」/ 07:00「早呀宝宝，今天也要加油」 |

## 6a. 灯语主题（DengYu）状态映射

灯语覆写渲染层但**复用全部骨架**（锁纪律/退休池/占位族/系统卡片），
上表通用项之外差异如下（详见 `theme/DengYu/README.md`）：

| 事件 | 灯语屏幕表现 |
|---|---|
| 设备态轮询（250ms） | 状态机真源：Listening→青苔绿光萤 / Speaking→迷你光萤+EQ / Connecting→思考三点 / FatalError→珊瑚红 / 其余→待机呼吸 |
| `SetChatMessage(user/assistant)` | 剧场字幕流：你=右对齐暖橙、灯灯=左对齐纸白；AI 回复逐字打字机（90~140ms/字抖动） |
| `SetChatMessage("system", …)` | 沿用基类（UA 过滤 / 激活码卡片），不入字幕流 |
| `ShowNotification(断连关键词)` | 珊瑚红放缓呼吸 +「信号走丢了」；「已连接」→ 解除 +「回来啦」（3 秒） |
| 短按 BOOT | 即时预置聆听光语（板级 ToggleChatState 主导） |
| 双击 BOOT | 轮换光萤配色 4 盘（炭火/月光/紫暮/珊瑚），NVS `dengyu/palette` 记忆 |
| 长按 BOOT | 静音状态短语（3 秒自动隐藏） |
| 每天 07:00 | 纸白晨间卡片 30 秒：大时钟 + 陪伴天数问候（NVS `dengyu/days`） |
| 字幕字体 | 动态文本跟随主题（basic→assets common）；固定文案用专属字档 `font_dengyu_16_4`（158 码位，`gen_dengyu_font.py` 生成——**组件 16_4 是限词表，固定文案直接绑会豆腐块**） |

## 7. 踩过的坑（改代码前必读）

1. **基类占位对象必须创建**。`LcdDisplay::SetTheme` / `LvglDisplay::ShowNotification`
   会无条件解引用 `container_ / content_ / network_label_ / mute_label_ / battery_label_ /
   status_label_ / notification_label_ / low_battery_popup_ / low_battery_label_ /
   chat_message_label_`。皮肤不建这些就没有视觉意义，但必须建成 1×1 隐藏对象，
   否则就是 2026-10-08 那次「Refreshing display theme 后 InstrFetchProhibited」崩溃循环。
2. **`SetTheme` 顺序不能反**：先 `LcdDisplay::SetTheme(theme)`（基类内部加锁 + 释放旧字体 +
   重绑基类 label），再在独立锁作用域里 `ApplyFonts()` 重绑皮肤自建 label。
   顺序反了布局测量会走已释放的字体指针。
3. **不要在持有 `DisplayLockGuard` 时调用会自锁的基类方法**（`SetEmotion` / `SetTheme`），
   否则死锁。低电量提示因此是「先算标志位、出锁后再调 `SetEmotion`」。
4. **LVGL 是 v9**：`lv_screen_active()` / `lv_obj_remove_flag` / `lv_image_set_src` /
   `lv_image_set_scale`；写 `lv_scr_act` / `lv_img_set_src` 会编不过。
5. **内置字体没有 ⚡ 这类符号**，会显示成方框；充电态用「充电85%」文案而不是图标。
6. **圆屏底部贴边会被裁**：基准原稿 y=-12 已改为 -18（圆屏专属），矩形屏用 -12。
7. **无电池板**（`yh-n16r8-st7789`）必须 `Round240(false)`，否则顶部永远挂一行空白电量。
8. **背景图用 `lv_image` 对象 + 缩放了**，不再用 `lv_obj_set_style_bg_image_src`：
   后者不能缩放，320×240 屏上会露出四周底色。
9. **两处"原生"行为要主动丢弃**：`SetChatMessage("system", GetUserAgent())` 与
   原生 `INITIALIZING` 文案，否则开机画面刚淡出就被它们写脏。

## 8. 如何验证

> 编译与烧录**由你手动执行**，agent 不代跑。

```bash
# 1) 编译（会先同步 staging → 固件树，再注册版型、编译、归档）
cd hardware/sets
python build.py            # 交互选版型；换版型后必须删 <FW>/build 全量重编

# 2) 烧录（不编译；三道闸默认开）
python flash.py            # 逐段 + 回读校验 + 启动检查

# 3) 起不来先体检
python diag.py
```

上电后逐条勾这份清单：

- [ ] 背光一亮就是深紫背景 + 「小柚」，**没有**状态栏、**没有**机器人 logo
- [ ] 品牌名下方三个点依次呼吸
- [ ] 右下角有版本号（与 `ai_ota.version` 一致）
- [ ] 连 Wi-Fi 时底部出现「正在连接…」，品牌画面不被冲掉
- [ ] 首次配网时出现「配网模式」卡片，热点名可读
- [ ] 激活时 6 位码是逐位大字，坐半米外能读
- [ ] 进待机后开机画面淡出，顶部出现 `HH:MM`，中心是表情，底部是「我在呢」
- [ ] 短按说话：表情变 laughing、气泡「我在听...」
- [ ] 说话时 320 宽屏（cam/big）元素不越界、不重叠
- [ ] 下发壁纸后背景替换成新图（清空壁纸回到 good.jpg）

## 9. 明确不做

- 不改 `Application` / 协议 / MCP / 音频链路；
- 不改壁纸协议与 `main/wallpaper/`（只消费 `SetWallpaper/ClearWallpaper`）；
- 不给 `yh-154tft-wifi` 加双击彩蛋：该板 `Button` 的 `long_press_time` 是默认值，
  加双击会改变单击手感，稳定性优先于彩蛋。

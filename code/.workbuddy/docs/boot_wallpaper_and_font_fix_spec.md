# 开机壁纸独立下发 + 开机首屏乱码修复 · 方案文档

> 需求一：壁纸分两种——**待机壁纸**（已有服务器下发，保持现状）与**开机壁纸**（新增，也由服务器下发）。
> 需求二：开机首屏文字乱码（连 WiFi 后正常）的根因与修复方案。
> 本文件为只读分析产物，不包含任何已落地的代码改动，供执行 agent 使用。
> 仓：固件 `G:/demo/21_xiaozhi/hardware/sets/yuhe-esp32/`（下称 FW）；
> Java `G:/demo/21_xiaozhi/yh/manager-api/`；Python `G:/demo/21_xiaozhi/yh/yuhe-server/`；
> 前端 `G:/demo/21_xiaozhi/yh/console-v2/`。

---

# 第一部分：开机文字乱码（需求二）

## 1.1 根因（已实证，非推测）

时序上，"第一个界面"（splash 开机画面）比 assets 分区加载**早**。

| 时刻 | 事件 | 字体 | 代码 |
|------|------|------|------|
| T0 | `LcdDisplay` 构造函数建主题，`current_theme_` 挂 **basic 档**字体（890 字） | `font_noto_sans_basic_20_4` | `main/display/lcd_display.cc:78` |
| T0 | `YhSkinDisplay::SetupUI()` → `ShowBootSplash()` → `BuildSplash()` 建 splash（品牌名/副标题/状态行/版本号） | basic 档 | `main/display/yh_skin/yh_skin_display.cc:521`、`yh_skin_boot.cc:113` |
| T1 | WiFi 连上 → `ActivationTask` → `CheckAssetsVersion` → `assets.cc` 加载 **common 档**（5258 字）→ `SetTextFont` + `SetTheme`（`assets.cc:419`） | common 档 | `main/application.cc:567`、`main/assets.cc:287-329` |
| T2 | `SetTheme` → `ApplyFonts()` → `SetSplashFont` 重绑 splash 文字 | common 档 | `main/display/yh_skin/yh_skin_display.cc:750-783`、`yh_skin_boot.cc:238-250` |

**结论：splash 首帧在 T0-T1 窗口渲染，用的是 basic 档。连 WiFi 后 common 档到位、文字重绑恢复正常。**
用户看到的"乱码"实际是 **basic 档缺字的方框**（`CONFIG_LV_USE_FONT_PLACEHOLDER=y` 会渲染成 □），
不是编码错误。

## 1.2 缺字实锤（`font_noto_sans_basic_20_4.c` 头部 `-r` range 逐字比对）

`main/CMakeLists.txt:891-910`（四个 yuhe 板型均 `font_noto_sans_basic_20_4`，890 字）：

| splash 文字 | 码点 | basic 档 | 结果 |
|-------------|------|----------|------|
| 品牌名「小柚」 | 柚 U+67DA | **缺** | **方框**（小 U+5C0F 也**缺**） |
| 副标题「AI 陪伴助手」 | 陪 U+966A / 伴 U+4F34 / 助 U+52A9 | **缺 ×3** | **方框**（AI 是 ASCII，正常） |
| 状态「正在连接网络」 | 正在连接网络 U+6B63/5728/8FDE/63A5/7F51/7EDC | 全有 | 正常 |
| 状态「激活设备」 | 激活设备 U+6FC0/6D3B/8BBE/5907 | 全有 | 正常 |
| 状态「检查新版本」 | 检查新版本 U+68C0/67E5/65B0/7248/672C | 全有 | 正常 |
| 状态「正在初始化」「请稍候」「下载资源失败」 | 化 U+5316 有；**初 U+521D 缺、始 U+59CB 缺、稍 U+7A0D 缺、候 U+5019 缺、搜 U+641C 缺、资 U+8D44 缺、源 U+6E90 缺、载 U+8F7D 缺、失 U+5931 缺、败 U+8D25 缺** | 部分缺 | **"正在初始化"会变成"正在□□□"** |
| 状态「配置同步中」 | 配 U+914D 有、置 U+7F6E 缺、同步中 OK | 部分缺 | "配置□步中" |
| 版本号 `2.5.1` | ASCII | 全有 | 正常 |

所以用户看到的"乱码"集中在 splash 的品牌名、副标题和部分状态文案。
**注意：splash 用 20px basic；待机界面用同一 basic 起步、但 common 到位后重绑，所以正常。**

## 1.3 修复方案（三选一，推荐 B）

### 方案 A：换字体——把 common 档链进固件（已评估，**不可行**）

common 20_4 在 noto-fonts `cbin/` 下（`font_noto_sans_common_20_4.bin`，构建期打进 assets 分区），
把 3+ MB 的 common 链接进固件会显著增大 app 体积、拖慢启动。**放弃。**

### 方案 B（推荐）：给 splash 单独编译一个小字体，链进固件

- splash 全部文案只有约 120 个字（品牌名+副标题+lang_config.h 全部状态文案+版本号 ASCII）。
  用现有 lv_font_conv 工具链（`78__xiaozhi-fonts` 组件就是 `--font ... --format lvgl --bpp 4` 生成的，
  basic_20_4.c 头部注释就是完整命令）从同一 TTF 生成一个 `font_splash_20_4.c`，
  `-r` 只带 splash 需要的码点，体积 < 50 KB。
- `main/CMakeLists.txt` yuhe 分支加 `SPLASH_FONT` 宏，或 `BuildSplash` 的 `SetFontIfAvailable` 里
  用这个字体代替 `fonts.text`（只在 `BuildSplash`/`SetSplashStatus` 用）。
- **最小改动**：只改 `yh_skin_boot.cc` 的 `BuildSplash`（把 `fonts.text` 换成 splash 专用字体），
  `SetSplashFont`（assets 到位后的重绑）保持原样——common 档照样接管，双保险。
- 需要给 TTF 或 noto-fonts 仓库路径；`78__xiaozhi-fonts` 组件的 `build/` 脚本是现成参考。

### 方案 C：绕过字体——把 splash 品牌字做成图片

- `tools/gen_yh_skin_assets.py` 已能生成 `yh_skin_bg`（图片资源），同样可生成"小柚 AI 陪伴助手"
  的 PNG 并链接进固件，splash 里用 `lv_image` 代替 `lv_label`。
- 但状态文案（连接中/激活中/初始化等）仍是动态文字，还是会有缺字，只能缓解品牌名部分。
- 若连状态文案也要根治，仍需 B 的字体。**B 覆盖面全，C 只是 B 的补充。**

## 1.4 执行清单（乱码）

| 步骤 | 内容 |
|------|------|
| F-1 | 收集 splash 全字符集：`main/assets/lang_config.h` 的 `Strings::*` 中开机阶段会显示的全部中文 + "小柚""AI 陪伴助手" + 版本号 ASCII |
| F-2 | 参考 `font_noto_sans_basic_20_4.c` 头部命令，用 lv_font_conv 从 noto TTF 生成 `font_splash_20_4.c`（-r 只含 F-1 码点） |
| F-3 | `main/CMakeLists.txt` 引入新字体文件（或放 `main/display/yh_skin/`） |
| F-4 | `yh_skin_boot.cc` `BuildSplash` 的 `SetFontIfAvailable(brand/sub/status)` 改用 splash 字体 |
| F-5 | `SetSplashFont` 不动（assets common 到位后仍会重绑，双保险） |

---

# 第二部分：开机壁纸由服务器下发（需求一）

## 2.1 现状链路（待机壁纸，已全部存在）

- **服务端**：`WallpaperMagController.java` 8 个端点（`/upload` `/dispatch` `/task/{id}` 等）。
  上传 → RGB565 转码（115200 字节）→ md5 → 存 `uploadfile/{md5}.bin`（`WallpaperServiceImpl.java:65-186`）。
  `wallpaperVersion = "3-" + md5`（`WallpaperServiceImpl.java:92`、`wallpaperVersion()`）。
  下发时把 `wallpaper` 子对象 JSON_MERGE_PATCH 进 `ai_device_config.config_json`
  （`configWallpaper()`，`WallpaperServiceImpl.java:810-822`）。
- **固件**：`application.cc:837-868` 解析 WS `{"type":"wallpaper","action":"set/clear"}`；
  `application.cc:982-991` 解析 `device_config.payload.wallpaper`。两路都进
  `WallpaperManager::HandleSet/HandleClear`。
- **控制台**：`components/DockNav.vue:25-32` 已有"壁纸下发"dock 按钮（浮层，不跳页）；
  `components/WallpaperDispatch.vue`（1319 行）承载上传/选择/下发/任务进度。

## 2.2 新增"开机壁纸"的最小改动设计

**语义**：boot_wallpaper 只在 splash 期间显示（`BuildSplash` 的 `info.background`），
待机壁纸仍是主界面背景。两者独立下载/独立 NVS/独立下发。

### 服务端（Java，改 WallpaperServiceImpl + WallpaperMagController）

1. `WallpaperMagController` 新增 `POST /wallpaperMag/uploadBoot`（或 `/upload` 加 `type=boot` 参数）
2. `WallpaperServiceImpl` 新增 `dispatchBoot`：写 `ai_device_config.config_json` 的 **`boot_wallpaper`**
   子对象（字段与 `wallpaper` 相同：version/url/md5/size/format）
3. Python `wallpaper_service` 新增 `push_boot_wallpaper`（或复用 `push_wake_words` 的
   `device_config` 推送模式）：推 `{"type":"device_config","payload":{"boot_wallpaper":{...}}}`，
   带 command_id 回执
4. `ConfigServiceImpl.java` 的白名单过滤（`sanitized.put` 那段，约 236-261 行）需要把
   `boot_wallpaper` 也放行（现只放行 volume/brightness/wake_word，wallpaper 是另一个通道）

### 固件（FW，改 WallpaperManager + application.cc + yh_skin_display）

5. `WallpaperRequest` 加 `kind` 字段（boot/idle）
6. `WallpaperManager::Impl` 双槽状态：`applied_version/buffer/dsc` 按 kind 各持一份
7. `application.cc:982-991` 解析 `device_config.payload.boot_wallpaper`，调 `HandleSet(request, kind=boot)`
8. `ShowBootSplash`（`yh_skin_display.cc:531-533`）的 `info.background` 优先取 boot 壁纸
9. `YhSkinDisplay` 加 `boot_wallpaper_` 指针（`SetBootWallpaper`/`ClearBootWallpaper`）
10. splash 淡出后 boot 壁纸不再显示（`DismissSplash` 已隐藏整树，无需额外处理）

### 控制台（Vue，改 WallpaperDispatch.vue + DockNav.vue）

11. `WallpaperDispatch.vue` 顶部加"待机壁纸 / 开机壁纸"切换（`wpMode` 或新 state），
    两种壁纸共用上传/下发 UI，仅 dispatch 调不同 API
12. 已选设备的预览区显示"当前待机壁纸 / 当前开机壁纸"两张缩略图

## 2.3 关键约束（从现状代码里必须守住的）

- `SetWallpaper` 在 `setup_ui_called_ == false` 时**直接拒绝**（`yh_skin_display.cc:852-857`），
  所以开机壁纸的"应用"仍要拆两步：启动时只把 NVS/PSRAM 状态准备好，`SetupUI` 后绑定显示。
- 分区表 `partitions/v2/16m.csv` 16 MB 已满，**不要**新增 flash 分区（除非复用已确认的
  `assets 8M→7M` 方案，见 `code/.workbuddy/docs/wallpaper_unify_boot_spec.md`）。boot 壁纸与
  待机壁纸一样走 NVS + 服务器 URL 拉取，天然不需要新分区。
- 服务端白名单（`ConfigServiceImpl`）与固件解析要**同一次提交**，否则会出现"服务端下发、
  固件丢弃"或"固件能收、服务端过滤"的单边生效。

## 2.4 执行清单（双壁纸，按文件）

| 层 | 文件 | 改动 |
|----|------|------|
| Java | `wallpaper/controller/WallpaperMagController.java` | 新增 boot 上传/下发端点 |
| Java | `wallpaper/service/impl/WallpaperServiceImpl.java` | `configBootWallpaper()` + `dispatchBoot()` |
| Java | `config/service/impl/ConfigServiceImpl.java` | 白名单放行 `boot_wallpaper` |
| Python | `core/services/wallpaper_service.py` + `core/api/wallpaper_handler.py` | 新增 boot 下发通道 |
| FW | `main/wallpaper/wallpaper_manager.{h,cc}` | `WallpaperRequest.kind` + 双槽状态 |
| FW | `main/application.cc` | 解析 `boot_wallpaper`（device_config 路径） |
| FW | `main/display/yh_skin/yh_skin_display.{h,cc}` | `boot_wallpaper_` + `SetBootWallpaper/ClearBootWallpaper` |
| FW | `main/display/yh_skin/yh_skin_display.cc` `ShowBootSplash` | `info.background` 优先 boot 壁纸 |
| Vue | `console-v2/src/components/WallpaperDispatch.vue` | 双壁纸 tab + 双缩略图 |
| Vue | `console-v2/src/lib/api.js` | `wallpaperApi.uploadBoot/dispatchBoot` |

## 2.5 验收

- 控制台分别上传两张图，一张下发为"开机壁纸"、一张为"待机壁纸"
- 设备重启，首屏（splash）显示开机壁纸；进待机后显示待机壁纸；两张图可不同
- 断网重启，开机壁纸仍在（NVS 恢复链路）
- 串口日志：`wallpaper: apply version=... source=config kind=boot`

---

# 第三部分：任务拆分（供多 agent 执行）

**共 5 个 agent，按依赖顺序派发：**

| Agent | 范围 | 依赖 |
|-------|------|------|
| A（字体） | 乱码方案 B：生成 splash 小字体 + 接入 `yh_skin_boot.cc` | 无 |
| B（固件壁纸） | 双壁纸固件侧：WallpaperManager 双槽 + application.cc 解析 + 显示层指针 | A 无关，可并行 |
| C（服务端） | Java + Python 双壁纸下发通道 + 白名单 | 无，可并行 |
| D（控制台） | WallpaperDispatch.vue 双 tab + api.js + DockNav 无需大改 | 无，可并行 |
| E（验证） | 串口/编译验证：编译四个 yuhe 板型，串口日志核对 `kind=boot` 与 `SetSplashFont` 重绑 | A-D 完成 |

> 警告：**五个 agent 不要同时动同一个文件**。A/B 都在动 `main/display/yh_skin/yh_skin_display.cc`
> （A 动 BuildSplash 字体、B 动 background 指针），建议 A 先做、B 后做，或 A/B 只动各自函数、
> 合并时由 E 统一 review。

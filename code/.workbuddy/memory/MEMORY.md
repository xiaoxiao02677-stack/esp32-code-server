# xiaozhi-esp32 / console-v2 项目记忆（长期 · 索引）

> 细节分库：服务端/前端/OTA/壁纸/鉴权 → `topics/server-side.md`；
> **固件崩溃排查（event_head 悬垂、字体悬垂、乱码、烧写没生效）→ `topics/firmware-crash-cookbook.md`**；
> 固件命令与引脚表 → `hardware/sets/README.md`；皮肤设计 → `hardware/sets/UI_SKIN.md`；逐日过程 → `2026-*.md`。

## 仓 / git
- 仓根 `G:/demo/21_xiaozhi`：`docs/ hardware/ yh/ third_party/ tools/ code/`；`hardware/camera/` 是**嵌套独立仓**、
  `hardware/sets/` 是多版型中心；`yh/_archive-order-module` 与现行 order **不可混用**
- **在用分支 `master`**（`test_environment` 落后）；提交前 `git branch --show-current`；
  远端 `git@gitee.com:mm-Super-Nices/esp32-code-server.git`；`baseline.json` 保持追踪，`.workbuddy`/`.trash/` 永不提交
- `.trash/` 可回滚、归档 `G:/demo/archive-20261015/`；**.gitignore 随移动同步**；嵌套仓父仓必须 ignore；
  **构建产物一律不入库**（曾误提交 1718 文件致 .git 膨胀 468M）
- **`main/display/yh_skin/` 至今未被 git 跟踪** ⇒ 不能用 `git show HEAD:` / `git diff` 判断它的历史状态（会得到假 0）

## ★ ESP-IDF 环境
- `IDF_PATH=D:\INSTALL\esp\v6.1\esp-idf`、`IDF_TOOLS_PATH=D:\INSTALL\esp`、
  `IDF_PYTHON_ENV_PATH=D:\INSTALL\esp\tools\python\v6.1\venv`、`ESP_IDF_VERSION=6.1`；权威记录 `C:\Espressif\tools\eim_idf.json`
- **`IDF_TOOLS_PATH` 不带 `\tools`**（工具在 `$IDF_TOOLS_PATH/tools/<name>/<ver>`）；
  eim 写 `...\esp\tools` 是命名偏差，照抄会让 `idf_tools.py check` 报 13 工具全缺失
- **`idf.py` 在 Git Bash 下只打印提示就提前退出、rc=0**（假绿）→ 校验必须在 CMD/PS；
  调 `idf_tools.py export` 时子进程 env `pop("MSYSTEM")`
- PATH 里的 `python` 常是 `Python310-32`（无 rich_click）；`scripts/build.py:70` 用 `sys.executable` 起 idf.py
  → **必须用 IDF venv python 启动编译**；`ESP_IDF_VERSION` 必补（`idf_extensions.py:388`），`IDF_VERSION` **绝不能代设**
- 切版型后**必须删 `<FW>/build` 全量重编**；半成品 build 偶发 `component_requires.temp.cmake` 报错，重跑即好
- `tools/yh_syntax_check.py` 参数是**相对 `hardware/sets/xiaozhi-esp32/` 的路径**（传全路径会重复拼接报「文件不存在」）；
  `.h` 单文件校验会因 `#pragma once in main file` 报假错，看包含它的 `.cc` 通过即可；改完 `tools/sets_diff_audit.py` 必须 PASS

## ★ sets 多版型中心 + 烧录
- 架构：`hardware/sets/xiaozhi-esp32/` = 自带固件副本（已入库）；`build.py` 选版型/注册/编译（**零串口**）、
  `flash.py` 探测+烧录+三道闸（**不编译**）、`diag.py` 只读比对（**不写盘**）
- **★ 背光脚不同 → 选错版型必黑屏**：`yh-154tft-wifi` 背光 **BL20**（征辰 1.54 寸，有电池）；
  `yh-n16r8-st7789` 背光 **42**、仅 BOOT 键、无电池；`yh-cam` **唯一有 AEC 回采**；`yh-big-ili9341` 引脚未验证
- **★ 三条硬约束**：① `config.json` 的 `type`/`builds[].name` 全局唯一且匹配 `^[a-z0-9.-]+$`（下划线非法）；
  ② `config.json` 的 `sdkconfig_append` 是**权威真源**，`set.json` 是增量层、正常留 `[]`；
  ③ CMakeLists board 分支 **4 行**，第 4 行 `set(DEFAULT_EMOJI_COLLECTION noto-color-emoji_64)` 别漏；
  注册块用 `# >>> SETS-BOARDS-BEGIN/END <<<` 幂等标记，改前备份 `*.bak-sets`
- **★ 布局**：`v2/16m.csv` = nvs 0x9000 / otadata 0xd000 / phy_init 0xf000 / **ota_0 0x20000** / ota_1 0x410000 /
  assets 0x800000（**无 factory**）；`v2/4m.csv` = **factory app @ 0x10000**。**assets 必须全量烧**；**baud 230400**
  （460800 写 4MB 实测断链）
- **★ 三道闸**：① 烧前 `check_layout_consistency()` 核对「写入地址 vs 分区表」同源 → 不同源**拒烧**；
  ② 烧后 `verify_written_regions()` 回读（大镜像头 4KB+尾 4KB，app 尾是整段 SHA256）；
  ③ `boot_check()` 复位读串口判循环重启（**ROM 的 `ESP-ROM:` 横幅不受 sdkconfig 影响**）
- **★ 顺序**：逐段（一镜像一会话，**按地址升序→assets 垫底**）+ 大镜像 1MB 切块 + 段前 `flash-id` 探活。
  **按 flash_args 书写顺序会把 assets 排在 app 前 → assets 断则 app 一字节没写**
- **★★ 复位线序**：参考设计 DTR→GPIO0/RTS→EN；**本项目板（COM18）反相 DTR→EN / RTS→GPIO0** → 首字节 `I`(0x49)
  被当包头 `Invalid head of packet (0x49)`；**按住 BOOT 开机也无效**；**反相板不能真跑 `idf.py flash`**
  （`--before` 编译期固化）→ 走「同一份 flash_args + 单会话 write-flash，只换复位」。
  判据：`boot:0x13/0x32(DOWNLOAD)`=反相，`boot:0x1b`=标准
- **★ 死机判据**：`bootloader_reset at bootloader_utility.c:1163` + `rst:0x3(RTC_SW_SYS_RST)` 死循环 + 屏不亮
  = **分区表与 app 不同源**（表 16MB ota_0@0x20000，app 却按 4MB 写 0x10000）；`CONFIG_BOOTLOADER_LOG_LEVEL_NONE=y`
  时一句话不打。**查 `diag.py`、处置 `flash.py --clean`**；**diag 必须查 assets**
- 每次 esptool 调用都是独立 connect→work→disconnect，`--after no-reset` 断开即退出下载模式
  → 下次调用前**必须重新进下载模式**；COM12 独占（PermissionError 13）；**别用 .bat 烧录**；探测跳过 `BTHENUM` 虚拟口
- **ESP32 魔数 `0xE9`**（头 `+0x4`=入口点）；`esp_app_desc` 用 `0xABCD5432` 定位，+16..48=version（各版型 2.5.1）

## ★ LVGL 皮肤（sets 四版型统一）
- 共享层 `main/display/yh_skin/`：`YhSkinDisplay`+`YhSkinProfile`(Round240(bat)/Wide320x240/Tall240x320)，
  坐标全 `profile.scaled(240基准)`；基准=A 板 `my-s3-tft/round_screen_display.*`
- **开机首帧**：`SetupUI` 只调 `Display::SetupUI()`（跳过原生布局）→ 建主界面 → 盖不透明品牌画面，
  进待机（顶部出 `HH:MM`）才淡出；**必须丢弃** `SetChatMessage("system",GetUserAgent())` 与「待机/初始化/连接中」噪声。
  **只有真实对话内容才允许收 splash**（UA 串是 `BOARD_NAME/version`，如 `yh-154tft-wifi/2.5.1`，**不是空格分隔**）
- **基类占位族必修**（`container_/content_/network|mute|battery|status|notification_label_/low_battery_*/chat_message_label_`
  全建 1×1 隐藏），否则 `SetTheme` null 崩；**锁顺序** `LcdDisplay::SetTheme()`→`DisplayLockGuard`→`ApplyFonts()`；
  持锁禁调 `SetEmotion/SetTheme`；`SetupUI()` 里先拿锁再置 `setup_ui_called_`（否则留"标志已置、界面没建"的半状态）
- 内置字体无 ⚡（用「充电85%」）；圆屏底部提示 18；无电池板隐藏电量；背景用 `lv_image`+`lv_image_set_scale`
  （`bg_image_src` 不能缩放），符号 `yh_skin_bg` 由 `tools/gen_yh_skin_assets.py` 生成、四版型共用
- **改共享层必须同步两份**：`hardware/sets/boards/<board>/` 是源副本，`build.py` 会用它覆盖
  `hardware/sets/xiaozhi-esp32/main/boards/yuhe/<board>/`；只改固件树下次编译会被冲掉
- **字体不是"设一次就完"**：`LvglBuiltInFont` 按值持 `lv_font_t`、样式只存裸指针 ⇒ 换字体时必须
  ①旧对象进退休池 ②全树改绑。详见 `topics/firmware-crash-cookbook.md` 现场 ②

## ★ 壁纸链路（SET_WALLPAPER）
- **`wallpaper: skip version=X (already applied)` = 幂等命中，不是没收到**；先看这一行再谈渲染
- `version` 是内容寻址的：`manager-api.wallpaperVersion()` = `"3-" + md5(转码后 RGB565 bin)`
  ⇒ **同 version 必是同一张图**，「下发没更新」第一嫌疑人永远是"服务端推的是不是旧图"
- 固件曾把 `applied_version/dsc_valid` 登记在 `SetWallpaper()` **之前**且该方法返回 `void`
  ⇒ 静默失败被记成成功、之后永久跳过。现为 `bool`（判据 `lv_image_get_src() == image`），
  显式命令命中幂等时 `RebindCurrent()` 重绑重绘，失败回 `render_failed` 而非假 ok
- 服务端 `dispatch()` 曾不清 `sent/offline` 的补投队列 → 旧版本被 30s 巡检重投、把新图顶回旧图
- 细节与不可达分支说明见 `2026-10-17.md` 的「18:1x 壁纸链路排查」

## ★ 崩溃排查（速查，全文见 `topics/firmware-crash-cookbook.md`）
- **先校验 elf 同源**：日志 `ELF file SHA256` 前 9 位 == `sha256sum build/xiaozhi.elf`；不一致时 addr2line 解出的符号是跨模块幻觉
- `EXCVADDR=0x14` + `lv_event_mark_deleted(lv_event.c:323)` → `event_head` 并发悬垂/自环（现场 ①）
- `PC=0x0` / `EXCVADDR=0x0` + `InstrFetchProhibited` + 紧跟 `Refreshing display theme...` → **字体对象已释放**
  （`get_glyph_dsc` 在 `lv_font_t` 偏移 0，free 后成 NULL）；寄存器里能看到正在渲染的 Unicode 码点（现场 ②）
- 「有些字乱码有些正常」→ ① 图标字体渲染中文 ② basic(890) vs common(5258) 档位 + splash 建早于 assets（乱码章）
- 「改了代码现象没变」→ **先看开机版本戳** `I (xxx) YhSkin: yh_skin build <date> <time>`，看不到就是没烧进去
- 拦不住的自旋/野跳在 `hardware/sets/patches/` 有兜底补丁（`lv-event-loop-guard`、`lv-font-null-glyph-guard`），
  每个补丁配同名 README；`managed_components/` 在 `.gitignore` 里，改动不出现在 `git status`
- 插桩红线：坏指针必须 `return`/`break` 拦住，只打日志会立刻在原处崩；**开探针后不崩 ≠ 修好了**

## ★ 子代理 / 多开
- **`session.teamCancelled` 置 true 后本会话 team 子系统整体砖化**：spawn 进 cancel barrier →
  `spawned after team cancel and was paused` / `was killed immediately`；`resume` 报
  `Cannot resume "X" while lead cancel is settling`。**不清会话不自愈**
- 置 true 唯一路径：任一 cancel（用户点停止 / ACP cancel / ECONNRESET 触发的 `error=aborted`）；
  唯一清除路径是 `team_resume_intent` 拦截器。判据：1–3ms 内 `running -> killed`
- **默认名会复用死任务**：不给 `name` 时默认 `general-purpose-1`，同名成员已 kill → 工具仍返回
  `Spawned successfully` 但 task_id 与上次**完全相同**、无新日志。**批量 spawn 必须显式取唯一 name**；
  风险是**单轮 spawn 太多**致响应膨胀（曾 7 并行 → 12669 chunks / 3.9MB）→ 每批 6–8 个

## ★ 生产环境发布（sandyun.top:22222，与测试 22223 分开记）
- Java `/opt/xiaozhi/xiaozhi-esp32-api.jar`（systemd `xiaozhi-manager-api`，8002）+ 外部 `application-dev.yml`（保留）
- Python `/root/xiaozhi-server/main/xiaozhi-server`，**systemd `xiaozhi-server`**（不是 setsid！），8000 WS / 8003 http / 12399 心跳
- 前端 `/var/www/console-v2/admin`（`/admin/` 与 `/admincc/` **同一 alias**）+ `app`（`/`）
- **顺序必须 Java → Python → Web**：`config_loader.py:73` 拉不到 Java 配置直接 raise
- **Python 三文件必须同批**：`core/services/wake_word_service.py`、`core/api/wake_word_handler.py`、
  **`core/http_server.py`（不在 core/api/）**；只换一个 → `Restart=always` 每 5s 崩（旧坑复发）
- **发布后验 inode 不验时间戳**：`stat -c %i jar` == `/proc/<pid>/fd` 里该 jar 的 inode
- **前端缺资源返 200+HTML**（try_files 回落）⇒ 逐个体 md5 校验；**只增不删旧 assets**
- **MySQL datetime 存 UTC**，比日志早 8h，禁止用 update_date 判写入
- 发布不批量改写 `device_config`（阈值/display 全 0 行是**预期**）；下行词 = agent 词 ∪ sys_params 全局 10 词

## ★★ Git Bash(MSYS) 改写以 / 开头的参数
`sftp_push.py x.py /root/a.py` → python 收到 `D:/INSTALL/.../PortableGit/root/a.py` → SFTP 报 ENOENT
（伪"路径不存在"）。解法：`MSYS_NO_PATHCONV=1` 或 `MSYS2_ARG_CONV_EXCL='*'`，或脚本内剥前缀。
**所有 `code/.workbuddy/*.py` 的远端路径参数都受此影响。**

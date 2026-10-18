# yuhe（原 xiaozhi-esp32）/ console-v2 项目记忆（长期 · 索引）

> **2026-10-18 全仓改名 xiaozhi→yuhe（a146e080）**：目录 `yh/yuhe-server`、`hardware/sets/yuhe-esp32`、Java 包 `yuhe`；
> WS `/yuhe/v1/`、OTA `/yuhe/ota/`、context-path `/yuhe`、产物 `yuhe.bin`。豁免：`78/xiaozhi-fonts`、
> 上游 GitHub URL、库名 `xiaozhi_esp32_server`、`/root/xiaozhi-server`、`/opt/xiaozhi`、`21_xiaozhi` 仓根。
> 旧路径双兼容（Java RewriteValve + Python 旧 OTA 路由）。生产迁移清单见 `2026-10-18.md` 22:0x 节。
> 细节分库：服务端/OTA/壁纸/鉴权 → `topics/server-side.md`；固件崩溃 → `topics/firmware-crash-cookbook.md`；
> 引脚表 → `hardware/sets/README.md`；皮肤 → `UI_SKIN.md`；逐日过程 → `2026-*.md`。

## 仓 / git
- 仓根 `G:/demo/21_xiaozhi`：`docs/ hardware/ yh/ third_party/ tools/ code/`；`hardware/camera/` 嵌套独立仓；
  在用分支 `master`；`.workbuddy`/`.trash/` 永不提交；**构建产物一律不入库**（曾致 .git 膨胀 468M）
- `main/display/yh_skin/` 未被 git 跟踪 ⇒ 不能用 `git show/diff` 判断其历史状态
- 固件树改名/切版型后必须删 `build/` 全量重编（compile_commands.json 固化旧绝对路径）

## ★ ESP-IDF 环境
- `IDF_PATH=D:\INSTALL\esp\v6.1\esp-idf`、`IDF_TOOLS_PATH=D:\INSTALL\esp`（**不带 \tools**）、
  `IDF_PYTHON_ENV_PATH=D:\INSTALL\esp\tools\python\v6.1\venv`；权威记录 `C:\Espressif\tools\eim_idf.json`
- `idf.py` 在 Git Bash 下假绿（rc=0 提前退出）→ 校验必须 CMD/PS；PATH 裸 `python` 缺 rich_click
  → **必须用 IDF venv python 启动编译**；`ESP_IDF_VERSION` 必补，`IDF_VERSION` 绝不能代设
- `tools/yh_syntax_check.py` 参数是相对 `hardware/sets/yuhe-esp32/` 的路径；`.h` 单文件假错看 `.cc`；
  改完 `tools/sets_diff_audit.py` 必须 PASS（3 项存量 DIFF 是 B 侧领先功能，非回归）

## ★ sets 多版型中心 + 烧录
- `build.py` 选版型/编译（零串口，支持 `--server prod|test` 选目标环境）、`flash.py` 烧录+三道闸、`diag.py` 只读比对
- **背光脚**：`yh-154tft-wifi`=BL20（有电池）；`yh-n16r8-st7789`=42（仅 BOOT 键无电池）；`yh-cam` 唯一有 AEC；`yh-big-ili9341` 未验证
- **三条硬约束**：① config.json `type`/`builds[].name` 全局唯一匹配 `^[a-z0-9.-]+$`；② `sdkconfig_append` 是权威真源；
  ③ CMakeLists board 分支 4 行含 `DEFAULT_EMOJI_COLLECTION`
- **布局**：`v2/16m.csv` = nvs 0x9000/otadata 0xd000/phy 0xf000/**ota_0 0x20000**/ota_1 0x410000/assets 0x800000（无 factory）；
  `v2/4m.csv` = factory app@0x10000。assets 必须全量烧；**baud 230400**（460800 断链）
- **三道闸**：烧前 layout 一致性（不同源拒烧）→ 烧后回读校验 → 复位读串口判循环重启
- **顺序**：一镜像一会话按地址升序、assets 垫底；大镜像 1MB 切块；段前 flash-id 探活
- **★★ 复位反相（COM18）**：DTR→EN/RTS→GPIO0 反相 → `Invalid head of packet (0x49)`；按住 BOOT 也无效；
  判据 `boot:0x13/0x32`=反相、`0x1b`=标准；反相板走「同一份 flash_args + 单会话 write-flash 只换复位」
- **死机判据**：`bootloader_reset` + `rst:0x3` 死循环 = 分区表与 app 不同源 → `diag.py` + `flash.py --clean`
- esptool 每次调用独立连接，`--after no-reset` 后须重新进下载模式；COM12 独占；别用 .bat 烧录

## ★ LVGL 皮肤
- 共享层 `main/display/yh_skin/`：`YhSkinDisplay`+`YhSkinProfile`（Round240/Wide320x240/Tall240x320）；
  **改共享层必须同步 `hardware/sets/boards/<board>/` 源副本**（build.py 会覆盖固件树副本）
- 开机首帧：SetupUI 建主界面 → 盖品牌 splash → 待机出 HH:MM 才淡出；须丢弃 UA 噪声
  （UA 串是 `BOARD_NAME/version` 无空格）；只有真实对话内容才允许收 splash
- 基类占位族必修（否则 SetTheme null 崩）；锁序 `LcdDisplay::SetTheme()`→DisplayLockGuard→ApplyFonts；
  持锁禁调 SetEmotion/SetTheme
- 背景用 `lv_image`+`lv_image_set_scale`；内置字体无 ⚡；**换字体必须旧对象进退休池+全树改绑**

## ★ 壁纸链路（SET_WALLPAPER）
- `skip version=X (already applied)` = 幂等命中不是没收到；version 内容寻址（`"3-"+md5(RGB565 bin)`），
  同 version 必是同一张图，「下发没更新」先查服务端推的是不是旧图
- SetWallpaper 返回 bool（判据 `lv_image_get_src()==image`）；幂等命中时 RebindCurrent 重绑重绘，失败回 render_failed
- 服务端 dispatch() 必须清 sent/offline 补投队列（否则旧版本被 30s 巡检重投顶回旧图）
- **双壁纸（本次）**：`WallpaperKind{Idle,Boot}`、slots[2]、boot 槽独立 NVS `wallpaper_boot`、
  Display 新增 SetBootWallpaper/ClearBootWallpaper/GetBootWallpaper

## ★ 语音链路（详见 2026-10-17/18.md）
- "服务端 AEC"是虚设（无 AEC 实现，conn.client_aec 只是打断判定位置开关）；设备 abort 日志
  `Send abort speaking (reason=...)`，无此行+服务端 Abort = 服务端触发
- 打断三道防线：起播保护窗 800ms → 人声确认窗 → 回声探测（grep `打断探测`）
- echo_guard v3：字符层+拼音层+跨句拼接拼音子串（真人说不出句1尾+句2头连续串）
- fun_local ASR 返回 dict 必须取 content；本地 pytest 需 `data/.config.yaml` 占位

## ★ 崩溃排查（全文见 firmware-crash-cookbook.md）
- **先校验 elf 同源**（日志 SHA256 前 9 位 == sha256sum build/yuhe.elf）；`EXCVADDR=0x14`+lv_event_mark_deleted
  = event_head 悬垂；`PC=0x0`+紧跟 Refreshing theme = 字体对象已释放
- 「有些字乱码」→ 图标字体渲染中文 / basic(890) vs common(5258) 档位；「改了没变」→ 先看开机版本戳
- 兜底补丁在 `hardware/sets/patches/`；插桩红线：坏指针必须 return/break 拦住

## ★ 子代理 / 多开
- **`session.teamCancelled` 置 true 后本会话 team 砖化，不清会话不自愈**（唯一清除路径 team_resume_intent）
- **默认名复用死任务**：批量 spawn 必须显式唯一 name；单轮 spawn ≤6–8 个防响应膨胀

## ★ 生产环境（sandyun.top:22222；测试 22223）
- Java `/opt/xiaozhi/xiaozhi-esp32-api.jar`（systemd `xiaozhi-manager-api`，8002）+外部 yml；
  Python `/root/xiaozhi-server/main/xiaozhi-server`（systemd，8000 WS/8003 http/12399 心跳）；
  前端 `/var/www/console-v2/admin`（`/admin/`与`/admincc/` 同 alias）
- **顺序 Java → Python → Web**（config_loader.py 拉不到 Java 配置直接 raise）；
  **Python 三文件同批**（wake_word_service.py / wake_word_handler.py / http_server.py）
- 发布后验 inode 不验时间戳；前端缺资源返 200+HTML ⇒ 逐体 md5；MySQL datetime 存 UTC 早 8h
- **测试环境设备侧**：OTA/WS 走 **8144**（明文 nginx），8101 TLS 明文连不上是坏配置；
  YH 心跳 TCP **8199**；OTA 须带 `Device-Id` 头（冒号 MAC）+ board 对象 + version Integer

## ★★ Git Bash(MSYS) 改写 / 开头参数
`sftp_push.py /root/a.py` → 收到 `D:/.../PortableGit/root/a.py`。解法 `MSYS_NO_PATHCONV=1`。
**所有 `code/.workbuddy/*.py` 远端路径参数受此影响。**

## ★ 推送调度（/admin/push-scheduler）
- 入参 `device_ids` 顶层列表 + `content.topic_sources`；任务查 `GET /api/push/tasks/{id}`
- **空闲设备 UUID→MAC 断链**：反查链末级接 `wake_word_service._agent_devices`（设备断 WS 后仍保留）
- 话题源全失败降级 chat 兜底；TTS 转 Ogg Opus mono；URL 兜底链 public_audio_base_url → vision → ws host:8003

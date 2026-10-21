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
- **「主人，小智现在有点忙」排查顺序**（2026-10-19 详录）：先 grep `LLM stream processing error`
  → tuple 崩溃 = Intent_nointent agent + 设备 MCP 工具时生产/消费条件不对称（已修 703eec33）；
  兜底话术≠部署回归，先比对崩溃/正常会话的 `selected_module.Intent`。E2E 冒烟基建
  `_e2e_venv`+`_e2e_tuple_fix.py`（复刻设备 ID+MCP 协商+listen 三连）

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
- **★★ 生产前端有两个目录必须同批更新**（2026-10-21 踩坑）：`/var/www/console-v2/app/`
  （nginx `location = /` + `/assets/`，客户端构建 base=/）和 `/var/www/console-v2/admin/`
  （`/admincc/`+`/admin/`，管理构建 base=/admincc/）。用户从 8001 根路径 `/#/admin/xxx`
  进管理页走的是 **app 目录**（客户端 bundle 自带全套管理路由）——只更 admin 会出现
  "同步了但用户看不到新功能"。nginx 配置真源：`/etc/nginx/snippets/xiaozhi-common.conf`
  （被 9001/9443/8443 server 共同 include）。测试环境 8144 根路径即 admin dist 无此问题
- **顺序 Java → Python → Web**（config_loader.py 拉不到 Java 配置直接 raise）；
  **Python 三文件同批**（wake_word_service.py / wake_word_handler.py / http_server.py）
- 发布后验 inode 不验时间戳；前端缺资源返 200+HTML ⇒ 逐体 md5；MySQL datetime 存 UTC 早 8h
- **测试环境设备侧**：OTA/WS 走 **8144**（明文 nginx），8101 TLS 明文连不上是坏配置；
  YH 心跳 TCP **8199**；OTA 须带 `Device-Id` 头（冒号 MAC）+ board 对象 + version Integer

## ★ 测试环境（22223）已部署改名版（2026-10-19 详录 2026-10-19.md）
- 全部切 /yuhe/：Java jar `yuhe-esp32-api.jar`（RewriteValve 旧 /xiaozhi/ 兼容）、
  Python 全量 222 文件、前端 dist、nginx /yuhe/ 路由；sys_params 三项已修（8144 新路径）
- **RewriteValve 必须 Engine 级**（addEngineValves）：Context 级在 /xiaozhi/* 映射不到 /yuhe 永不触发；
  setConfiguration 必须延迟到子类 startInternal（customizer 阶段 container 未挂载 NPE）
- **Liquibase 红线**：改名提交误改 7 个已执行 changeset → 校验和漂移启动失败；已还原 faaafaaf 版
- **壁纸 URL 幂等陷阱**：队列去重只比 version 不比 URL；改壁纸 URL 须清 Redis 队列键+重启 Python（内存队列同旧）
- 壁纸下载 URL 由 `sys_params.server.ota` 推导（buildDownloadUrl 把 /ota/ 换成下载路径），非 fronted_url
- 测试登录程序化：uuid→captcha→Redis 读值(JSON parse)→sm2 加密→`Authorization: Bearer`；token 直接 UPDATE sys_user_token

## ★★ Git Bash(MSYS) 改写 / 开头参数
`sftp_push.py /root/a.py` → 收到 `D:/.../PortableGit/root/a.py`。解法 `MSYS_NO_PATHCONV=1`。
**所有 `code/.workbuddy/*.py` 远端路径参数受此影响。**

## ★ 推送调度（/admin/push-scheduler）
- 入参 `device_ids` 顶层列表 + `content.topic_sources`；任务查 `GET /api/push/tasks/{id}`
- **空闲设备 UUID→MAC 断链**：反查链末级接 `wake_word_service._agent_devices`（设备断 WS 后仍保留）
- 话题源全失败降级 chat 兜底；TTS 转 Ogg Opus mono；URL 兜底链 public_audio_base_url → vision → ws host:8003

## ★★ 配置真源：manager-api 模式下 config.yaml 大部分键无效
`data/.config.yaml` 配了 `manager-api.url` → 运行时配置整包从 Java `/config/server-base` 拉
（sys_params 整表 + Redis `server:config` 缓存 + Python 进程缓存）。
**话术/唤醒词等系统参数改 sys_params 表**，改完三连：`UPDATE` → `redis-cli DEL server:config`
→ `systemctl restart xiaozhi-server`。本地 config.yaml 只补 redis/TTS/prompt_template 兜底键。
鉴权头 `Authorization: Bearer <secret>`；服务 venv 是 `.venv/bin/python`（系统 python3 缺 httpx）。
**时序红线**：必须先 UPDATE 后清缓存重启；顺序颠倒 Java 会把旧值重建进 Redis 需重来一轮。
sed 删中文行在远端不可靠（编码），用远端 python3 按行过滤。
生产 Python 根 `/root/xiaozhi-server/main/xiaozhi-server/`；订单日报邮件
`/root/xiaozhi-server/tools/order_report_mailer.py`（root cron 00:00，报昨天）。

## ★ 前端 API 契约陷阱（cc-console 迁移遗留）
- **`POST /device/bind/{agentId}` 是 MQTT 在线状态转发（返回 String，网关未配置返回空串）**；
  已绑设备列表真契约是 **`GET /device/bind/{agentId}`**（List<UserShowDeviceListVO>）。
  adminApi.boundDevices 曾误用 POST，2026-10-21 已改 GET（连带 Agents 编辑弹窗/清单展开/Devices 降级路径）
- `/agent/list` 设备计数字段名是 **`deviceCount`**（非 boundCount）
- OtaEntity 自带 remark，/otaMag 列表直接返回实体；PUT /otaMag/{id} 需带 type/version（唯一性校验）
- UserShowDeviceListVO 已含 agentId/agentName/targetOtaId/otaType（2026-10-21 补，修"智能体列全 demo"）

# xiaozhi-esp32 / console-v2 项目记忆（长期 · 索引）

> 细节见 `hardware/sets/README.md` 与 `code/.workbuddy/memory/2026-*.md`；这里只留结论与坑。

## 拓扑（同机双 VM）
- **生产** `ssh -p 22222 root@sandyun.top`(.10)：Java `/opt/xiaozhi/xiaozhi-esp32-api.jar`（systemd `xiaozhi-manager-api`，JDK21，日志 `/opt/xiaozhi/logs/`，配置 `/opt/xiaozhi/application-dev.yml`）；Python `/root/xiaozhi-server/main/xiaozhi-server/`（systemd `xiaozhi-server`）；MySQL root/123456 `xiaozhi_esp32_server`；Redis 127.0.0.1:6379 无密码；nginx 9001 / 8443+9443 TLS / public 8001（分流 9002/9444）/ 8002→Java；前端 `/var/www/console-v2/`、`/var/www/cc-console/`
- **测试** `ssh -p 22223`(.20)：根 `/root/yh/`，Java 源码 `app/manager-api/`、jar `deploy/opt-xiaozhi/`，Python `app/xiaozhi-server/`，nginx 8101/8144
- 一个崩另一个报连不上 8002/8003 → 先查根因再重启

## 仓 / git
- 仓根 `G:/demo/21_xiaozhi`：`docs/ hardware/ yh/ third_party/ tools/ code/`（reports + `.workbuddy`）；`hardware/` 里 `camera/` 是**嵌套独立 git 仓**、`sets/` 是多版型中心；`yh/` 里 `_archive-order-module` 与现行 order **不可混用**
- `.trash/` 可回滚、归档 `G:/demo/archive-20261015/`；**.gitignore 随移动同步**；嵌套仓父仓必须 ignore；**构建产物一律不入库**（曾误提交 1718 文件使 .git 膨胀 468M）
- **★ 在用分支 `master`**（`test_environment` 落后）；提交前 `git branch --show-current`；远端 `git@gitee.com:mm-Super-Nices/esp32-code-server.git`；`baseline.json` 保持追踪，`.workbuddy`/`.trash/` 永不提交

## 前端 / 服务端
- console-v2：`npm run build`→`dist`(base=/)；`npx vite build --mode admin`→`dist-admin`(base=/admincc/)。两产物 bundle 同名**仅 index.html 前缀不同** → admin 入口必须部署 dist-admin 的 index.html，否则 /assets 落 app 目录 404 白屏。nginx `/assets/` 固定 root→`console-v2/app`；cc-console `API_BASE='/xiaozhi'`
- 登录分流 `api.js`：`userState` + `refreshUserInfo()` + `defaultRouteAfterLogin()`(demo→/customer；hasAdminRole→/admin)。生产旧 jar 的 TokenDTO 无 roles → 以 `superAdmin===1` 为主判据；TopBar/DockNav 必须订阅 `userState`，勿裸读 localStorage
- 订单 `/xiaozhi/order`：/page /{id} POST PUT DELETE(软删) /export /stats；VO **下划线命名**。**导出契约两环境不同**：本地 `POST /export` 返 CSV，生产旧 jar `GET /export` 返 JSON → 前端双兼容
- Java 构建：`/d/INSTALL/maven/bin/mvnd.cmd -o -Dmaven.test.skip=true package`（**无 `mvn`**），产物 `target/xiaozhi-esp32-api.jar`；部署前核对 jar 内 Controller 数（当前 37）。Python aiohttp `client_max_size` 默认 1MB → 大 payload 接口须调大（已 8MB）
- 唤醒词 `WakeWordService` 注册于 `connection.py` hello/device_register（断开双注销）；格式 `{"type":"device_config","payload":{"wake_word":[...]}}`（固件只认此 type）；**在线设备靠 push 生效，改 DB 不生效**；Push Scheduler 话题源 `POST /api/push/schedule`
- **SSH 写文件**：禁止把命令回显/标记混进内容（曾 `[rc=0]` 混入 YAML 致 Liquibase 崩）；用 heredoc 隔离，写完 tail + 语法校验再重启

## ★ Python 配置装配（血泪）
- 生产 `data/.config.yaml` 有 `manager-api.url` → **整份配置由 Java API 下发**，本地 `config.yaml` 只按**白名单**回填 `server`(ip/port/http_port/vision_explain/auth_key/heartbeat_port/ws_udp_heartbeat_port)、`prompt_template`、`TTS`
- **★ 新增 server 键必须补白名单；新增顶层基础设施键（如 `redis`）必须在 `load_config()` 显式透传**，否则 `config.get("redis")` 恒为 None：壁纸回执悄悄丢失、队列静默退化纯内存，日志仅一句 WARNING 极易漏看
- 排查：`cd <prod>/xiaozhi-server && .venv/bin/python -c "import asyncio;from config.settings import load_config;print(asyncio.run(load_config()).get('redis'))"`（**`load_config` 是 async**）

## ★ 壁纸全链路
- 表：`ai_wallpaper` / `ai_wallpaper_task`（status/total/sent/success/failed，**非 success_count**）/ `ai_wallpaper_task_device`（error/ack_time，**非 err_msg**）；`create_date` 存 **UTC**（差 8h）
- 链路：Java `WallpaperServiceImpl.dispatch` → 写 `device_config`（下次启动保底）+ `WallpaperDispatchClient` → Python `127.0.0.1:8003/api/wallpaper/dispatch`，返回 `{sent,queued,offline}`
- **`targetType` 必须 `devices`（复数）**；DTO 字段是 **`deviceIds`**（不是 targetIds）。`10003 获取参数失败` 多义（参数缺失/设备不存在/目标空）
- **`version` 必须内容寻址 `3-<md5>`**（写死 `"3"` 会让固件按 version 幂等，第二张图永不生效）
- **★ 三级投递**（设备空闲不保持 WS，WS 8000 按次会话、心跳 TCP 12399 常连）：① WS 直投 → ② 心跳 `COMMAND/SET_WALLPAPER`（**需固件 ADVERTISEMENT 声明该 operation**，老固件 `operations=[]` 走不通）→ ③ 待补投队列 `wallpaper:pending:<归一化MAC>`（Redis，TTL 7 天，**last-write-wins 每设备只留最新一条**）
- 补投三触发：WS hello 注册 / 心跳上线或能力变更（`heartbeat_server.on_device_online`）/ 30s 巡检 `start_sweeper`（启动 `hydrate()` 从 Redis 恢复）
- 回执：固件回 `{"type":"wallpaper","action":"result"}` → `save_ack` 写 `wallpaper:ack:<device_id>`（TTL 7 天）→ Java `buildDetail` **只在查详情时读 Redis 合并**（DB 不落 applied）→ 回执 Redis 不通等于任务永远 pending
- 运维：`GET /api/wallpaper/queue`（Bearer = `sys_params.server.secret`，`?flush=1` 强制补投）
- 壁纸模块用 stdlib `logging`、项目用 loguru → 必须 `install_stdlib_log_bridge(__name__)`，否则 INFO 全丢

## ★ ESP-IDF 环境
- `IDF_PATH=D:\INSTALL\esp\v6.1\esp-idf`、`IDF_TOOLS_PATH=D:\INSTALL\esp`、`IDF_PYTHON_ENV_PATH=D:\INSTALL\esp\tools\python\v6.1\venv`、`ESP_IDF_VERSION=6.1`；权威记录 `C:\Espressif\tools\eim_idf.json`
- **`IDF_TOOLS_PATH` 不带 `\tools`**（工具在 `$IDF_TOOLS_PATH/tools/<name>/<ver>`）；eim 写 `...\esp\tools` 是命名偏差，照抄会让 `idf_tools.py check` 报 13 工具全缺失
- **`idf.py` 在 Git Bash 下只打印提示就提前退出、rc=0**（假绿）→ 校验必须在 CMD/PowerShell；调 `idf_tools.py export` 时子进程 env `pop("MSYSTEM")`
- PATH 里的 `python` 常是 `Python310-32`（无 rich_click）；`scripts/build.py:70` 用 `sys.executable` 起 idf.py → 解释器接力失败。**必须用 IDF venv python 启动编译**；`ESP_IDF_VERSION` 必补（`idf_extensions.py:388`），`IDF_VERSION` **绝不能代设**
- 切版型后**必须删 `<FW>/build` 全量重编**；半成品 build 偶发 `component_requires.temp.cmake` 报错，重跑即好

## ★ sets 多版型中心 + 烧录（**命令/参数/引脚表全在 `hardware/sets/README.md`**，这里只留判据）
- 架构：`hardware/sets/xiaozhi-esp32/` = 自带固件副本（已入库）；`build.py` 选版型/注册/编译（**零串口**）、`flash.py` 探测+烧录+三道闸（**不编译**）、`diag.py` 只读比对（**不写盘**）
- **★ 背光脚不同 → 选错版型必黑屏**：`yh-154tft-wifi` 背光 **BL20**（征辰 1.54 寸，有电池）；`yh-n16r8-st7789` 背光 **42**、仅 BOOT 键、无电池；`yh-cam` **唯一有 AEC 回采**；`yh-big-ili9341` 引脚未验证
- **★ 三条硬约束**：① `config.json` 的 `type`/`builds[].name` 全局唯一且匹配 `^[a-z0-9.-]+$`（下划线非法，撞车终止编译）；② `config.json` 的 `sdkconfig_append` 是**权威真源**，`set.json` 是增量层、正常留 `[]`；③ CMakeLists board 分支 **4 行**，第 4 行 `set(DEFAULT_EMOJI_COLLECTION noto-color-emoji_64)` 别漏；注册块用 `# >>> SETS-BOARDS-BEGIN/END <<<` 幂等标记，改前备份 `*.bak-sets`
- **★ 布局**：`v2/16m.csv` = nvs 0x9000 / otadata 0xd000 / phy_init 0xf000 / **ota_0 0x20000** / ota_1 0x410000 / assets 0x800000（**无 factory**）；`v2/4m.csv` = **factory app @ 0x10000**。**assets 必须全量烧**；**baud 230400**（460800 写 4MB 实测断链）
- **★ 三道闸**：① 烧前 `check_layout_consistency()` 核对「写入地址 vs 正在写入的分区表」同源（除 `0x0`/`0x8000`）→ 不同源**拒烧**；② 烧后 `verify_written_regions()` 回读（大镜像**头 4KB+尾 4KB**，app 尾是整段 SHA256，抓「写一半断链」）；③ `boot_check()` 复位读串口判循环重启（**ROM 的 `ESP-ROM:` 横幅不受 sdkconfig 影响**）
- **★ 顺序**：逐段（一镜像一会话，**按地址升序→assets 垫底**）+ 大镜像 1MB 切块 + 段前 `flash-id` 探活 + 换复位线序。**按 flash_args 书写顺序会把 assets 排在 app 前 → assets 断则 app 一字节没写，表现「烧了没生效」**
- **★★ 复位线序**：参考设计 DTR→GPIO0/RTS→EN；**本项目板（COM18）反相 DTR→EN / RTS→GPIO0** → 首字节 `I`(0x49) 被当包头 → `Invalid head of packet (0x49)`；**按住 BOOT 开机也无效**；**反相板不能真跑 `idf.py flash`**（`--before` 编译期固化）→ 走「同一份 flash_args + 单会话 write-flash，只换复位」。判据：`boot:0x13/0x32(DOWNLOAD)`=反相，`boot:0x1b`=标准
- **★ 死机判据**：`bootloader_reset at bootloader_utility.c:1163` + `rst:0x3(RTC_SW_SYS_RST)` 死循环 + 屏不亮 = **分区表与 app 不同源**（表 16MB 布局 ota_0@0x20000，app 却按 4MB 布局写 0x10000）；`CONFIG_BOOTLOADER_LOG_LEVEL_NONE=y` 时一句话不打。**查 `diag.py`、处置 `flash.py --clean`**；**diag 必须查 assets**（两次翻车都在这，实测「写到 0xBADF58(~95%) 后 192KB 全 0xFF，设备仍能启动」）
- 每次 esptool 调用都是独立 connect→work→disconnect，`--after no-reset` 断开即退出下载模式 → 下次调用前**必须重新进下载模式**；COM12 独占（PermissionError 13）；**别用 .bat 烧录**；探测不复位设备、跳过 `BTHENUM` 虚拟口
- **ESP32 魔数 `0xE9`**（头 `+0x4`=入口点）；`esp_app_desc` 用 `0xABCD5432` 定位，+16..48=version（各版型 2.5.1）

## OTA / 固件包
- `POST /otaMag/upload`（multipart，只收 .bin/.apk，存 `<Java user.dir>/uploadfile/<md5>.bin`）→ `POST /otaMag`（**同 type 幂等 upsert**）
- 门控 `buildFirmwareInfo`：`ai_device` 有行 **且** `auto_update=1` **且** `ai_ota.version > 设备上报` **且** `board.type == ai_ota.type`；URL=`server.ota.replace("/ota/","/otaMag/download/")+uuid`（Redis 一次性限 3 次）
- **★ `ai_ota.version` 必须等于 bin 内嵌 `esp_app_desc.version`**，否则无限升级循环。发布 `ota_publish.py --board <id>|--all`；鉴权 `--token`（复用 `sys_user_token`）或 `--user/--password`（需 gmssl）
- `POST /ota/` 响应**扁平**：`{server_time, firmware{version,url}, websocket{url,token}, activation?}`。**尾斜杠坑**：`ota.cc:254` 拼 `/xiaozhi/ota//config/version`，Java 用 `OtaSlashNormalizeFilter` 归一；该接口必须返回 `version` **字符串**（`ota.cc:276` 校类型）

## 字形 / 心跳 / 音频 / TTS
- glyph_push：bundle `<prod>/xiaozhi-server/data/glyph_bundle/`（noto-v1-full，basic 890/common 6845）；`glyph_provider.py`+`glyph_push.py` 挂 `sendAudioHandle.py`。契约：hello 的 `features.glyph_push===true` + `text_font{bundle,charset,size,bpp}` 须与清单完全相等；硬限 64 字/64KiB。四版型内置 `font_noto_sans_basic_20_4` 且 assets 无 common → 设备报 charset=basic → **所有汉字都推送**（单句 ~3KB）
- 心跳：固件 `websocket_protocol.cc:371` 写死 UDP 8002；`core/heartbeat.py` 回 `{"type":"udp_heartbeat_ack"}`；开关 `XIAOZHI_WS_UDP_HEARTBEAT_PORT` > `server.ws_udp_heartbeat_port` > 8002
- **★ 固件 NotifyPlayer 只支持 Ogg Opus 单声道**（MP3 URL 报 "Ogg stream ended before a complete audio stream"）→ 推送音频必须 `.ogg mono`（ffmpeg `-ac 1 -ar 24000 -c:a libopus -b:a 32k`）；`sent=1` ≠ 播放成功
- TTS：`S_` 前缀=私有复刻音色（授权随额度失效，403 code=45000030）→ **禁止入 DB**；推荐 TTS_DoubaoV3_V01，其 resource_id 走 **X-Api-Resource-Id header**；真实配置在 MySQL `ai_model_config`(config_json)

## 鉴权 / 工具坑
- 登录：`GET /user/pub-config` 取 sm2PublicKey → `GET /user/captcha?uuid=` → Redis `sys:captcha:<uuid>` → 密码 `'04'+sm2.doEncrypt(captcha+password, pk, 1)`（**验证码拼在密文里**）→ `POST /user/login`。省事：复用 `sys_user_token` + `Authorization: Bearer <token>`
- `sys_params.id` 是 **BIGINT 雪花**（非 UUID）；缓存 key 是 paramCode 本身（`DEL sys:params` 无效）
- AOCI：`D:/INSTALL/aoci/aoci.exe` 靠 `.git` 定位 → **必须 `--repo <绝对路径>`**；**`scan --force` 已锁**、**`scope apply/plan/preview` 有缺陷 → 严禁使用**；reconcile 只比 **raw sha256**（`code/.workbuddy/safe_reconcile.py`）；条目 `F:... | R:... | A:... | S:...`（**必须 ` | ` 分隔**）
- Bash 工具下 **`env -u VAR cmd` 会让子进程丢 stdio**（零输出、rc=0）→ 改脚本内 `os.environ.pop()`；终端 `*>` 重定向默认 **UTF-16LE**，先 `tr -d '\000'`；`cmd.exe /c` 与含重定向的 heredoc 会被拦 → 用编辑工具 + `git commit -F <file>`；.bat/.ps1 必须带 UTF-8 BOM；调 Python 前设 `PYTHONUTF8=1`

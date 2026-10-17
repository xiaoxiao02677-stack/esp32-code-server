# xiaozhi-esp32 / console-v2 项目记忆（长期 · 精简索引）

> 用法/参数见 `hardware/sets/README.md` 与 `code/.workbuddy/memory/2026-*.md` 日志；本文件只留结论与坑。

## 环境拓扑（同机双 VM）
- **生产** `ssh -p 22222 root@sandyun.top`(.10)：Java `/opt/xiaozhi/xiaozhi-esp32-api.jar`（systemd `xiaozhi-manager-api`，JDK21，日志 `/opt/xiaozhi/logs/`，外置配置 `/opt/xiaozhi/application-dev.yml`）；Python `/root/xiaozhi-server/main/xiaozhi-server/`（systemd `xiaozhi-server`，直接 `python app.py`）；MySQL root/123456 `xiaozhi_esp32_server`；Redis 127.0.0.1:6379 无密码；nginx 9001 明文 / 8443+9443 TLS / public 8001（分流 9002/9444）/ 8002→Java；前端 `/var/www/console-v2/`、`/var/www/cc-console/`
- **测试** `ssh -p 22223 root@sandyun.top`(.20)：根 `/root/yh/`；Java 源码 `/root/yh/app/manager-api/`、jar `/root/yh/deploy/opt-xiaozhi/`（须 JDK21）；Python `/root/yh/app/xiaozhi-server/`（WS 8000/HTTP 8003）；nginx 8101 明文 / 8144 TLS
- 一个崩另一个报连不上 8002/8003 → 先查根因再重启

## 仓结构 / git
- 仓根 `G:/demo/21_xiaozhi`：`docs/ hardware/ yh/ third_party/ tools/ code/`（reports + `.workbuddy` 记忆）
- `hardware/`(3.7G)：big_secreen、small_secreen(主工作区 my-s3-tft/COM12)、small_secreen_test(沙盒)、**camera(嵌套独立 git 仓**=上游 lckfb/szpi-esp32s3)、small_screen_camera、**sets(多版型中心)**、clawbot_llm、weixin_clawbot + fixes/artifacts/tests
- `yh/`：manager-api(Java)、manager-web(含**必须入库的 public/generator 75M**)、xiaozhi-server、console-v2、cc-console、_archive-order-module（**两套 order 不可混用**）。后端从生产 22222 `/root/xiaozhi-server/main/` 同步，排除 target/node_modules/models/data/.venv/.webpack_cache
- `.trash/` 可回滚、归档 `G:/demo/archive-20261015/`；**.gitignore 随移动同步**；嵌套 git 仓父仓必须 ignore；**构建产物一律不入库**（曾误提交 1718 文件使 .git 膨胀 468M）
- **★ 在用分支 `master`**；`test_environment` 停在 `d82f86e0` 已落后；提交前先 `git branch --show-current`。远端 `git@gitee.com:mm-Super-Nices/esp32-code-server.git`。`baseline.json` 保持追踪；`.workbuddy`/`.trash/` 永不提交

## 前端 / 服务端（要点）
- console-v2：`npm run build`→`dist`(base=/)；`npx vite build --mode admin`→`dist-admin`(base=/admincc/)。两产物 bundle 同名**仅 index.html 前缀不同** → admin 入口必须部署 dist-admin 的 index.html，否则 /assets 落 app 目录 404 白屏。生产 nginx `/assets/` 固定 root→`/var/www/console-v2/app`；cc-console API_BASE='/xiaozhi'
- 登录分流 `api.js`：`userState`(响应式 ref) + `refreshUserInfo()`(GET /user/info 兜底) + `defaultRouteAfterLogin()`(demo→/customer；hasAdminRole→/admin；其余 /customer)。生产 jar 9559d030 旧构建(TokenDTO 无 superAdmin/roles) → 前端以 `superAdmin===1` 为主判据；TopBar/DockNav 必须订阅 `userState`，勿裸读 localStorage
- 订单 `@RequestMapping("/xiaozhi/order")`：/page /{id} POST PUT DELETE(软删) /export /stats；VO **下划线命名**。**导出契约两环境不同**：本地源码 `POST /export` 返 CSV，生产旧 jar `GET /export` 返 JSON `{code:0,data:[...]}` → 前端双兼容
- Java 构建：`/d/INSTALL/maven/bin/mvnd.cmd -o -Dmaven.test.skip=true package`（**没有 `mvn`**，是 mvnd），产物 `target/xiaozhi-esp32-api.jar`。部署前核对 jar 内 Controller 数量（曾部署 37/43 旧 jar → 端点 404 连环误诊）。Python aiohttp `client_max_size` 默认 1MB → 大 payload 接口须显式调大（已 8MB）
- 唤醒词 `WakeWordService` 注册于 `connection.py` hello/device_register（断开双注销）；格式 `{"type":"device_config","payload":{"wake_word":[...]}}`（固件只认此 type）；**在线设备靠 push 生效，改 DB 不生效**。Push Scheduler 话题源 `POST /api/push/schedule`(memory/weather/chat)
- **SSH 写文件规范**：禁止把命令回显/标记混进内容（曾 `[rc=0]` 混入 YAML 致 Liquibase 崩溃）；用 heredoc 隔离，写完必 tail + 语法校验再重启

## ★ Python 配置装配（血泪，2026-10-17）
- 生产 `data/.config.yaml` 有 `manager-api.url` → **整份配置来自 Java API**（`get_config_from_api_async`），本地 `config.yaml` 只按**白名单**回填：`server`(ip/port/http_port/vision_explain/auth_key/heartbeat_port/ws_udp_heartbeat_port)、`prompt_template`、`TTS`、`selected_module.TTS`
- **★ 新增 server 键必须补白名单；新增顶层基础设施键（如 `redis`）必须在 `load_config()` 里显式透传** → 否则 `config.get("redis")` 恒为 None：壁纸回执悄悄丢失、待补投队列静默退化为纯内存，且**日志只有一句 WARNING 极易漏看**
- 排查手法：`cd <prod>/xiaozhi-server && .venv/bin/python -c "import asyncio;from config.settings import load_config;print(asyncio.run(load_config()).get('redis'))"`（`load_config` 是 **async**，不能直接 print）

## ★ 壁纸下发全链路（2026-10-17）
- 表：`ai_wallpaper` / `ai_wallpaper_task`（status/total/sent/success/failed，**不是 success_count**）/ `ai_wallpaper_task_device`（error/ack_time，**不是 err_msg**）；`create_date` 存 **UTC**（比 CST 差 8h）
- 下发接口 `POST /xiaozhi/wallpaperMag/...` → Java `WallpaperServiceImpl.dispatch` → 写 `device_config`（下次启动保底）+ `WallpaperDispatchClient` → Python `127.0.0.1:8003/api/wallpaper/dispatch`；返回 `{sent,queued,offline}`
- **`targetType` 必须是 `devices`（复数）**，"device" 被 `normalizeTargetType` 直接抛错；`10003 获取参数失败` 多义（参数缺失/设备不存在/目标空）
- **`version` 必须内容寻址 `3-<md5>`**（写死 `"3"` 会让固件按 version 幂等，第二张图永不生效）
- **★ 三级投递**（设备空闲态不保持 WS，WS 8000 是按次会话、心跳 TCP 12399 常连）：① WS 在线直投 `{"type":"wallpaper",...}`；② 心跳通道 `COMMAND/SET_WALLPAPER`（**需固件在 ADVERTISEMENT 声明该 operation**，老固件 `operations=[]` 走不通）；③ 待补投队列（`wallpaper:pending:<归一化MAC>`，TTL 7 天，**last-write-wins 每设备只留最新一条**）
- 补投三触发点：WS hello 注册 / 心跳重连或能力变更（`heartbeat_server.on_device_online`）/ 后台巡检 30s（`start_sweeper`，启动时 `hydrate()` 从 Redis 恢复）
- 回执：固件回 `{"type":"wallpaper","action":"result",...}` → Python `save_ack` 写 Redis `wallpaper:ack:<device_id>`（TTL 7 天）→ Java `buildDetail` **只在查详情时读 Redis 合并**（DB 行不落 applied）。故「回执 Redis 没通」等于任务永远 pending
- 运维接口：`GET /api/wallpaper/queue`（Bearer = DB `sys_params.server.secret`，`?flush=1` 强制补投一轮）
- 壁纸模块用 stdlib `logging`、项目用 loguru → 必须 `install_stdlib_log_bridge(__name__)`，否则 INFO 全丢（曾因此完全无日志）

## ★ ESP-IDF 环境（实测，build.py 已自愈）
- `IDF_PATH=D:\INSTALL\esp\v6.1\esp-idf`、`IDF_TOOLS_PATH=D:\INSTALL\esp`、`IDF_PYTHON_ENV_PATH=D:\INSTALL\esp\tools\python\v6.1\venv`、`ESP_IDF_VERSION=6.1`；权威记录 `C:\Espressif\tools\eim_idf.json`
- **`IDF_TOOLS_PATH` 不带 `\tools`**（工具在 `$IDF_TOOLS_PATH/tools/<name>/<ver>`）；eim/官方 profile 写 `...\esp\tools` 是**命名偏差，别照抄**（带 `\tools` 会让 `idf_tools.py check` 报 13 工具全缺失）
- **`idf.py` 在 Git Bash 下只打印提示就提前退出、退出码 0**（假绿）→ 校验必须在 CMD/PowerShell；调 `idf_tools.py export` 时子进程 env `pop("MSYSTEM")`
- PATH 里的 `python` 常是 `Python310-32`（无 rich_click）。`scripts/build.py:70` 用 `sys.executable` 起 idf.py → 错误解释器接力 → `No module named 'rich_click'`。**必须用 IDF venv python 启动编译**；`ESP_IDF_VERSION` 必补（`idf_extensions.py:388` 缺则 TypeError），`IDF_VERSION` **绝不能代设**
- 切版型后**必须删 `<FW>/build` 全量重编**；半成品 build 偶发 `component_requires.temp.cmake` 报错，重跑即好

## ★ hardware/sets 多版型中心（build / flash / diag）
- `hardware/sets/xiaozhi-esp32/` = **自带固件副本**（源码 ~10M，已入库，**无 `main/boards/zhengchen/`**）；上游 `hardware/small_screen_camera/xiaozhi-esp32` 只作参照；可 `--fw-root`/`XIAOZHI_FW_ROOT` 覆盖
- **职责分离**：`build.py`=选版型/同步/注册/编译/归档（**零串口**）；`flash.py`=探测 COM + esptool 烧录 + 三道闸（**不编译**）；`diag.py`=只读回读比对（**不写盘**）
- `flash.py` 用 importlib 按路径把 build.py 载成 `sets_build` 复用工具函数；缺 pyserial 时 `subprocess` 重跑自己（IDF venv python）——**别用 os.execve**（Git Bash + 重定向实测段错误 exit 139）
- 四套版型（统一接屿禾私有服务器：YH 协议 + 唤醒词「你好小禾」+ 16m 分区表 + assets）：
  - `yh-154tft-wifi` = 征辰 1.54 寸：ST7789 240×240，显示 SDA41/SCL42/RES45/DC40/CS21/**BL20**，音频 4/5/6/7/15/16，按键 0/10/39，电池 ADC8 / 充电 9 / RTC 保持 2
  - `yh-cam`：OV2640 + ES8311/ES7210 + PCA9557，**唯一有 AEC 回采**；`yh-big-ili9341`：ILI9341 + ES8311，**引脚未验证**
  - `yh-n16r8-st7789`：显示 47/21/45/40/41/**42**，仅 BOOT 键，**无电池/电量**（背光脚与第 1 项不同 → **选错版型必黑屏**）
- **★ 三条硬约束**：① `config.json` 的 `type`/`builds[].name` 全局唯一且 `type` 匹配 `^[a-z0-9.-]+$`（下划线非法，撞车直接终止编译）；② `config.json` 的 `sdkconfig_append` 是**权威真源**，`set.json` 是**增量追加层**、正常留 `[]`；③ CMakeLists 的 board 分支是 **4 行**，第 4 行 `set(DEFAULT_EMOJI_COLLECTION noto-color-emoji_64)` 别漏
- 注册块：`Kconfig.projbuild` 插 `endchoice` 前、`main/CMakeLists.txt` 插 board 链 `else()` 前；`# >>> SETS-BOARDS-BEGIN/END <<<` 标记幂等，改前备份 `*.bak-sets`。按硬件取舍：有回采才加 `USE_DEVICE_AEC=y`（仅 yh-cam）、有摄像头才加 `CAMERA_PSRAM_DMA=y`

## ★ 烧录（flash.py / diag.py）
- chip esp32s3 / **baud 默认 230400**（460800 写 4MB 实测断链）/ dio / 16MB / 80m；`0x0` bootloader、`0x8000` pt、`0xd000` ota_data_initial、`0x20000` xiaozhi.bin、`0x800000` generated_assets.bin；**assets 必须全量烧**（OTA 只刷 app）
- 布局：`v2/16m.csv` → nvs 0x9000 / otadata 0xd000 / phy_init 0xf000 / **ota_0 0x20000** / ota_1 0x410000 / assets 0x800000（**无 factory**，能否启动全看 otadata 选中的 ota_0/ota_1）；`v2/4m.csv` → **factory app @ 0x10000**
- **★ 三道闸（默认开）**：① 烧录前 `check_layout_consistency()` 核对「写入地址 vs 正在写入的分区表」同源（除固定 `0x0`/`0x8000`，每个写入地址必须落在表中某分区起址；app 必须落在 app 分区）→ 不同源**直接拒烧**；② 烧录后 `verify_written_regions()` 回读比对：小镜像全量、大镜像**头 4KB + 尾 4KB**（app 尾是整段 SHA256，能抓「写一半断链」）；③ `boot_check()` 复位读串口判「已启动 / 循环重启」（判据：**ROM 的 `ESP-ROM:` 横幅不受 sdkconfig 影响**，窗口内 ≥2 次即循环）。另有 `--clean`、`--no-verify`、`--boot-check SEC`
- **★ 写入策略**：**逐段**（一镜像一 esptool 会话，**按地址升序 → assets 垫底**，它断了设备照样能启动）→ 大镜像 **1MB 切块**（>1.5MB 才切，块界与 4KB sector 对齐）→ 每段写前 `flash-id` 探活（~1.8s）→ 失败 3 次 → 降档 → **换复位线序**（认对的写回 `plan.order`）。**旧顺序按 flash_args 书写顺序会把 assets 排在 app 前 → assets 断则 app 一字节没写，表现为「烧了没生效」**。开关 `--chunk-size 512K|1M` / `--no-chunk` / `--single` / `--skip-assets` / `--only assets`
- **★ 两种烧录方式**：`--mode idf`（交互菜单 1／回车默认）= 直接吃 `build/flash_args` 一条命令写完；`staged`（菜单 2；非交互默认）= 逐段加固；`diag` = 只体检。两模式共用闸门。**反相板不能真跑 `idf.py flash`**：`--before` 编译期固化于 `CONFIG_ESPTOOLPY_BEFORE`（`esptool_py/project_include.cmake:472`），`--extra-args` 又被追加在 `write-flash` 之后（实测 esptool 报 `No such option '--before'`）→ 反相板走「同一份 flash_args + 单会话 write-flash，只换复位」。`--idf-all` = `flash --all`。**调 idf.py 必须 pop `MSYSTEM`**，否则裸跑 `idf.py --version` 无输出且 rc=0（假绿）
- **★ diag 必须查 assets**：曾只查 boot/pt/otadata/app，两次翻车都在 assets。已加 `0x800000` 头 4KB + 尾 4KB；实测抓到「assets 写到 0xBADF58（~95%）后 192KB 全 0xFF，设备仍能启动」—— assets 垫底不影响启动，只缺末尾表情/字库。`--only assets` 可单独补
- **★ 死机形态（实测）**：`bootloader_reset at bootloader_utility.c:1163` + `rst:0x3 (RTC_SW_SYS_RST)` 无限循环 + 屏幕不亮 = **分区表与 app 不同源**（分区表 16MB 布局 ota_0@0x20000，app 却按 4MB 布局写到 0x10000）→ bootloader 在 0x20000 找不到首字节 `0xE9` 的合法镜像就自杀重启；`CONFIG_BOOTLOADER_LOG_LEVEL_NONE=y` 时一句话都不打。其余触发点：无 boot 分区(587) / 无 bootable app(626) / `boot_select==INVALID_INDEX`(start.c:55)。**排查 `diag.py`；处置 `flash.py --clean`**
- **★★ 复位线序（血泪）**：参考设计 DTR→GPIO0 / RTS→EN，esptool `--before default-reset` 按此假定；**本项目板子（实测 COM18）反相接线 DTR→EN / RTS→GPIO0** → default-reset 后芯片继续跑应用，日志首字节 `I`(0x49) 被当包头发 → `Invalid head of packet (0x49)`；**按住 BOOT 开机也无效**（esptool 连接阶段会再复位一次）
  - 判据：复位后 `boot:0x13/0x32 (DOWNLOAD(USB/UART0)) + waiting for download` = 反相；`boot:0x1b (SPI_FAST_FLASH_BOOT)` = 标准
  - `--reset auto`(默认) 先复位识别线序 → 反相板由脚本送进下载模式 + `--before no-reset`；探针 `_reset_lines(order)` = `dtr=T,rts=F` 保持 0.12s → `rts=T,dtr=F` → 释放
- **★ 每次 esptool 调用都是独立 connect→work→disconnect**；配 `--after no-reset` 时断开即退出下载模式 → 后续每次调用前**必须重新进下载模式**（否则 `Failed to connect … No serial data received`）
- 探测/诊断：`ThreadPoolExecutor` 一口一线程（**不复位设备**，open 前 dtr/rts=False）；**蓝牙虚拟口默认跳过**（`BTHENUM`，open() 实测卡 5～9s）；失败后自己回读 1.2s 串口判断「在跑应用/静默(已下载模式)/无输出」，不捕获 esptool stdout（rich/编码风险）；COM12 串口独占（PermissionError 13）；**别用 .bat 烧录**（语义指向上游目录）
- **ESP32 镜像魔数 `0xE9`**，头 `+0x4` = 入口点；`esp_app_desc` 用 `0xABCD5432` 定位，+16..48 = version（各版型 2.5.1）

## OTA / 固件包
- `POST /otaMag/upload`（multipart，只收 .bin/.apk，存 `<Java user.dir>/uploadfile/<md5>.bin`）→ `POST /otaMag`（**同 type 幂等 upsert**）
- 下发门控 `DeviceServiceImpl.buildFirmwareInfo`：`ai_device` 有行 **且** `auto_update=1` **且** `ai_ota.version > 设备上报 version` **且** `board.type == ai_ota.type`；URL=`server.ota.replace("/ota/","/otaMag/download/")+uuid`（Redis 一次性，限 3 次）
- **★ `ai_ota.version` 必须等于 bin 内嵌 `esp_app_desc.version`**，否则无限升级循环。发布 `ota_publish.py --board <id>|--all`；鉴权 `--token`（复用 DB `sys_user_token`）或 `--user/--password`（需 gmssl）
- `POST /ota/` 响应**扁平**：`{server_time, firmware{version,url}, websocket{url,token}, activation?}`；未绑定给 `INVALID_FIRMWARE_URL`；`auto_update=0` 时无 firmware 键。**尾斜杠坑**：`ota.cc:254` 拼出 `/xiaozhi/ota//config/version`，Java 用 `OtaSlashNormalizeFilter` 归一化；该接口必须返回 `version` **字符串**（`ota.cc:276` 校类型）

## 字形补字 / 心跳 / 音频 / TTS
- glyph_push：bundle `<prod>/xiaozhi-server/data/glyph_bundle/`（noto-v1-full，charset basic 890/common 6845）；`core/utils/glyph_provider.py` + `glyph_push.py`，挂 `sendAudioHandle.py`。契约：hello 的 `features.glyph_push===true` + `text_font{bundle,charset,size,bpp}` 须与 bundle 清单完全相等；硬限 64 字/64KiB。四版型内置 `font_noto_sans_basic_20_4` 且 assets 无 common → 设备报 charset=basic → **所有汉字都会被推送**（单句 ~3KB）
- 通道：固件 `websocket_protocol.cc:371` 写死 UDP 8002（fire-and-forget）；服务端 `core/heartbeat.py` 回 `{"type":"udp_heartbeat_ack"}`；开关 `XIAOZHI_WS_UDP_HEARTBEAT_PORT` > `server.ws_udp_heartbeat_port` > 8002
- **★ 固件 NotifyPlayer 只支持 Ogg Opus 单声道**（MP3 URL 必报 "Ogg stream ended before a complete audio stream"）→ 推送音频必须 `.ogg mono`；生产 `_ensure_device_playable_audio`（ffmpeg `-ac 1 -ar 24000 -c:a libopus -b:a 32k`）；`sent=1` ≠ 播放成功
- TTS：`S_` 前缀=私有复刻音色（授权随免费额度失效，403 code=45000030）→ **禁止入 DB**；推荐 TTS_DoubaoV3_V01；doubao_v3 的 resource_id 走 **X-Api-Resource-Id header**；真实配置在 MySQL `ai_model_config`(config_json)

## 鉴权 / AOCI / 工具坑
- 登录：`GET /user/pub-config` 取 sm2PublicKey → `GET /user/captcha?uuid=` → Redis `sys:captcha:<uuid>` → 密码 `'04'+sm2.doEncrypt(captcha+password, pk, 1)`（**验证码拼在密文里**）→ `POST /user/login`。更省事：复用 `sys_user_token`，头 `Authorization: Bearer <token>`；WS 测试设备须是 `ai_device` 已登记 MAC
- `sys_params.id` 是 **BIGINT 雪花**（不是 UUID）；缓存 key 是 paramCode 本身（`DEL sys:params` 无效）
- AOCI：`D:/INSTALL/aoci/aoci.exe` 靠 `.git` 定位根 → **必须显式 `--repo <绝对路径>`**；**`scan --force` 已锁**、**`scope apply/plan/preview` 有缺陷** → **严禁使用**；reconcile 只比 **raw sha256**（脚本 `code/.workbuddy/safe_reconcile.py`）；条目 `F:... | R:... | A:... | S:...`（**必须 ` | ` 分隔**）
- Bash 工具下 **`env -u VAR cmd` 会让子进程丢 stdio**（零输出、退出码 0）→ 改脚本内 `os.environ.pop()`；终端工具 `*>` 重定向默认 **UTF-16LE**，先 `tr -d '\000'`；`cmd.exe /c` 与含重定向的 heredoc 会被拦 → 用文件编辑工具 + `git commit -F <file>`；.bat/.ps1 必须带 UTF-8 BOM；调 Python 前设 `PYTHONUTF8=1`

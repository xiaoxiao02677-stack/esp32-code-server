# 服务端 / 前端 / 云端链路（细节库）

> 从 `MEMORY.md` 拆分出来的细节，索引仍看 `MEMORY.md`。

## 拓扑（同机双 VM）
- **生产** `ssh -p 22222 root@sandyun.top`(.10)：Java `/opt/xiaozhi/xiaozhi-esp32-api.jar`（systemd `xiaozhi-manager-api`、JDK21、日志 `/opt/xiaozhi/logs/`、配置 `/opt/xiaozhi/application-dev.yml`）；Python `/root/xiaozhi-server/main/xiaozhi-server/`（systemd `xiaozhi-server`）；MySQL root/123456 `xiaozhi_esp32_server`；Redis 127.0.0.1:6379 无密码；nginx 9001 / 8443+9443 TLS / public 8001（分流 9002/9444）/ 8002→Java；前端 `/var/www/console-v2/`、`/var/www/cc-console/`
- **测试** `ssh -p 22223`(.20)：根 `/root/yh/`，Java `app/manager-api/`、jar `deploy/opt-xiaozhi/`，Python `app/xiaozhi-server/`，nginx 8101/8144
- 一个崩另一个报 8002/8003 连不上 → 先查根因再重启

## 前端 / 服务端
- console-v2：`npm run build`→`dist`(base=/)；`npx vite build --mode admin`→`dist-admin`(base=/admincc/)。两产物 bundle 同名**仅 index.html 前缀不同** → admin 入口必须部署 dist-admin 的 index.html，否则 /assets 落 app 目录 404 白屏。nginx `/assets/` 固定 root→`console-v2/app`；cc-console `API_BASE='/xiaozhi'`
- 登录分流 `api.js`：`userState` + `refreshUserInfo()` + `defaultRouteAfterLogin()`(demo→/customer；hasAdminRole→/admin)。生产旧 jar 的 TokenDTO 无 roles → 以 `superAdmin===1` 为主判据；TopBar/DockNav 必须订阅 `userState`，勿裸读 localStorage
- 订单 `/xiaozhi/order`：/page /{id} POST PUT DELETE(软删) /export /stats；VO **下划线命名**。**导出契约两环境不同**：本地 `POST /export` 返 CSV，生产旧 jar `GET /export` 返 JSON → 前端双兼容
- Java 构建：`/d/INSTALL/maven/bin/mvnd.cmd -o -Dmaven.test.skip=true package`（**无 `mvn`**），产物 `target/xiaozhi-esp32-api.jar`，部署前核对 jar 内 Controller 数（当前 37）。Python aiohttp `client_max_size` 默认 1MB → 大 payload 须调大（已 8MB）
- 唤醒词 `WakeWordService` 注册于 `connection.py` hello/device_register（断开双注销）；格式 `{"type":"device_config","payload":{"wake_word":[...]}}`（固件只认此 type）；**在线设备靠 push 生效，改 DB 不生效**；Push Scheduler 话题源 `POST /api/push/schedule`
- **SSH 写文件**：禁止把命令回显混进内容（曾 `[rc=0]` 混入 YAML 致 Liquibase 崩）；用 heredoc 隔离，写完 tail + 语法校验再重启

## ★ Python 配置装配（血泪）
- 生产 `data/.config.yaml` 有 `manager-api.url` → **整份配置由 Java API 下发**，本地 `config.yaml` 只按**白名单**回填 `server`(ip/port/http_port/vision_explain/auth_key/heartbeat_port/ws_udp_heartbeat_port)、`prompt_template`、`TTS`
- **★ 新增 server 键必须补白名单；新增顶层基础设施键（如 `redis`）必须在 `load_config()` 显式透传**，否则 `config.get("redis")` 恒 None：壁纸回执悄悄丢、队列静默退化纯内存，日志只一句 WARNING 极易漏看
- 排查：`cd <prod>/xiaozhi-server && .venv/bin/python -c "import asyncio;from config.settings import load_config;print(asyncio.run(load_config()).get('redis'))"`（**`load_config` 是 async**）

## ★ 壁纸全链路
- 表：`ai_wallpaper` / `ai_wallpaper_task`（status/total/sent/success/failed，**非 success_count**）/ `ai_wallpaper_task_device`（error/ack_time，**非 err_msg**）；`create_date` 存 **UTC**（差 8h）
- 链路：Java `WallpaperServiceImpl.dispatch` → 写 `device_config`（下次启动保底）+ `WallpaperDispatchClient` → Python `127.0.0.1:8003/api/wallpaper/dispatch`，返回 `{sent,queued,offline}`
- **`targetType` 必须 `devices`（复数）**；DTO 字段是 **`deviceIds`**（不是 targetIds）；`10003 获取参数失败` 多义（参数缺失/设备不存在/目标空）。**`version` 必须内容寻址 `3-<md5>`**（写死 `"3"` 会让固件按 version 幂等，第二张图永不生效）
- **★ 三级投递**（WS 8000 按次会话、心跳 TCP 12399 常连）：① WS 直投 → ② 心跳 `COMMAND/SET_WALLPAPER`（需固件 ADVERTISEMENT 声明，老固件 `operations=[]` 不通）→ ③ 队列 `wallpaper:pending:<归一化MAC>`（TTL 7 天，**last-write-wins 只留最新**）
- 补投三触发：WS hello / 心跳上线 `on_device_online` / 30s `start_sweeper`（启动 `hydrate()` 恢复）；回执 `{"type":"wallpaper","action":"result"}` → `wallpaper:ack:<id>`，Java 仅查详情时读 Redis（**Redis 不通=任务永远 pending**）；运维 `GET /api/wallpaper/queue`（Bearer=`sys_params.server.secret`，`?flush=1`）
- 壁纸模块用 stdlib `logging`、项目用 loguru → 必须 `install_stdlib_log_bridge(__name__)`，否则 INFO 全丢

## OTA / 固件包
- `POST /otaMag/upload`（multipart，只收 .bin/.apk，存 `<Java user.dir>/uploadfile/<md5>.bin`）→ `POST /otaMag`（**同 type 幂等 upsert**）
- 门控 `buildFirmwareInfo`：`ai_device` 有行 **且** `auto_update=1` **且** `ai_ota.version > 设备上报` **且** `board.type == ai_ota.type`；URL=`server.ota.replace("/ota/","/otaMag/download/")+uuid`（Redis 一次性限 3 次）
- **★ `ai_ota.version` 必须等于 bin 内嵌 `esp_app_desc.version`**，否则无限升级循环。发布 `ota_publish.py --board <id>|--all`；鉴权 `--token`（复用 `sys_user_token`）或 `--user/--password`（需 gmssl）
- `POST /ota/` 响应**扁平**：`{server_time, firmware{version,url}, websocket{url,token}, activation?}`。**尾斜杠坑**：`ota.cc:254` 拼 `/xiaozhi/ota//config/version`，Java 用 `OtaSlashNormalizeFilter` 归一；该接口必须返回 `version` **字符串**（`ota.cc:276` 校类型）

## 字形 / 心跳 / 音频 / TTS
- glyph_push：bundle `<prod>/xiaozhi-server/data/glyph_bundle/`（noto-v1-full，basic 890/common 6845）；`glyph_provider.py`+`glyph_push.py` 挂 `sendAudioHandle.py`。契约：hello 的 `features.glyph_push===true` + `text_font{bundle,charset,size,bpp}` 须与清单完全相等；硬限 64 字/64KiB。四版型内置 `font_noto_sans_basic_20_4` 且 assets 无 common → 设备报 charset=basic → **所有汉字都推送**（单句 ~3KB）
- 心跳：固件 `websocket_protocol.cc:371` 写死 UDP 8002；`core/heartbeat.py` 回 `{"type":"udp_heartbeat_ack"}`；开关 `XIAOZHI_WS_UDP_HEARTBEAT_PORT` > `server.ws_udp_heartbeat_port` > 8002
- **★ 固件 NotifyPlayer 只支持 Ogg Opus 单声道**（MP3 URL 报 `Ogg stream ended before a complete audio stream`）→ 推送音频必须 `.ogg mono`（`-ac 1 -ar 24000 -c:a libopus -b:a 32k`）；`sent=1` ≠ 播放成功
- TTS：`S_` 前缀=私有复刻音色（授权随额度失效，403 code=45000030）→ **禁止入 DB**；推荐 TTS_DoubaoV3_V01，其 resource_id 走 **X-Api-Resource-Id header**；真实配置在 MySQL `ai_model_config`(config_json)

## 鉴权 / 工具坑
- 登录：`GET /user/pub-config` 取 sm2PublicKey → `GET /user/captcha?uuid=` → Redis `sys:captcha:<uuid>` → 密码 `'04'+sm2.doEncrypt(captcha+password, pk, 1)`（**验证码拼在密文里**）→ `POST /user/login`。省事：复用 `sys_user_token` + `Authorization: Bearer <token>`
- `sys_params.id` 是 **BIGINT 雪花**（非 UUID）；缓存 key 是 paramCode 本身（`DEL sys:params` 无效）
- AOCI：`D:/INSTALL/aoci/aoci.exe` 靠 `.git` 定位 → **必须 `--repo <绝对路径>`**；**`scan --force` 已锁**、**`scope apply/plan/preview` 有缺陷 → 严禁使用**；reconcile 只比 **raw sha256**（`code/.workbuddy/safe_reconcile.py`）；条目 `F:... | R:... | A:... | S:...`（**必须 ` | ` 分隔**）
- Bash 下 **`env -u VAR cmd` 会让子进程丢 stdio**（零输出、rc=0）→ 改脚本内 `os.environ.pop()`；终端 `*>` 重定向默认 **UTF-16LE**，先 `tr -d '\000'`；`cmd.exe /c` 与含重定向的 heredoc 会被拦 → 用编辑工具 + `git commit -F <file>`；.bat/.ps1 带 UTF-8 BOM；调 Python 前设 `PYTHONUTF8=1`

# xiaozhi-esp32 / console-v2 项目记忆（长期）

## 环境拓扑（同一物理机双 VM）
- **生产** `ssh -p 22222 root@sandyun.top`（192.168.50.10）：Java `/opt/xiaozhi/xiaozhi-esp32-api.jar`（systemd `xiaozhi-manager-api`，JDK21，日志 `/opt/xiaozhi/logs/`）；Python `/root/xiaozhi-server/main/xiaozhi-server/`；MySQL root/123456 库 `xiaozhi_esp32_server`；nginx 9001 明文 / 8443 / 9443 TLS，public 8001（stream 分流 9002/9444）；前端 `/var/www/console-v2/{app,admin,firmware-flash}` + `/var/www/cc-console/`；外置配置 `/opt/xiaozhi/application-dev.yml`
- **测试** `ssh -p 22223 root@sandyun.top`（192.168.50.20）：根 `/root/yh/`；Java 源码 `/root/yh/app/manager-api/`、运行 jar `/root/yh/deploy/opt-xiaozhi/xiaozhi-esp32-api.jar`（须 JDK21）；Python `/root/yh/app/xiaozhi-server/`（WS 8000 / HTTP 8003）；nginx 8101 明文 / 8144 TLS（对外统一 8100-8200）
- Java/Python 两服务联动：一个崩另一个报连不上 8002/8003，先查根因再重启
- 环境标题：console-v2 模板默认「屿禾工坊」；测试环境手动改 index.html title 为「测试环境」作标记

## 前端构建与部署
- console-v2 源码 `G:/demo/21_xiaozhi/console-v2/`；`npm run build`→`dist`(base=/)；`npx vite build --mode admin`→`dist-admin`(base=/admincc/)
- 两产物 bundle 同名（同一次源码构建），仅 index.html 引用前缀不同；**admin 入口必须部署 dist-admin 的 index.html**，否则 /assets 落到 app 目录 → 404 白屏
- 生产 nginx `/assets/` 固定 root → `/var/www/console-v2/app`；cc-console 源码 `G:/demo/21_xiaozhi/cc-console/`，API_BASE='/xiaozhi' 相对

## 登录角色分流（2026-10-15）
- api.js：`userState`（响应式 ref）+ `refreshUserInfo()`（GET /user/info 兜底）+ `defaultRouteAfterLogin()`（demo→/customer 保切换按钮；hasAdminRole→/admin；其余 /customer）+ `isDemoUser()`
- 生产 jar 9559d030 为旧构建（TokenDTO 无 superAdmin/roles）；前端双兼容靠 refreshUserInfo 以 `superAdmin===1` 为主判据
- TopBar/DockNav 必须订阅 `userState`，勿裸读 localStorage（无响应式不重算）

## 订单模块
- 后端 `OrderTableController @RequestMapping("/xiaozhi/order")`：`GET /page`、`GET /{id}`、`POST /`、`PUT /{id}`、`DELETE /{id}`（软删）、导出、`GET /stats`；权限 `@RequiresPermissions("xiaozhi:order:list|add|update|delete")`
- VO 序列化为**下划线**：`user_name/contact/product/amount/pay_time/address/remark/shipping_status`
- **导出契约两环境可能不同**：本地镜像源码=`POST /order/export` 返回 CSV 文本流；生产旧 jar 实测=`GET /order/export` 返回 JSON `{code:0,data:[...]}`（POST 报 method not supported）→ 前端导出须**双兼容**
- 前端 `console-v2/src/views/admin/Orders.vue`：head-actions（新增/刷新）、DataTable `#actions` 插槽（搜索/重置）、行内操作（编辑/删除）
- 生产 DB 已有 orders 测试数据；`/order/page` 返回 `{list,total}`

## 服务端规律
- Java 构建用 `-Dmaven.test.skip=true`（测试代码常滞后）；部署前核对 jar 内 Controller 数量（曾部署 37/43 旧 jar → 端点 404 连环误诊）
- Python aiohttp `client_max_size` 默认 1MB → 音频/大 payload 接口须显式调大（已 8MB）
- 唤醒词推送：`WakeWordService` 注册于 `connection.py` hello/device_register（断开双注销）；推送格式 `{"type":"device_config","payload":{"wake_word":[...]}}`（固件只认此 type）；空数组=清空回默认；在线设备靠 push 实时生效，改 DB 不自动生效
- Push Scheduler 话题源：`POST /api/push/schedule`（topic_sources: memory/weather/chat），TopicGenerator 须在 app.py 注入
- **SSH 写文件规范**：禁止把命令回显/标记混进写入内容（曾 `[rc=0]` 混入 YAML 致 Liquibase 崩溃）；用 heredoc 隔离，写完必 `tail` + 语法校验再重启

## 固件多版型中心 hardware/sets（2026-10-16 建成；当晚改造为自带副本 + 集成烧录）
- **架构**：`hardware/sets/xiaozhi-esp32/` 是**自带固件副本**（`<FW>`，仅源码 ~10M，排除 build/managed_components，**已入库**）；
  上游 `hardware/small_screen_camera/xiaozhi-esp32` **保留不动**（仍在 gitignore，作为上游参照）。可用 `--fw-root`/`XIAOZHI_FW_ROOT` 覆盖
  `build.py` 流程：选版型 →（副本缺 `managed_components` 时**自动从上游本地拷贝**，免联网重下 758M）→ 同步到 `<FW>/main/boards/yuhe/<id>/` → 幂等注册 → 编译 → 归档 → 可选烧录
- **四套版型**：`yh-154tft-wifi`(ST7789+直驱I2S) / `yh-cam`(OV2640+ES8311/ES7210+PCA9557，**唯一有 AEC 回采**) / `yh-big-ili9341`(ILI9341+ES8311，**引脚未验证**) / `yh-n16r8-st7789`(ST7789+MAX98357+INMP441)
- **用法**：`python hardware/sets/build.py [--board <id>] [--yes] [--sync-only] [--list]`；**切换版型后必须删 `<FW>/build` 全量重编**
- **烧录（2026-10-16 集成）**：`--flash`(编译后直烧) / `--flash-only`(只烧上次产物) / `--no-flash` / `--port COMx` / `--baud N`(默认460800)。
  串口用 pyserial 探测（回退 wmic，**必须按本机 OEM 编码解码**，否则 subprocess reader 线程抛 UnicodeDecodeError）；
  优先 `@flash_args`，不含 assets 时退回显式全量烧录（bootloader+分区表+ota_data+app+assets@0x800000）；
  **`--yes` 不自动烧录**（物理操作须显式 `--flash` 或交互回 y）。副本内 `yh_flash.bat` 的 `PROJECT_DIR` 已改 `%~dp0` 自适应（上游原值硬编码指向上游，在副本内会烧错 build）
- **★ 三条硬约束**：① `config.json` 的 `type`/`builds[].name` 全局唯一且 `type` 匹配 `^[a-z0-9.-]+$`（下划线非法）——固件 `_collect_variants()` 全量 rglob 查重，撞车直接终止编译；
  ② 两个 `sdkconfig_append` 语义不同：`config.json` 是**权威真源**，`set.json` 是**增量追加层**、正常留 `[]`；
  ③ CMakeLists 的 board 分支是 **4 行**，第 4 行 `set(DEFAULT_EMOJI_COLLECTION noto-color-emoji_64)` 别漏
- **注册块**：`<FW>/main/Kconfig.projbuild` 插 `endchoice`(716 行)前，`main/CMakeLists.txt` 插 board 链 `else()` 前；
  用 `# >>> SETS-BOARDS-BEGIN/END <<<` 标记，幂等，改前备份 `*.bak-sets`。**新增版型零改动，脚本自动扫描发现**
- **用户拍板**：四套版型**统一接入屿禾私有服务器**（YH 协议 + 唤醒词「你好小禾」+ 16m 分区表 + assets）。
  注：源板 `yuhe/1.54tft-wifi` 原本 `sdkconfig_append=[]`（走官方服务器），与 `yuhe/cam` 的 31 条不同源
- **按硬件取舍**：有回采才加 `USE_DEVICE_AEC=y`（仅 yh-cam；ES8311 的 `input_reference_` 硬编码 false、NoAudioCodecSimplex 无回采）；有摄像头才加 `CAMERA_PSRAM_DMA=y`

## 固件烧录
- **assets 分区必须全量烧录**（OTA 只刷 app）；换唤醒词/SR 配置 → config.json 改 CONFIG_SR_* → assets 打包 → app+assets 都变 → USB 全量烧录
- 全量模板（小屏 my-s3-tft，COM12，16MB）：`python -m esptool --chip esp32s3 -b 460800 --before default-reset --after hard-reset write-flash --flash-mode dio --flash-size 16MB --flash-freq 80m 0x0 build/bootloader/bootloader.bin 0x8000 build/partition_table/partition-table.bin 0xd000 build/ota_data_initial.bin 0x20000 build/xiaozhi.bin 0x800000 build/generated_assets.bin`
- COM12 串口独占（一会话一设备，争用报 PermissionError 13）；构建被杀用 ninja 前台续跑；merge-bin 可能滞后 → 分产物烧录更稳

## TTS 音色（火山引擎）
- `S_` 前缀=私有复刻音色（授权随免费额度失效，403 code=45000030）→ **禁止入 DB**；`ICL_uranus_*`=官方预置；推荐官方音色（TTS_DoubaoV3_V01 / zh_female_xiaohe_uranus_bigtts）
- doubao_v3 的 resource_id 走 **X-Api-Resource-Id header**；403 先判永久/临时，8 种永久码快速失败不重试，TTS 全失败补发 FIRST 字幕保底
- TTS 真实配置在 MySQL 表 `ai_model_config`（config_json 列），非 agent_config（不存在）

## 推送音频（2026-10-15 修复，硬约束）
- **固件 NotifyPlayer 只支持 Ogg Opus 单声道**（OpusHead 声道=1 + OpusTags + 合法帧时长；MP3 URL 必然 300ms 报 "Ogg stream ended before a complete audio stream"）→ **任何推送给设备的音频必须是 .ogg mono**
- 生产 topic_generator.py 已加 `_ensure_device_playable_audio`（ffmpeg `-ac 1 -ar 24000 -c:a libopus -b:a 32k` 转码，mp3 删除）；ffmpeg 临时输出必须带 .ogg 扩展名
- doubao_v3 上游每个 MP3 尾部带 150-450B 0xAA/0x55 垃圾（ffmpeg 可忽略，勿被误导）
- 验证工具：`code/tests/push_chain_simulator.py`（复刻固件 OggDemuxer 状态机，check <url> 判 PLAYABLE）
- 推送鉴权读 config.yaml 的 server.auth_key（非 data/.config.yaml）；`sent=1` ≠ 播放成功（设备先 ACK 再异步播放，无回执）

## AOCI 治理
- git 仓根 = `G:/demo/21_xiaozhi`，`xiaozhi-esp32` 为子目录；`aoci.exe`（`D:/INSTALL/aoci/aoci.exe`）靠 `.git` 定位根 → **必须显式 `--repo <子项目绝对路径>`**
- 双屏子项目：`code/big_secreen/xiaozhi-esp32`、`code/small_secreen/xiaozhi-esp32`（各带 .aoci）
- **`aoci scan --force` 已锁**；**`scope apply/plan/preview` 有缺陷**（不套用 exclude_dirs，index 从 ~1071 暴涨 ~9000+）→ **严禁使用**
- `governance_aligned:false` 是**结构性既存无害**（策略指纹不符，非内容漂移）
- 增量：`aoci update-entry --repo ... --source-sha256 <sha> <file[tag]>`；基线指纹刷新走手动 Python 编辑 baseline.json（套用 exclude_dirs + .git/.aoci/.workbuddy）
- **reconcile 铁律**：只比较 **raw sha256**，仅 raw 不同才刷新 sha256/size/normalized_sha256 三项；raw 相同保留原值（否则伪漂移）。安全脚本 `code/.workbuddy/safe_reconcile.py`（参数=repo 路径）
- aoci.code.txt 条目 `文件名[标签]: F:... | R:... | A:... | S:...`；规模档 S/T≈70 行（≥70 用 T）、~221→M、~449→L；**FRAS 四字段必须用 ` | `（空格竖线空格）分隔**，误用 `;`/`,` 会整行判为单 F 并报 fras_r/a/s_empty；`--preview --json` 只读探测可精确定位违规
- 660 二进制资产已人工翻 observe；全部 2808 二进制资产在基线中为 observe；baseline 编辑前必备份 `baseline.json.bak-<UTC>`

## 目录结构（2026-10-15 深夜重构后 · 双大目录）
- **仓库根**：README、docs/、hardware/、yh/、third_party/、tools/、code/（+隐藏 .git/.trash/.workbuddy/.aoci）
- **`hardware/`（固件，3.7G）**：big_secreen、small_secreen（主工作区 my-s3-tft/COM12）、small_secreen_test（沙盒，本地不入库）、camera（嵌套 git，szpi 板）、small_screen_camera（摄像头×小屏，活跃）、clawbot_llm、weixin_clawbot + fixes/artifacts/tests
- **`yh/`（web 后台+服务端，106M）**：manager-api（Java）、manager-web（前端，含**必须入库的 public/generator 75M**——DeviceManagement.vue 引用、本地不可重建）、xiaozhi-server（Python）、console-v2、cc-console、_archive-order-module（两套 order 不可混用红线）
- `third_party/`（hermes-agent-main、stylekit）、`tools/aoci-code`、`docs/`、`code/`（reports+.workbuddy 记忆）
- **yh 后端从生产 22222 `/root/xiaozhi-server/main/` 同步**（测试 22223 才是 /root/yh/；生产无 yh 目录），排除 target/node_modules/models/data/.venv/.webpack_cache
- 移动后 .gitignore 路径必须同步更新（失效规则会让 camera/沙盒 1.6G 脱离忽略）

## git / gitee 远端
- 远程 `git@gitee.com:mm-Super-Nices/esp32-code-server.git`（账号 mm-Super-Nices，SSH 已认证；本沙箱可直连 gitee/github）
- gitee `main` 与 `master` 均已同步为本地 main（master 曾用 `--force-with-lease` 覆盖，清除旧快照泄漏的私钥 certs/*.key）
- **2026-10-15 重构后已推送 `master`（faaafaaf）**：本地 test_environment HEAD → `git push gitee master`（与远端同源快进，无需 force）
- `baseline.json` 保持 git 追踪并提交（用户拍板，每次 reconcile 变更属预期）；`.workbuddy`、`.trash/` 临时产物永不进提交
- Windows 保留名 `nul` 已用 MoveFileExW 隔离至 `.trash/`；`safe_reconcile.py` 含 RESERVED 名跳过
- **活跃工作分支 = `test_environment`**（10-13 起所有工作提交于此，领先 main 30+ 提交）；main/master 为 gitee 同步分支，勿在其上直接开发

## 目录结构（2026-10-15 大整理后）
- 仓库根仅 9 项：README/docs/code/console-v2/cc-console/code-server-mirror/hermes-agent-main/stylekit/aoci-code + 隐藏 .git/.trash/.workbuddy/.aoci；`git status` 保持 0 余项
- **归档外移 → `G:/demo/archive-20261015/`**：网页后台(275M 最早期克隆)、test_environment(1.2G 部署包，远端 22223 才真实)、super_small_screen(原型)——历史仍在 git，可 `git rm --cached` 后 `git mv` 找回
- **.trash/ 可回滚区**（3.3G）：build 缓存×5、死 dist、scope 死重、4 补丁对、3 nul、token；确认无用后可 rm
- **嵌套 git 仓必须父仓 ignore**：`code/camera/`（上游完整仓，自带 .git，szpi-esp32s3 摄像头板 IDF v6.1，提交于其自身仓）、`code/small_secrenn_test/`（本地沙盒，不入库）
- camera 仓身份：非 xiaozhi 克隆，是**独立上游镜像**，board=lckfb/szpi-esp32s3，构建脚本 build_szpi.bat
- 活跃固件区 big/small/camera **build 已清空**（managed_components 保留）→ 下次构建需全量编译（时间成本换 2.5G 空间）
- 项目文档集中在 `docs/`（PROJECT-*.md/验收清单/tts 探针归档 docs/archive/tts-probe-20261009/）
- git 大文件教训：**super_small_screen/build 曾误提交 1718 文件**（.git 468M 膨胀主因），构建产物一律不入库

## OTA / 固件包管理（2026-10-16 打通）
- 管理端链路：`POST /otaMag/upload`（multipart，只收 .bin/.apk，存 `<Java user.dir>/uploadfile/<md5>.bin`，生产 user.dir=`/opt/xiaozhi`）→ `POST /otaMag`（**同 type 幂等 upsert**）
- 设备下发门控（`DeviceServiceImpl.buildFirmwareInfo`）：设备在 `ai_device` 有行 **且** `auto_update=1` **且** `ai_ota.version > 设备上报 application.version` **且** `board.type == ai_ota.type`；URL=`server.ota.replace("/ota/","/otaMag/download/")+uuid`（Redis 一次性 UUID，限 3 次，第 4 次 404）
- **★ `ai_ota.version` 必须等于 bin 内嵌 `esp_app_desc.version`**，否则升完仍报旧版本 → 无限升级循环。解析法：镜像里 find `0xABCD5432`，`off+16..48` = version（当前四版型/大屏/small_screen_camera 均为 `2.5.1`）
- **发布工具**：`python hardware/sets/ota_publish.py --board <id>|--all [--dry-run] [--verify --mac <已登记MAC>]`；鉴权 `--token`（推荐，可复用 DB `sys_user_token` 未过期 token）或 `--user/--password`（gmssl 未装则不可用）
- `POST /ota/` 响应是**扁平** JSON（无 code/data 包裹）：`{server_time, firmware{version,url}, websocket{url,token}, activation?}`
- **固件 OTA URL 尾斜杠 → 双斜杠请求**：`ota.cc:254` 在 `CONFIG_OTA_URL` 后直接拼 `"/config/version"` 得 `/xiaozhi/ota//config/version`；Java 用 `OtaSlashNormalizeFilter` 归一化（仅 `/ota/` 且含 `//` 时触发）
- 配置版本端点契约：`GET /ota/config/version?device_id=` 必须返回 `version` **字符串**（固件 `ota.cc:276` 校类型），可附 `download_url`；固件当前只比较并打日志，尚不真正下载
- 验收工具：`hardware/tests/ota_simulator.py`（复刻 `GetSystemInfoJson()` + `Device-Id` 头）

## 字形补字 glyph_push（2026-10-16 打通）
- 服务端：`/root/xiaozhi-server/main/xiaozhi-server/data/glyph_bundle/`（官方 `noto-v1-full`，16.6MB 压缩/35MB 解压，bundle_id=`noto-v1`，charset basic 890 / common 6845，profiles `14_1/16_4/20_4/30_4`）；下载源 `https://files.xiaozhi.me/assets/fonts/noto-v1-full.tar.gz`
- 代码：`core/utils/glyph_provider.py`（厂商官方逐字节）+ `core/utils/glyph_push.py`（接入层）；挂载点 `sendAudioHandle.py` 的 `send_tts_message`/`send_stt_message`/`send_display_message`
- 能力契约：hello 的 `features.glyph_push===true` + `text_font{bundle,charset∈{basic,common},size,bpp∈{1,4}}`，且 bundle/size/bpp 必须与 bundle 清单**完全相等**；提取器硬限 64 字/64KiB
- 四版型内置 `font_noto_sans_basic_20_4` 且 assets 无 common 字库 → 设备报 `charset=basic` → **所有汉字都会被推送**（顺带补齐小屏中文字显）；单句中文 ~3KB 字模
- 验收工具：`hardware/tests/glyph_push_simulator.py`（复刻 `text_glyph_payload.cc::Parse()` 全部拒绝规则）

## WS UDP 心跳 8002（2026-10-16 补齐）
- 固件 `websocket_protocol.cc:371` 写死 `host:8002` UDP，`OpenUdpChannel()` 在 WS 建链后无条件调用，**回包仅 ESP_LOGD → fire-and-forget 零依赖**
- 服务端 `core/heartbeat.py` 增 `_WsUdpHeartbeatProtocol`（回 `{"type":"udp_heartbeat_ack"}`）；开关：env `XIAOZHI_WS_UDP_HEARTBEAT_PORT` > `server.ws_udp_heartbeat_port` > 默认 8002，0=关
- **★ 坑**：`read_config_from_api=True` 时 `config_loader.py` 用**白名单重建** server 段 —— 新增 server 配置键必须同时补进白名单，否则永远读不到（`ws_udp_heartbeat_port` 已补）
- 公网 UDP 不可达（路由器只做 TCP 映射，同机 12399/UDP 亦然）；需真机回环要在出口路由器加 UDP 8002 映射，无需改固件
- 重启后约 20s 才打「心跳服务已启动」（VAD/ASR 初始化耗时），别过早判定失败

## 管理端鉴权速查
- 登录：`GET /user/pub-config` 取 `sm2PublicKey` → `GET /user/captcha?uuid=` → 从生产 Redis `redis-cli -n 0 get sys:captcha:<uuid>` 读答案 → `'04'+sm2.doEncrypt(captcha+password, pk, 1)` → `POST /user/login`
- **更省事**：直接复用 `sys_user_token` 表中未过期 token，请求头 `Authorization: Bearer <token>`
- WS 测试设备必须是 `ai_device` 里已登记的真实 MAC（Python 经 Java 校验，未登记直接断连）；也可用 `?device-id=` 查询参数代替请求头

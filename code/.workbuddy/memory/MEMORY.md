# xiaozhi-esp32 / console-v2 项目记忆（长期）

## 环境拓扑（同机双 VM）
- **生产** `ssh -p 22222 root@sandyun.top`(.10)：Java `/opt/xiaozhi/xiaozhi-esp32-api.jar`（systemd `xiaozhi-manager-api`，JDK21，日志 `/opt/xiaozhi/logs/`）；Python `/root/xiaozhi-server/main/xiaozhi-server/`；MySQL root/123456 `xiaozhi_esp32_server`；nginx 9001 明文/8443/9443 TLS + public 8001（stream 分流 9002/9444）+ public 8002→Java；前端 `/var/www/console-v2/{app,admin,firmware-flash}`、`/var/www/cc-console/`；外置配置 `/opt/xiaozhi/application-dev.yml`
- **测试** `ssh -p 22223 root@sandyun.top`(.20)：根 `/root/yh/`；Java 源码 `/root/yh/app/manager-api/`、jar `/root/yh/deploy/opt-xiaozhi/xiaozhi-esp32-api.jar`（须 JDK21）；Python `/root/yh/app/xiaozhi-server/`（WS 8000/HTTP 8003）；nginx 8101 明文/8144 TLS
- Java/Python 联动：一个崩另一个报连不上 8002/8003 → 先查根因再重启
- 标题：console-v2 模板默认「屿禾工坊」；测试环境手改 index.html title 为「测试环境」

## 目录结构（2026-10-15 重构后）
- 仓根 `G:/demo/21_xiaozhi`：README、docs/、hardware/、yh/、third_party/、tools/、code/（隐藏 .git/.trash/.workbuddy/.aoci）
- **hardware/（固件 3.7G）**：big_secreen、small_secreen（主工作区 my-s3-tft/COM12）、small_secreen_test（沙盒不入库）、camera（**嵌套独立 git 仓**=上游镜像 lckfb/szpi-esp32s3，build_szpi.bat）、small_screen_camera（活跃）、**sets（多版型中心）**、clawbot_llm、weixin_clawbot + fixes/artifacts/tests
- **yh/（后台+服务端 106M）**：manager-api(Java)、manager-web（含**必须入库的 public/generator 75M**）、xiaozhi-server(Python)、console-v2、cc-console、_archive-order-module（**两套 order 不可混用**）
- third_party/(hermes-agent-main、stylekit)、tools/aoci-code、docs/、code/(reports + .workbuddy 记忆)
- yh 后端从生产 22222 `/root/xiaozhi-server/main/` 同步（生产无 yh 目录），排除 target/node_modules/models/data/.venv/.webpack_cache
- 归档外移 `G:/demo/archive-20261015/`（早期后台克隆 275M、test_environment 1.2G、super_small_screen 原型），历史可 `git mv` 找回；.trash/ 可回滚区 3.3G
- 活跃固件区 big/small/camera 的 build 已清空（managed_components 保留）→ 下次构建全量编译
- 移动后 **.gitignore 路径必须同步更新**；嵌套 git 仓必须父仓 ignore；**构建产物一律不入库**（曾误提交 1718 文件使 .git 膨胀至 468M）

## git / gitee
- `git@gitee.com:mm-Super-Nices/esp32-code-server.git`（SSH 已认证，沙箱可直连）；已推 `faaafaaf`(10-15 重构)、`bc75ae80`(10-16 sets 入库 1785 文件)
- `baseline.json` 保持 git 追踪并提交（用户拍板）；`.workbuddy`、`.trash/` 永不提交
- Windows 保留名 `nul` 已 MoveFileExW 隔离至 `.trash/`；`safe_reconcile.py` 跳过 RESERVED
- **分支实况（10-16 复核，与旧记忆相反）**：当前检出并在用的是 **`master`** —— 10-15 重构以来的提交（`faaafaaf` → `bc75ae80` → `5d1aad54` → `c286c94a`）全部落在这里；
  `test_environment` 停在 `d82f86e0` 已落后，`main` 跟踪 `gitee/main`。**提交前先 `git branch --show-current` 确认**，别再照旧记忆往 test_environment 上做

## 前端与业务模块（console-v2 / cc-console）
- 源码 `G:/demo/21_xiaozhi/console-v2/`：`npm run build`→`dist`(base=/)；`npx vite build --mode admin`→`dist-admin`(base=/admincc/)。两产物 bundle 同名、仅 index.html 前缀不同，**admin 入口必须部署 dist-admin 的 index.html**，否则 /assets 落到 app 目录 → 404 白屏
- 生产 nginx `/assets/` 固定 root→`/var/www/console-v2/app`；cc-console 源码 `G:/demo/21_xiaozhi/cc-console/`，API_BASE='/xiaozhi'
- 登录分流：`api.js` 的 `userState`(响应式 ref) + `refreshUserInfo()`(GET /user/info 兜底) + `defaultRouteAfterLogin()`(demo→/customer；hasAdminRole→/admin；其余 /customer)。生产 jar 9559d030 为旧构建（TokenDTO 无 superAdmin/roles），前端以 `superAdmin===1` 为主判据；TopBar/DockNav 必须订阅 `userState`，勿裸读 localStorage
- 订单：`OrderTableController @RequestMapping("/xiaozhi/order")` 提供 /page /{id} POST PUT DELETE(软删) 导出 /stats；权限 `xiaozhi:order:list|add|update|delete`；VO **下划线命名**(user_name/contact/product/amount/pay_time/address/remark/shipping_status)。**导出契约两环境不同**：本地源码 `POST /export` 返 CSV，生产旧 jar `GET /export` 返 JSON `{code:0,data:[...]}` → 前端须双兼容

## 服务端规律
- Java 构建 `-Dmaven.test.skip=true`；部署前核对 jar 内 Controller 数量（曾部署 37/43 旧 jar → 端点 404 连环误诊）
- Python aiohttp `client_max_size` 默认 1MB → 大 payload 接口须显式调大（已 8MB）
- 唤醒词推送：`WakeWordService` 注册于 `connection.py` hello/device_register（断开双注销）；格式 `{"type":"device_config","payload":{"wake_word":[...]}}`（固件只认此 type）；空数组=清空回默认；在线设备靠 push 实时生效，改 DB 不生效
- Push Scheduler 话题源 `POST /api/push/schedule`(topic_sources: memory/weather/chat)，TopicGenerator 须在 app.py 注入
- **SSH 写文件规范**：禁止把命令回显/标记混进写入内容（曾 `[rc=0]` 混入 YAML 致 Liquibase 崩溃）；用 heredoc 隔离，写完必 tail + 语法校验再重启

## ★ ESP-IDF 环境（10-16 实测，build.py 已自愈）
- 正确取值：`IDF_PATH=D:\INSTALL\esp\v6.1\esp-idf`、`IDF_TOOLS_PATH=D:\INSTALL\esp`、`IDF_PYTHON_ENV_PATH=D:\INSTALL\esp\tools\python\v6.1\venv`、`ESP_IDF_VERSION=6.1`；权威记录 `C:\Espressif\tools\eim_idf.json`
- **`IDF_TOOLS_PATH` 不带 `\tools`**（工具在 `$IDF_TOOLS_PATH/tools/<name>/<ver>`）。eim idfToolsPath 与官方 profile 写成 `...\esp\tools`（**命名偏差别照抄**）；`idf_tools.py check`：父目录正常，带 `\tools` 报 13 工具全缺失。官方 profile 的 PATH 有陈旧条目 → 按实际可执行文件重建更稳
- **`idf.py` 在 Git Bash 下只打印提示就提前退出、退出码 0**（假绿）→ idf.py 验证必须在 CMD/PowerShell；调 `idf_tools.py export` 时子进程 env `pop("MSYSTEM")`
- IDF venv python=3.13.15（pyserial 3.5 / esptool 5.3.1 / rich_click）；PATH 里的 `python` 常是 `Python310-32`（无 rich_click）。固件 `scripts/build.py:70` 用 `sys.executable` 起 idf.py → 错误解释器接力 → `No module named 'rich_click'`。**必须用 IDF venv python 启动编译**；`ESP_IDF_VERSION` 必补（`idf_extensions.py:388` 缺则 TypeError），但 `IDF_VERSION` **绝不能代设**（idf.py:1157 有赋值+递归防护）
- 切版型后**必须删 `<FW>/build` 全量重编**；空/半成品 build 偶发 `component_requires.temp.cmake` 报错，重跑即好

## 固件多版型中心 hardware/sets（★ 拆为编译/烧录双脚本）
- **架构**：`hardware/sets/xiaozhi-esp32/` 是**自带固件副本**（`<FW>`，仅源码 ~10M，已入库）；上游 `hardware/small_screen_camera/xiaozhi-esp32` 不动（gitignore，作参照）。可 `--fw-root`/`XIAOZHI_FW_ROOT` 覆盖
- **★ 职责分离**：`build.py` = 选版型/同步/注册/编译/归档（**零串口操作**，收尾只打印 flash 命令）；`flash.py` = 多线程探测 COM 口 + esptool 烧录（**不编译**）
- `flash.py` 用 importlib 按路径把 build.py 加载为 `sets_build` 复用工具函数（色彩/GBK 降级/IDF 环境探测），不重复维护；缺 pyserial 时 `subprocess` 重跑自己（IDF venv 的 python）——**别用 os.execve**（Git Bash 下配合重定向实测段错误 exit 139）
- 四套版型：`yh-154tft-wifi`(ST7789+直驱I2S) / `yh-cam`(OV2640+ES8311/ES7210+PCA9557，**唯一有 AEC 回采**) / `yh-big-ili9341`(ILI9341+ES8311，**引脚未验证**) / `yh-n16r8-st7789`(ST7789+MAX98357+INMP441)。四套统一接入屿禾私有服务器（YH 协议 + 唤醒词「你好小禾」+ 16m 分区表 + assets）
- 用法：`build.py [--board <id>] [--yes] [--sync-only] [--list] [--python <venv python>]`，无需预先激活 IDF；缺 `managed_components` 自动从上游本地拷贝（免联网重下 758M）；同步到 `<FW>/main/boards/yuhe/<id>/`；归档 `out/<id>/`
- **★ 三条硬约束**：① `config.json` 的 `type`/`builds[].name` 全局唯一且 `type` 匹配 `^[a-z0-9.-]+$`（下划线非法，撞车直接终止编译）；② `config.json` 的 `sdkconfig_append` 是**权威真源**，`set.json` 是**增量追加层**、正常留 `[]`；③ CMakeLists 的 board 分支是 **4 行**，第 4 行 `set(DEFAULT_EMOJI_COLLECTION noto-color-emoji_64)` 别漏
- 注册块：`Kconfig.projbuild` 插 `endchoice` 前、`main/CMakeLists.txt` 插 board 链 `else()` 前；`# >>> SETS-BOARDS-BEGIN/END <<<` 标记幂等，改前备份 `*.bak-sets`；新增版型零改动自动发现
- 按硬件取舍：有回采才加 `USE_DEVICE_AEC=y`（仅 yh-cam；ES8311 的 `input_reference_` 硬编码 false）；有摄像头才加 `CAMERA_PSRAM_DMA=y`

## 固件烧录（flash.py）
- 参数：chip esp32s3 / baud 460800 / dio / 16MB / 80m；全量地址表 `0x0` bootloader、`0x8000` partition-table、`0xd000` ota_data_initial、`0x20000` xiaozhi.bin、`0x800000` generated_assets.bin
- **assets 分区必须全量烧录**（OTA 只刷 app）；换唤醒词/SR 配置 → config.json 改 CONFIG_SR_* → assets 打包 → app+assets 都变 → USB 全量烧录
- 优先 `@flash_args`（含 assets 时），否则显式全量；esptool 用 IDF venv python 跑并带 `_idf_env_vars()`
- **★★ 复位线序（血泪）**：Espressif 参考设计 DTR→GPIO0 / RTS→EN，esptool `ClassicReset`（=`--before default-reset`）按此假定；**本项目板子（实测 COM18 那块 yh-n16r8-st7789）是反相接线 DTR→EN / RTS→GPIO0** → default-reset 只让芯片跑应用，日志首字节 `I`(0x49) 被当成包头发 → 报 `Failed to connect to ESP32-S3: Invalid head of packet (0x49)`；**按住 BOOT 开机也无效**（esptool 连接阶段会再复位一次）
  - 判据：镜像时序复位后 `boot:0x13/0x32 (DOWNLOAD(USB/UART0)) + waiting for download` = 反相；`boot:0x1b (SPI_FAST_FLASH_BOOT)` = 标准（进了应用）
  - `flash.py --reset auto`（默认）先复位识别线序 → 反相板由脚本送进下载模式 + esptool `--before no-reset`（实测 460800 一次连上）；标准板维持 default-reset。另有 `--manual`（BOOT/RST 步骤+回车）、`--reset {esptool,reversed,none}`、`--before/--after`、`--attempts`
  - 探针 `_reset_lines(order)`：反相 = `dtr=T,rts=F` 保持 0.12s → `rts=T,dtr=F` → 释放；标准 = esptool 原样
  - esptool 打开串口前就设 `rts=False,dtr=False`（loader.py:441）→ 不会打扰已进下载模式的芯片，所以「先复位再交给 esptool」安全
- **多线程探测**：`ThreadPoolExecutor` 一口一线程，`as_completed` 谁先探完先打印；探测**不复位设备**（open 前 dtr/rts=False 避开自动复位电路）；只有 `--identify` 主动复位读 `ESP-ROM:` 判型号（两线序都试，完事把设备还原成运行状态）
- **烧录失败诊断**：不捕获 esptool stdout（rich 输出/编码风险），改为失败后自己回读 1.2s 串口判断「在跑应用 / 静默(已下载模式) / 无输出」，据此给建议
- **蓝牙虚拟口默认跳过**（hwid `BTHENUM` / 「蓝牙链接上的标准串行」）：能 open 成功会误判"在线"，且 open() 实测卡 5～9s；`--include-bluetooth` 强制纳入。状态四态：在线/被占用/打不开/跳过
- COM12 串口独占（争用报 PermissionError 13）；构建被杀用 ninja 前台续跑；merge-bin 可能滞后 → 分产物烧录更稳
- 副本内 `yh_flash.bat` 与上游 8 个 .bat 的 `PROJECT_DIR`/`cd` 已改 `%~dp0` 自适应（原值硬编码指向上游，在副本内会烧错 build）

## OTA / 固件包管理
- `POST /otaMag/upload`（multipart，只收 .bin/.apk，存 `<Java user.dir>/uploadfile/<md5>.bin`，生产 user.dir=`/opt/xiaozhi`）→ `POST /otaMag`（**同 type 幂等 upsert**）
- 下发门控（`DeviceServiceImpl.buildFirmwareInfo`）：设备在 `ai_device` 有行 **且** `auto_update=1` **且** `ai_ota.version > 设备上报 version` **且** `board.type == ai_ota.type`；URL=`server.ota.replace("/ota/","/otaMag/download/")+uuid`（Redis 一次性，限 3 次，第 4 次 404）
- **★ `ai_ota.version` 必须等于 bin 内嵌 `esp_app_desc.version`**，否则无限升级循环。解析：镜像 find `0xABCD5432`，`off+16..48`=version（当前各版型 `2.5.1`）
- 发布工具 `python hardware/sets/ota_publish.py --board <id>|--all [--dry-run] [--verify --mac <MAC>]`；鉴权 `--token`（可复用 DB `sys_user_token` 未过期 token）或 `--user/--password`（需 gmssl）
- `POST /ota/` 响应是**扁平** JSON：`{server_time, firmware{version,url}, websocket{url,token}, activation?}`；未绑定设备给 `INVALID_FIRMWARE_URL`；`auto_update=0` 时无 firmware 键
- **尾斜杠双斜杠坑**：`ota.cc:254` 拼出 `/xiaozhi/ota//config/version`；Java 用 `OtaSlashNormalizeFilter` 归一化。`GET /ota/config/version?device_id=` 必须返回 `version` **字符串**（`ota.cc:276` 校类型）
- 验收工具：`hardware/tests/ota_simulator.py`

## 字形补字 glyph_push
- 服务端 bundle `<prod>/xiaozhi-server/data/glyph_bundle/`（官方 noto-v1-full，16.6MB 压缩/35MB 解压，bundle_id=`noto-v1`，charset basic 890/common 6845，profiles 14_1/16_4/20_4/30_4）；代码 `core/utils/glyph_provider.py`（官方逐字节）+ `glyph_push.py`；挂载点 `sendAudioHandle.py` 的 send_tts/stt/display_message
- 契约：hello 的 `features.glyph_push===true` + `text_font{bundle,charset∈{basic,common},size,bpp∈{1,4}}`，须与 bundle 清单完全相等；提取器硬限 64 字/64KiB
- 四版型内置 `font_noto_sans_basic_20_4` 且 assets 无 common 字库 → 设备报 charset=basic → **所有汉字都会被推送**；单句中文 ~3KB 字模。验收工具 `hardware/tests/glyph_push_simulator.py`

## WS UDP 心跳 8002
- 固件 `websocket_protocol.cc:371` 写死 `host:8002` UDP，WS 建链后无条件调用，回包仅 ESP_LOGD（fire-and-forget）
- 服务端 `core/heartbeat.py` 增 `_WsUdpHeartbeatProtocol`（回 `{"type":"udp_heartbeat_ack"}`）；开关 env `XIAOZHI_WS_UDP_HEARTBEAT_PORT` > `server.ws_udp_heartbeat_port` > 默认 8002，0=关
- **★ 坑**：`read_config_from_api=True` 时 `config_loader.py` 用**白名单重建** server 段 → 新增 server 配置键必须同时补白名单
- 公网 UDP 不可达（路由器只做 TCP 映射）；真机回环需出口加 UDP 8002 映射，无需改固件。重启后约 20s 才打「心跳服务已启动」（VAD/ASR 初始化），别过早判定失败

## TTS 音色（火山引擎）
- `S_` 前缀=私有复刻音色（授权随免费额度失效，403 code=45000030）→ **禁止入 DB**；`ICL_uranus_*`=官方预置；推荐 TTS_DoubaoV3_V01 / zh_female_xiaohe_uranus_bigtts
- doubao_v3 的 resource_id 走 **X-Api-Resource-Id header**；403 先判永久/临时，8 种永久码快速失败不重试，TTS 全失败补发 FIRST 字幕保底
- TTS 真实配置在 MySQL 表 `ai_model_config`（config_json 列），非 agent_config（不存在）

## 推送音频（硬约束）
- **固件 NotifyPlayer 只支持 Ogg Opus 单声道**（MP3 URL 必然 300ms 报 "Ogg stream ended before a complete audio stream"）→ **推送音频必须 .ogg mono**
- 生产 topic_generator.py 有 `_ensure_device_playable_audio`（ffmpeg `-ac 1 -ar 24000 -c:a libopus -b:a 32k`）；ffmpeg 临时输出必须带 .ogg 扩展名
- doubao_v3 上游 MP3 尾部带 150-450B 0xAA/0x55 垃圾（ffmpeg 可忽略）；验证工具 `code/tests/push_chain_simulator.py`（复刻固件 OggDemuxer，check <url> 判 PLAYABLE）
- 推送鉴权读 config.yaml 的 server.auth_key（非 data/.config.yaml）；`sent=1` ≠ 播放成功

## 管理端鉴权速查
- 登录：`GET /user/pub-config` 取 sm2PublicKey → `GET /user/captcha?uuid=` → 生产 Redis `redis-cli -n 0 get sys:captcha:<uuid>` → 密码 `'04'+sm2.doEncrypt(captcha+password, pk, 1)`（**验证码拼在密文里**）→ `POST /user/login`
- 更省事：复用 `sys_user_token` 未过期 token，请求头 `Authorization: Bearer <token>`；WS 测试设备必须是 `ai_device` 已登记的 MAC（也可用 `?device-id=` 代替请求头）

## AOCI 治理
- 仓根 `G:/demo/21_xiaozhi`；`aoci.exe`(`D:/INSTALL/aoci/aoci.exe`) 靠 `.git` 定位根 → **必须显式 `--repo <绝对路径>`**
- **`aoci scan --force` 已锁**；**`scope apply/plan/preview` 有缺陷**（不套 exclude_dirs，index 1071→9000+）→ **严禁使用**；`governance_aligned:false` 是**结构性既存无害**
- 增量 `aoci update-entry --repo ... --source-sha256 <sha> <file[tag]>`；基线刷新走手动 Python 编辑 baseline.json
- **reconcile 铁律**：只比 **raw sha256**，仅 raw 不同才刷新 sha256/size/normalized_sha256 三项。安全脚本 `code/.workbuddy/safe_reconcile.py`
- aoci.code.txt 条目 `文件名[标签]: F:... | R:... | A:... | S:...`；规模档 S/T≈70 行（≥70 用 T）、221→M、449→L；**FRAS 必须用 ` | ` 分隔**，误用 `;`/`,` 会整行判为单 F；`--preview --json` 可定位违规
- 2808 个二进制资产在基线中为 observe；baseline 编辑前必备份 `baseline.json.bak-<UTC>`

## 工具使用坑（本机实测）
- Bash 工具下 **`env -u VAR cmd` 会让子进程丢 stdio**（零输出、退出码 0）→ 改在脚本内 `os.environ.pop()`
- 终端工具 `*>` 重定向默认写 **UTF-16LE**，用 `tr -d '\000'` 转 UTF-8 再 grep
- `cmd.exe /c` 从 Bash 调会被拦；heredoc 含重定向符号/终端关键字也被拦 → 改用文件编辑工具写内容，`git commit -F <file>`
- 代码里用 `os.execve` 替换镜像在 Git Bash 下配合重定向会段错误（实测 exit 139）→ 用 `subprocess` 重跑
- 写 .bat/.ps1 必须带 UTF-8 BOM；普通 PowerShell 里没有 `idf.py`（须 dot-source 激活脚本）

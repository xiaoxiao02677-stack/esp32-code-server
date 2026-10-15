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

## git / gitee 远端
- 远程 `git@gitee.com:mm-Super-Nices/esp32-code-server.git`（账号 mm-Super-Nices，SSH 已认证；本沙箱可直连 gitee/github）
- gitee `main` 与 `master` 均已同步为本地 main（master 曾用 `--force-with-lease` 覆盖，清除旧快照泄漏的私钥 certs/*.key）
- `baseline.json` 保持 git 追踪并提交（用户拍板，每次 reconcile 变更属预期）；`.workbuddy`、`.trash/` 临时产物永不进提交
- Windows 保留名 `nul` 已用 MoveFileExW 隔离至 `.trash/`；`safe_reconcile.py` 含 RESERVED 名跳过

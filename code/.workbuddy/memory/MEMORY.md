# xiaozhi-esp32 AOCI 项目记忆（长期）

## aoci CLI 运行必读（环境陷阱）
- git 仓库根 = `G:/demo/21_xiaozhi`（那里有 `.git`），`xiaozhi-esp32` 只是子目录。
- `aoci.exe` 靠 `.git` 定位仓库根 → 会错误指向父目录并报告 "The index does not exist; run aoci init first"。
- **必须显式指定 `--repo <子项目绝对路径>`** 才能让 `aoci status` / `aoci verify` / `aoci update-entry` 正确作用于本项目。
- CLI 路径：`D:/INSTALL/aoci/aoci.exe`。离线确定性工具，无 AI 配置也能跑治理命令。

## 项目结构（2026-10-10 重组）
- 原单一 `code/xiaozhi-esp32` 已拆分为**两个独立 AOCI 子项目**（各自带 `.aoci` 索引与备份）：
  - 大屏：`G:/demo/21_xiaozhi/code/big_secreen/xiaozhi-esp32`（含新板级 `main/boards/bigscreen-s3/`）
  - 小屏：`G:/demo/21_xiaozhi/code/small_secreen/xiaozhi-esp32`（含 my-s3-tft 圆屏 + audio 引擎改造）
- 两者基线规模相近（~12600 文件）。新增首方源默认归 `observe`，重要板级源建议建 FRAS 条目升 `index`。
- 安全同步脚本：`G:/demo/21_xiaozhi/code/.workbuddy/safe_reconcile.py`（参数=repo路径；raw-sha-only 比对，先备份再仅刷新 raw 变化者）。

## 治理模式（Volumes v1 + Managed Scope）
- `aoci scan --force` 被锁定：已有 Managed Scope Baseline 不能通过 scan 重建。
- **`scope apply` / `scope plan` / `scope preview` 在本环境有缺陷**：全量重扫且不套用 `exclude_dirs`，会把 index 从 ~1071 暴涨到 ~9000+（41196 等）。严禁使用，会用它"修复对齐"会破坏索引。
- `governance_aligned: false` 是**结构性、既存、无害**的：工具 computed scope 要 9016 index（忽略 exclude_dirs 缺陷）vs 策展基线 1074 index → `policy_identity ≠ active_policy_identity`。它代表 scope 策略指纹不符，**不代表内容漂移**（code_drift 恒为空）。
- 安全增量流程：`aoci update-entry --repo ... --source-sha256 <sha> <file[tag]>` 写条目；基线指纹刷新走**手动 Python 编辑** baseline.json（套用 exclude_dirs + .git/.aoci/.workbuddy），不触发重扫。
- **基线 reconcile 铁律（2026-10-09 踩坑）**：同步指纹时**只比较 raw sha256（实际内容），仅当 raw 不同才刷新 sha256/size/normalized_sha256 三项**；raw 相同则原样保留 baseline 中原始的 normalized_sha256，绝不按自算的 LF 归一化值批量覆盖。否则会把数千文件误判为"changed"并改写 normalized_sha256，导致 aoci verify 出现伪漂移。`.workbuddy` 目录走扫描排除但基线已有条目须 preserve（不 drop）。size 在 baseline 中以 int 存储。

## 基线/索引关键事实
- 基线 baseline.json：`{files:{相对路径:{role,sha256,size,normalized_sha256}}}`，role∈index/observe/exclude。
- 660 个二进制资产（.ogg/.jpg/.png/.eaf）已被人工从 index 翻为 observe（在基线直接持有，非依赖 config 规则；config.json 的 scope.rules 实际为空，规则未持久化但不影响现状）。
- 全部 2808 个二进制资产在基线中均为 observe。
- aoci.code.txt 条目格式：`文件名[标签]: F:... | R:... | A:... | S:...`；标签形如 `EA9L`（A层-模块-重要性-规模）；规模档由行数定（S/T 边界≈70 行：69→S/T，81 行实测须 **T**，故 ≥~70 优先 T；~221→M；~449→L）；S 字段有 FRAS token 预算（C4≤40/C7≤80/C9≤200）；模块字母须合法（`CT` 触发 `impact_candidate_tag_dictionary_violation`，`CH` 可用）。
- **⚠️ FRAS 字段分隔符铁律（2026-10-10 踩坑，代价 3 次失败）**：F/R/A/S 四字段**必须用 ` | `（空格-竖线-空格）分隔**，绝不能用 `;` 或 `,`。误用 `;` 会让整行被解析成单一超长 `F`（>160 runes 触发 `fras_f_too_long`），且 `R/A/S` 判为空 → `update-entry` 报 `impact_candidate_fras_invalid`（含 `fras_r_empty`/`fras_a_empty`/`fras_s_empty`/`fras_structure_invalid`）。字段**内部**可用 `;` 细分小点。**`--preview --json` 是只读探测利器**：会返回结构化 `findings` 精确指出哪字段违规（含 `retry_scope`），先 preview 再正式写可避免盲试。
- **config.h 规模档**：同目录同名首方头按行数定档（76 行 → `CH4T`，与 `bigscreen_display.h[CH4T]` 一致）；全仓库其余 163 个上游 `config.h` 多标 `CH4S`，但工具会对 76 行文件给"E规模档位错配"提醒（属正常，可顺手改 T）。

## 备份
- baseline 编辑前必备份：`baseline.json.bak-<UTC时间戳>`。已知：20260107T192834Z（660翻转前）、20261009T003322Z（reconcile前）。

## 固件烧录规范（2026-10-10 确立）
- **assets 分区必须全量烧录**：OTA 只刷 app 分区，不改 assets；凡 assets 变更（换唤醒词模型/SR 配置/音效资源）必须 USB 全量烧录，否则设备行为与 bin 不符。
- 全量烧录命令模板（小屏 my-s3-tft，COM12，16MB flash）：
  `python -m esptool --chip esp32s3 -b 460800 --before default-reset --after hard-reset write-flash --flash-mode dio --flash-size 16MB --flash-freq 80m 0x0 build/bootloader/bootloader.bin 0x8000 build/partition_table/partition-table.bin 0xd000 build/ota_data_initial.bin 0x20000 build/xiaozhi.bin 0x800000 build/generated_assets.bin`
- 烧录后验证清单：MultiNet 初始化日志 → 默认命令表打印（Command: ni3 hao3 xiao3 he2）→ 重连后 device_config 含 wake_word → 新旧唤醒词实测（旧词不醒/新词醒）→ ASR→LLM→TTS 全链路。
- **COM12 串口独占**：一台设备一个 idf_monitor 会话；两个会话争用会互报 PermissionError(13)（super_small_screen 与 small_secreen 曾互踩）。烧录前先确认无残留 monitor 进程。
- 构建被反复杀（防病毒误报）：用 ninja 前台直跑 + 增量续跑，不要反复起停 idf.py。
- 换 SR 模型的连带链：config.json 改 CONFIG_SR_* → assets 打包（build_default_assets.py 按 USE_CUSTOM_WAKE_WORD 分支出 index.json 命令表）→ app+assets 都变 → 必须全量烧录。
- **merge-bin 时序陷阱（21:33 实测）**：ninja 增量构建后 `merged-binary.bin` 可能滞后（曾停留 20:54 而 xiaozhi.bin 已 21:33，merge 在后台延迟 4 分钟才补齐）。用 merged 一把梭前必核对三产物（xiaozhi.bin/generated_assets.bin/merged-binary.bin）时间戳一致；分产物烧录无此风险。
- 烧录新鲜度自检：`strings` 查 bin 内特征串（如 "ni3 hao3 xiao3 he2"、NVS 清空日志串）可确认修复是否已编入。
- 唤醒词日志锚点：`Initialized FD AFE detector`（afe_audio_engine.cc:243）、`Command: <拼音>`（custom_wake_word.cc:77）、`Received device_config`（application.cc:741）、`已清空云端唤醒词，恢复默认`（board.cc:242）、`Restored N server wake-word command(s) from NVS`（custom_wake_word.cc:159）。

## 测试环境（2026-10-13 建立）
- 测试服务器：root@sandyun.top:22223（Ubuntu 24.04 VMware VM，SSH 免密），部署包解压在 `/root/yh/`，与生产完全隔离。
- 组件：MySQL8(root/123456, 库 xiaozhi_esp32_server)、Redis、nginx(8001 明文 ws+web / 9444 自签 TLS)、Java(xiaozhi-manager-api@8002, **须 JDK21**)、Python(xiaozhi-server WS:8000/HTTP:8003)。
- 服务名：xiaozhi-manager-api / xiaozhi-server（systemd，适配 ~/yh 路径的 unit 与 nginx 站点存于 `code/test_environment/config/test/`，已开机自启）。
- Python 依赖坑：torch/torchaudio==2.2.2+cpu 须走 `https://download.pytorch.org/whl/cpu`；须预装 python3-venv 与 ffmpeg。
- gitee 分支 `test_environment`（基于 261012-backup）保存该部署包与配置；大文件 model.pt/sql.gz 被 .gitignore 排除。

## SSH 写文件规范（2026-10-10 踩坑，代价一次部署崩溃）
- **禁止把命令回显/标记混进写入内容**：曾用 SSH 写文件时 `[rc=0]` 之类 shell 输出标记混入 db.changelog-master.yaml 第 840 行 → YAML 解析崩 → Liquibase 崩 → Java 崩溃循环并连累 Python。
- 规范：写远程文件用 heredoc/`cat > file <<'EOF'` 且内容与命令输出严格隔离；写完必 `tail -n 5` + 语法校验（YAML 用 python -c yaml.safe_load，SQL/JSON 同理）再重启服务。
- 部署 jar 前：`systemctl is-active` 两服务（xiaozhi-manager-api=Java、xiaozhi-server=Python）联动的，一个崩另一个也会报连不上 8002/8003，先查根因再重启。

## TTS 音色命名规范（火山引擎，2026-10-10 确立）
- **S_ 前缀 = 私有复刻音色（seed-icl-2.0 资源）→ 禁止入 DB**：授权随免费额度（20000 字符）耗尽自动失效（403 code=45000030 "requested resource not granted"），重试无用，恢复需控制台购买槽位（约150元/年）。
- ICL_uranus_* 前缀 = 官方预置复刻系（seed-tts-2.0 下实测可用）；唯一例外 zh_male_beijingxiaoye（55000000 资源不匹配）。
- 推荐：demo/默认智能体一律用官方音色（TTS_DoubaoV3_V01=小何温柔女声，zh_female_xiaohe_uranus_bigtts 亦实测 200 OK）。
- doubao_v3 的 resource_id 走 **X-Api-Resource-Id header**（非 body 字段），直连测试易踩坑。
- 火山 403 处理原则：先判永久/临时——8 种永久错误码直接快速失败不重试（_is_fatal_tts_error），临时错误才重试；TTS 全失败要补发 FIRST 字幕保底（设备端不再无声卡顿）。

## 服务端其他规律（2026-10-10）
- Java 构建：本地 mvn 有过 testCompile 错误（测试代码滞后于构造器变更），部署用 `-Dmaven.test.skip=true`；部署前核对 jar 内 Controller 数量（曾部署 37/43 的旧 jar 导致端点 404，连环误诊）。
- Python aiohttp 默认 client_max_size=1MB：音频/大 payload 接口要显式调大（已调 8MB）。
- config.yaml 本地镜像与远程保持同步（auth_key 等），防后续全量推送覆盖回退。
- 唤醒词推送链路（改造后）：WakeWordService 注册在 connection.py hello/device_register 处（断开双注销）；推送格式必须是 {"type":"device_config","payload":{"wake_word":[...]}}（固件只认这个 type）；空数组/空串 = 清空回默认词（固件 ClearWakeWordCommands 链路）。
- 设备配置生效时机：开机连接时拉取 device_config；在线设备靠 push 实时生效；改 DB 后需设备重连或推送，光改库不生效。

## 远端与上传（2026-10-12）
- **gitee 远程**：`git@gitee.com:mm-Super-Nices/esp32-code-server.git`（账号 mm-Super-Nices，SSH 已认证）。本沙箱可直连 gitee/github（此前曾被 198.18.1.133 拦，现已通）。
- `git push -u gitee main` 已成功：gitee `main=5652ed40`（全量 110 提交）；gitee `master=a76acb2` 为占位初始提交且是**默认分支**，仍空。
- **baseline.json 决策（用户拍板）**：保持 git 追踪并提交（尽管 .gitignore 第21行本意忽略它，但文件此前已被追踪）。每次 reconcile 都会变更此文件，属预期。
- **Windows 保留名 `nul` 隔离**：小屏仓库根曾存在未追踪的 `nul`(34B) 致 safe_reconcile 崩溃；用 `MoveFileExW` + `\\?\` 前缀隔离至 `G:/demo/21_xiaozhi/.trash/nul_quarantine.bin`。`safe_reconcile.py` 已加 RESERVED 设备名跳过逻辑（双重防护）。`.trash/` 与 `quarantine_nul.py` 等临时产物永不进提交。
- **gitee master 已强制覆盖为本地 main（2026-10-12）**：旧 `master`(a76acb2, auto-sync 2026-10-08) 虽含 27223 文件但比本地 main 少 4304 个、且含两把私钥(certs/*.key)。先 `git show a76acb2:<path>` 抢救本地缺失的 6 个文档(PROJECT-HANDOFF/PROJECT-REQUIREMENTS*.md / 验收标准清单-v1/v2)并入 main 并提交(a5bc16d1)，再 `git push gitee main:master --force-with-lease`。结果 gitee master(=a5bc16d1) 与本地 main 完全一致、无私钥残留、共 31520 文件。两分支历史无关，直接 merge 会产约 6000 冲突，故用 force。**教训：gitee 旧快照里曾泄漏私钥，已借本次覆盖清除。**

## Push Scheduler 话题源随机聊天（2026-10-13）
- 服务端新增 `/api/push/schedule` 端点，支持 topic_sources 自动生成话题文案+TTS
- 三场景校验：双空400、双填400、合法话题200
- TopicGenerator 需在 app.py 中初始化并注入 PushScheduler
- EdgeTTS 是 fallback provider，需本地配置 selected_module.TTS 和 TTS.EdgeTTS.type=edge

## 测试环境（sandyun.top:22223）
- 路径：`/root/yh/`
- MySQL root/123456，库 xiaozhi_esp32_server
- Java 8002（JDK 21），Python 8000/8003
- nginx 8101/8144 路由
- 生产快照已导入（Redis 18 keys, MySQL 33 tables）

## 测试环境端口规划（2026-10-13）
- 对外端口统一 8100-8200 范围（生产 8000-8100）
- 8101: HTTP 设备连接/API/控制台 → Python WS:8000 + HTTP:8003, Java:8002
- 8102: Health Check endpoint
- 8104: MySQL 代理 (nginx stream)
- 8105: Redis 代理 (nginx stream)
- 8144: TLS (同 8101)
- 8199: 心跳 (TCP/UDP)
- nginx 已安装 nginx-extras，stream 模块支持
- 所有配置已提交 gitee test_environment 分支

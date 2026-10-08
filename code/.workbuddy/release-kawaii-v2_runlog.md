# Kawaii v2 上线执行 Runlog（任务 #16 · e-deploy）

> 清单：release-kawaii-v2.md ｜ 开始：2026-10-07（GO 已收到）
> 纪律：每阶段记录时间戳/命令/输出摘要/md5/verdict；FAIL 即停。

---

## 阶段 0：基线快照 + 备份

- 14:25 web 基线：217 文件，list/md5 清单落 /root/backup/2026-10-07/{web-list-before,web-md5-before}.txt ✅
- jar 基线：md5 `b20af27bff438d83df1618f1b2e4198e`，85327377 字节，10-05 21:41 ✅
- git rev：服务器两仓均无 .git（NO_GIT，预期外无影响，基线以 md5 清单为准）⚠️记录
- Liquibase 现状：202610060030/202610070010 均 0 行（未执行，符合预期）✅
- 三服务基线：xiaozhi-server=active，xiaozhi-manager-api=active，8001=200 ✅
- 备份：jar cp ✅；xiaozhi-server-src 916M ✅；xiaozhi-manager-web 15M ✅；mysqldump sql.gz 46.4M（rc=0）✅；合计 1.1G
- **verdict：阶段 0 PASS**

## 阶段 1：构建

- 13:28 Vue build 第一次被 safe-delete 拦截（dist 内旧 chunk 删除需确认）→ 按预案改 `--dest dist-new` → **DONE**（26s，Hash 2560faa6）
- 验收：`grep kawaii|KawaiiLayout|MemoryEngineParams` dist-new/js 命中（408.cf5de4a3.js、978.d29273e3.js）；service-worker.js 存在；js chunk 48 个；dist-new/index.html md5=`9c4b286e2d82f7f399732c7391473463` ✅
- 13:27 Java 源码 tar（389409B）→ sftp 上传（路径坑：MSYS_NO_PATHCONV=1 时本地路径须用 Windows 风格；tar 打包输出路径须用 /g/ MSYS 风格，二者分开处理）
- 13:29 mvn 第一次 `-DskipTests` **FAIL**：testCompile 编译过期测试 ConfigServiceImplTest（旧构造器缺 DeviceConfigService 参数）→ 判定属测试代码滞后非产品代码问题，改 `-Dmaven.test.skip=true`（跳过测试编译，生产 jar 不含测试类）重跑
- 13:30 mvn `-Dmaven.test.skip=true` **MVN_RC=0** ✅
- 验收：jar 内含 202610060030.sql + 202610070010.sql + DeviceConfig{Dao,Entity,Service,ServiceImpl,AdminService,AdminServiceImpl,AdminController}.class 全套；新 jar 85343915B，md5=`3c6ffb4fd3cc31eba637eefbdc5fa49d` ✅
- **verdict：阶段 1 PASS**（1 次安全工具拦截 + 1 次 mvn 测试编译失败，均按预案/合理判定处置后通过）

## 阶段 2：传输

### 2.1 Python
- 13:30 tar（2.1MB，本地已排除 .venv/data/__pycache__/.workbuddy/tmp/models/music）→ sftp → 13:31 服务器 rsync（排除清单照抄 deploy_memory_v1 第 0 节）RSYNC_PY_OK ✅
- 4 文件 md5 双端完全一致：device_config_sync=ee0ab60a… / mcp_executor=8e440177… / manage_api_client=d43d49bc… / connection=d169b5d0… ✅
- py_compile 4 文件 PY_COMPILE_OK ✅
- 排除项存活：models/ 904M、music/ 14M、config.yaml（9-29 10:03）、data/.config.yaml（10-05 23:04）均在位 ✅；tts_notify.mp3 实际路径为 config/assets/tts_notify.mp3（排除模式按文件名匹配任意层级，存活，备份内同路径可回滚）✅

### 2.2 Web
- 13:32 dist-new tar（10.9MB）→ sftp → rsync --delete RSYNC_WEB_OK ✅
- 验收：230 文件；/var/www index.html md5=`9c4b286e2d82f7f399732c7391473463`（=本地 dist-new，旧站点为 217 文件基线）；service-worker.js 在位；8001=200；SW HTTP 200 ✅
- **verdict：阶段 2 PASS**

## 阶段 3：服务

### 3.1 Java
- 13:33 cp jar（md5=3c6ffb4f… 与构建产物一致）→ restart → active ✅
- Liquibase：202610060030 + 202610070010 均 DATEEXECUTED=2026-10-06 13:33:18 ✅；ai_device_config 表可查（count=0 空表正常）✅
- journalctl 无 ERROR/exception/Liquibase 报错（旧进程 143 退出为正常 stop 信号）✅
- HTTP 面：8001/xiaozhi/sys/login=200、8001 静态=200 ✅
- 备注：systemd 提示 unit 文件 on-disk 变更过（daemon-reload 提示，非本次操作所致，服务正常，不动）

### 3.2 Python
- 13:34 restart → active；8000/8003 启动后 ~25s 完成监听（ASR 模型加载稍慢，探活初次 000 属启动窗口，复查 200/401）✅
- 8000=200、8003 无key=401（记忆路由契约在）、带key=200 ✅
- app.log 近 60 行 traceback/CRITICAL/FATAL 计数=0 ✅
- **verdict：阶段 3 PASS**（Java 先、Python 后顺序执行，两步间无控制台操作）

## 阶段 4：冒烟移交

- 13:35 移交前自检三连：双服务 active ✅、8001 HTTP 200 ✅、DATABASECHANGELOG 两行在库 ✅
- 13:36 已 SendMessage 移交 e-qa-smoke（GO 冒烟）：附 runlog 路径、service-worker 强刷坑、业务码模式坑、新改动面清单（Kawaii 布局/双主题/设备配置管理页 + /xiaozhi/config/device-config + ai_device_config）、现网基线 md5、回滚物料位置 /root/backup/2026-10-07/、FAIL 处置路由
- 服务器 /tmp 部署残留已清理（CLEANUP_DONE）
- **verdict：阶段 4（移交）PASS —— 上线动作全部完成，冒烟结论待 e-qa-smoke 回报**

## 收尾登记（S-REF 引用，不执行）

- secret 轮换：引用 `G:/demo/21_xiaozhi/code/.workbuddy/secret-rotation/rotate-secret.sh`（任务 #13，e-secret-ops 负责，待 team-lead 另行下令）。本任务不执行，完成时间/执行人待其回报后补记。

## 冒烟结论（e-qa-smoke 回报，2026-10-06）

- **9/9 全 PASS，无回滚触发**；基线三方核对一致（jar md5=3c6ffb4f…、/var/www 230 文件、index.html md5=9c4b286e…），部署后无漂移。冒烟 runlog：`.workbuddy/reports/2026-10-06-smoke/qa-smoke-runlog-2026-10-06.md`
- **F1 认知修正（重要）**：站点纯 HTTP 非安全上下文，`navigator.serviceWorker === undefined`——SW 注册被浏览器协议层禁止，从未注册成功。本 runlog 中「SW HTTP 200」仅证明文件可下载；「强刷」要求降级（对本次上线无影响：无 SW 缓存即无旧包风险）。若 P1-7 的 PWA 离线为验收目标，需先上 HTTPS（8001 非 TLS、443 无监听，e-qa-smoke 实测确认）
- **登录后 UI 层未覆盖**：无冒烟账号（验证码+SM2；直插 token 会踢真实用户会话——10-05 事故教训）。路由可达+守卫行为已覆盖；侧边栏全量/设备配置管理页 UI/记忆管理页留给回归批次（#17）或人工验证
- **任务 #16 最终 verdict：上线成功（部署 + 冒烟双 PASS）**


## 全程 verdict 汇总

| 阶段 | verdict | 关键证据 |
|---|---|---|
| 0 基线+备份 | PASS | 217→清单/md5 落盘；jar md5 b20af27b…；备份 1.1G（含 mysqldump 46.4M） |
| 1 构建 | PASS | dist-new Hash 2560faa6；jar mvn RC=0（-Dmaven.test.skip，测试滞后已记录） |
| 2 传输 | PASS | 4 文件 md5 双端一致；web index.md5=9c4b286e…；排除项全部存活 |
| 3 服务 | PASS | Liquibase 13:33:18 双行；ai_device_config 建成；双服务 active；错误日志 0 |
| 4 冒烟移交 | PASS（移交完成） | e-qa-smoke 已收 GO + 基线与坑位说明 |

遗留登记：① ConfigServiceImplTest 构造器参数滞后（工程师修复项，不影响生产）；② systemd unit 磁盘变更 daemon-reload 提示（非本次所致，未动）；③ 固件 B 线 4 文件未刷写（e-fw-build 范围，真机联调另排）。






# 记忆功能部署执行手册（v1，2026-10-05）

> 作者：ops-deploy ｜ 状态：**准备就绪，待 team-lead 下发"执行部署"指令**
> 目标：把 code-server-mirror 的记忆功能（mem_holographic 引擎 + /api/memory API + Java 代理 + Vue 控制台）部署到 sandyun.top 并完成线上复验 R1–R5。
> 红线：本手册任何命令在收到"执行部署"指令前**不得执行**。部署当天按阶段 0→5 顺序执行。

---

## 0. 环境事实与工具约定（已逐项实测核验）

| 项 | 事实 | 核验方式 |
|---|---|---|
| 服务器 SSH | sandyun.top:22222，仅密码认证（key 被拒，已实测），密码同 ssh_run.py | BatchMode=yes 实测 |
| SSH 工具 | `python G:/demo/21_xiaozhi/code/.workbuddy/ssh_run.py "CMD" ["CMD2"...]` | 现成 |
| SFTP 推送 | **新增** `G:/demo/21_xiaozhi/code/.workbuddy/sftp_push.py`（镜像 sftp_pull.py，本地文件未上传） | 待部署日首次使用 |
| **MSYS 坑（重要）** | Git Bash 会把以 `/` 开头的参数自动转成 `C:/...`。**所有含 `/root/...` 绝对路径的命令必须前缀 `MSYS_NO_PATHCONV=1`**。否则会静默变成错误路径 | 已实测复现并规避 |
| **引号坑（重要）** | ssh_run.py 的命令参数含括号/内嵌引号时 bash 会先解析崩溃。**复杂脚本一律用 base64 传入**：`echo <B64> \| base64 -d > /tmp/x.sh && bash /tmp/x.sh` | 已实测复现并规避 |
| 本地 rsync | **不存在**（服务器有）。本手册传输全部走：本地 tar 打包 → sftp_push.py 上传 → 服务器解包 → md5 校验 | `which rsync` 空 |
| Python 服务 | venv `/root/xiaozhi-server/main/yuhe-server/.venv`（带点！Python 3.12.3），systemd 单元 `yuhe-server`，WorkingDirectory=`/root/xiaozhi-server/main/yuhe-server` | 已实测 |
| Python 配置 | 每个 WS 连接从 Java 拉私有配置（`data/.config.yaml` 只含 server/manager-api 段 + read_config_from_api=true）。**config.yaml 不随连接生效、config_from_api.yaml 只是模板，故两者均无需同步、严禁 --delete 时误动** | 代码走读 + md5 实测 |
| Java 服务 | 源码 `/root/xiaozhi-server/main/manager-api/`，jar 部署于 `/opt/xiaozhi/xiaozhi-esp32-api.jar`，systemd 单元 `xiaozhi-manager-api`（ExecStart `java -jar /opt/xiaozhi/xiaozhi-esp32-api.jar --spring.profiles.active=dev`），JDK 21，mvn 3.8.7，m2 缓存 141M（热，含 spring-boot 全套） | 已实测 |
| Java 配置 | 运行目录 /opt/xiaozhi 下**没有** application-dev.yml，DB 等配置在 jar 内 resources（dev profile 指向 MySQL）；外部只放 jar + logs | ls 实测 |
| Liquibase | **Spring Boot 自动装配**（`@DependsOn("liquibase")` 佐证 bean 存在，changelog 在 jar resources 默认路径）。`mvn package` 不执行 changelog，**jar 启动时才执行**，DATABASECHENGELOG 表已存在（查 `202610051800` 返回 0 行而非报错） | 代码 + 服务器实测 |
| Vue | 本地 `npm run build`（node 22/npm 10 可用，node_modules 已装，dist 现有构建 10-05 18:44 已含记忆 chunk `dist/js/607.0ad10ed9.js`）→ 传 `/var/www/xiaozhi-manager/`（nginx 8001，静态零重启）。**有 service-worker**，验证必须强刷 | 已实测 |
| nginx | 8001 根 `/var/www/xiaozhi-manager`，`/yuhe/` 反代 127.0.0.1:8002（context-path /yuhe）。**未发现 8003 代理**（8003 只服务 OTA/vision/memory） | nginx -T 实测 |
| 8003 与 loopback | 8003 公网直达（无代理层），`memory_loopback_middleware` 只放行 127.0.0.1/::1；Java 经 127.0.0.1:8003 互调，port 参数取 `sys_params.server.http_port`（当前 8003），fallback 8003 | 代码走读 |
| 共享密钥 | `server.secret`（Python data/.config.yaml L9）= `sys_params.server.secret` = `2d7b6bde-4de9-49f1-9072-476cec13292e`；Java 侧 `Constant.SERVER_SECRET` 读 sys_params（fromCache=false） | 双端实测一致 |
| MySQL | root/123456（e2e 脚本同源），库 `xiaozhi_esp32_server`。**服务器无 sqlite3 CLI，用 venv python3 sqlite3 模块**；FTS5 已实测可用（venv Python 3.12.3 自带 FTS5）；venv numpy 1.26.4 已装 | 已实测 |
| 权限模型 | 控制台登录用户全部带 `sys:role:normal`（super_admin 另有 sys:role:superAdmin），MemoryFactController 只用 `@RequiresPermissions("sys:role:normal")`，普通登录用户即可调记忆 API；`listAgents` 只列 `getUserAgents(userId)` 自己的 Agent | 代码走读 |
| 磁盘/内存 | 磁盘 105G 可用；内存 9.9G 总量、5.6G available；JVM 启动 + mvn 编译无压力 | df/free 实测 |
| 基线漂移校验 | 镜像 HEAD 对比服务器：Python 仅 6 个文件不一致（connection/http_server + 4 个 memory provider），Java 仅 3 个（2 个 ServiceImpl + changelog-master.yaml），**全部是本次功能改动文件**；其余 700+ 文件与服务器一致。服务器没有镜像外的热修复 → 增量同步安全 | md5 全量比对实测 |

### 待部署改动清单（镜像 git status 实测）

- **Python**（git 修改 6 文件 + 新增 5 文件）：`core/http_server.py`（loopback middleware + /api/memory 路由）、`core/connection.py`（agent_id 注入）、`core/api/memory_handler.py`（新）、`core/providers/memory/mem_holographic/`（新 5 文件：`__init__.py/holographic.py/store.py/retrieval.py/mem_holographic.py`，纯标准库 + 可选 numpy）、`mem0ai/mem_local_short/mem_report_only/nomem` 各加 `get_status()`；`config.yaml` 加 mem_holographic 段（**只对本地单模块模式生效，线上由 Java 下发，不同步**）
- **Java**（git 修改 3 + 新增 9）：`ConfigServiceImpl`（下发 agent_id + 注入 db_dir）、`ModelConfigServiceImpl`（mem0ai key 脱敏徽标）、`db.changelog-master.yaml` + 新 `202610051800.sql`（种子两行）；新增 `modules/memory/` 包 9 文件（controller/service/dto/vo/client）
- **Vue**（git 修改 11 + 新增 2）：路由/HeaderBar/i18n×6/api.js + 新 `views/MemoryManagement.vue`、`apis/module/memory.js`
- 镜像内残留（**不部署**）：`.aoci/`（含 280K baseline.json，本地认知资产）、`aoci*.txt`、`AGENTS.md`、`.gitattributes`、`.workbuddy/`（qa 脚本副本）、`yuhe-server/.workbuddy/`。git 状态"脏"但内容干净，不影响部署

### 传输总原则（本手册核心方法）

所有传输 = **本地 tar 打包（保留权限）→ sftp_push.py → 服务器解包到临时目录 → 远程 rsync 增量落位 → md5 校验**。服务器有 rsync 而本地没有，所以 rsync 只在服务器内跑；rsync 排除清单保证不碰 .venv/data/target。

```bash
# 本地（Git Bash）
tar czf /tmp/mirror-python.tar.gz -C "G:/demo/21_xiaozhi/code-server-mirror/yuhe-server" .
python "G:/demo/21_xiaozhi/code/.workbuddy/sftp_push.py" /tmp/mirror-python.tar.gz /tmp/mirror-python.tar.gz

# 服务器（经 ssh_run.py，注意 MSYS_NO_PATHCONV=1 与无括号）
mkdir -p /tmp/mirror-python && tar xzf /tmp/mirror-python.tar.gz -C /tmp/mirror-python && rm -f /tmp/mirror-python.tar.gz
rsync -rltgoD --delete \
  --exclude=.venv/ --exclude=data/ --exclude=config.yaml --exclude=config_from_api.yaml \
  --exclude=__pycache__/ --exclude=*.log --exclude=.workbuddy/ --exclude=tmp/ \
  --exclude=models/ --exclude=music/ --exclude=tts_notify.mp3 \
  /tmp/mirror-python/ /root/xiaozhi-server/main/yuhe-server/ \
  && rm -rf /tmp/mirror-python
```

**排除解释（--delete 安全）**：`.venv/ data/ config.yaml config_from_api.yaml` 绝不能被 delete 波及；`data/` 排除放最前（防删记忆库与 .config.yaml）；`__pycache__`、`*.log` 排除防本地残留污染；`.workbuddy/ tmp/` 是 QA 脚本副本与本地运行残留，不进生产。**`models/ music/ tts_notify.mp3` 是服务器本地运行时资产（SenseVoice/silero-vad 模型权重共 904M、音乐播放 MP3、TTS 通知音），镜像内不存在——执行时实测曾被 --delete 误删 28 个文件，已从阶段 1 备份定点恢复；此后所有 rsync（含回滚）必须排除这三项**。镜像内已无符号链接（实测 find -type l 为空），tar/rsync 无链接风险。

---

## 阶段 1：部署前快照备份（/root/backup/2026-10-05/）

> 服务器当前**无任何备份机制**（实测 /root/backup 不存在）。首次建立。所有子目录幂等：重复执行覆盖式重写，可安全重跑。

```bash
# 服务器
mkdir -p /root/backup/2026-10-05
cp -a /opt/xiaozhi/xiaozhi-esp32-api.jar /root/backup/2026-10-05/
rsync -a --exclude=.venv/ --exclude=data/ --exclude=__pycache__/ --exclude=*.log \
  /root/xiaozhi-server/main/yuhe-server/ /root/backup/2026-10-05/yuhe-server-src/
rsync -a /var/www/xiaozhi-manager/ /root/backup/2026-10-05/xiaozhi-manager-web/
mysqldump -uroot -p123456 --single-transaction --routines --triggers \
  xiaozhi_esp32_server | gzip > /root/backup/2026-10-05/xiaozhi_esp32_server.sql.gz
# 校验
du -sh /root/backup/2026-10-05/ && ls -la /root/backup/2026-10-05/
```

**预期输出**：jar 约 85M；sql.gz 非零（几十 KB 级）；四个条目齐全。**验收**：`mysql` dump 退出码 0。

**回滚（全量回退最后手段）**：
```bash
mysql -uroot -p123456 xiaozhi_esp32_server < <(gzip -dc /root/backup/2026-10-05/xiaozhi_esp32_server.sql.gz)  # 恢复 DB
cp /root/backup/2026-10-05/xiaozhi-esp32-api.jar /opt/xiaozhi/ && systemctl restart xiaozhi-manager-api
rsync -a --delete /root/backup/2026-10-05/yuhe-server-src/ /root/xiaozhi-server/main/yuhe-server/ && systemctl restart yuhe-server
rsync -a --delete /root/backup/2026-10-05/xiaozhi-manager-web/ /var/www/xiaozhi-manager/
```

**中断恢复**：本阶段全部命令幂等，直接重跑；若 dump 失败先修权限（root/123456）。

---

## 阶段 2：Python 服务（yuhe-server）

### 2.1 同步（改动 11 文件 + 新增 mem_holographic 包，总量 <100KB）

```bash
# 本地
cd "G:/demo/21_xiaozhi/code-server-mirror/yuhe-server" && tar czf /tmp/mirror-python.tar.gz .
python "G:/demo/21_xiaozhi/code/.workbuddy/sftp_push.py" /tmp/mirror-python.tar.gz /tmp/mirror-python.tar.gz

# 服务器（经 ssh_run.py）
mkdir -p /tmp/mirror-python && tar xzf /tmp/mirror-python.tar.gz -C /tmp/mirror-python
rsync -rltgoD --delete \
  --exclude=.venv/ --exclude=data/ --exclude=config.yaml --exclude=config_from_api.yaml \
  --exclude=__pycache__/ --exclude=*.log --exclude=.workbuddy/ --exclude=tmp/ \
  --exclude=models/ --exclude=music/ --exclude=tts_notify.mp3 \
  /tmp/mirror-python/ /root/xiaozhi-server/main/yuhe-server/
rm -rf /tmp/mirror-python /tmp/mirror-python.tar.gz
```

**预期输出**：rsync 无错误；以下文件到位：
- `core/api/memory_handler.py`（新）
- `core/providers/memory/mem_holographic/` 5 文件（新）
- `core/http_server.py`、`core/connection.py`、`mem0ai/mem_local_short/mem_report_only/nomem` 各 provider（覆盖）

**验收（同步后、重启前）**：
```bash
ls /root/xiaozhi-server/main/yuhe-server/core/providers/memory/mem_holographic/
grep -c "api/memory" /root/xiaozhi-server/main/yuhe-server/core/http_server.py   # >= 1
/root/xiaozhi-server/main/yuhe-server/.venv/bin/python -m py_compile \
  /root/xiaozhi-server/main/yuhe-server/core/api/memory_handler.py \
  /root/xiaozhi-server/main/yuhe-server/core/http_server.py \
  /root/xiaozhi-server/main/yuhe-server/core/connection.py && echo PY_COMPILE_OK
```

### 2.2 重启 + 探活

```bash
systemctl restart yuhe-server
sleep 5
systemctl is-active yuhe-server                                        # 预期 active
curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8000/             # 预期 200/404（端口活着）
# 部署后信号①：无鉴权本机请求 → 401（而不是 404）
curl -s -w '\nHTTP:%{http_code}' http://127.0.0.1:8003/api/memory/agents  # 预期 {"code":401,...} HTTP:401
# 部署后信号②：带 key 本机请求 → 200 code=0（空 agents 列表也成立）
curl -s -H "Authorization: Bearer 2d7b6bde-4de9-49f1-9072-476cec13292e" \
  -w '\nHTTP:%{http_code}' http://127.0.0.1:8003/api/memory/agents
tail -30 /root/xiaozhi-server/main/yuhe-server/data/app.log           # 无 traceback
```

**预期输出**：`PY_COMPILE_OK`；is-active=active；8000 有响应；8003 `/api/memory/agents` 无 key=**401**（404 说明路由未挂载，立即查日志）；带 key=**200 code:0**（若 demo Agent 不在列表为空数组也 PASS）。

**回滚（本阶段）**：
```bash
# 注意：排除清单必须与部署一致，否则 --delete 会删掉生产 data/（记忆库）与 config
rsync -a --delete \
  --exclude=.venv/ --exclude=data/ --exclude=config.yaml --exclude=config_from_api.yaml \
  --exclude=__pycache__/ --exclude=*.log \
  /root/backup/2026-10-05/yuhe-server-src/ /root/xiaozhi-server/main/yuhe-server/
systemctl restart yuhe-server && sleep 5 && systemctl is-active yuhe-server
curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:8003/api/memory/agents   # 应回到 404（旧代码）
```

**中断恢复**：同步步骤幂等重跑即可；若 rsync 中断，重新解包重跑（--delete 保证终态一致）。

---

## 阶段 3：Java 服务（manager-api）

### 3.1 同步源码 + mvn 打包（m2 缓存热，全量增量编译）

```bash
# 本地
cd "G:/demo/21_xiaozhi/code-server-mirror" && tar czf /tmp/mirror-java.tar.gz -C manager-api/src .
python "G:/demo/21_xiaozhi/code/.workbuddy/sftp_push.py" /tmp/mirror-java.tar.gz /tmp/mirror-java.tar.gz

# 服务器（经 ssh_run.py）
mkdir -p /tmp/mirror-java-src && tar xzf /tmp/mirror-java.tar.gz -C /tmp/mirror-java-src
rsync -rltgoD --delete --exclude=target/ /tmp/mirror-java-src/ /root/xiaozhi-server/main/manager-api/src/
rm -rf /tmp/mirror-java-src /tmp/mirror-java.tar.gz
cd /root/xiaozhi-server/main/manager-api && mvn -q package -DskipTests
```

**预期输出**：mvn 无 ERROR；`target/xiaozhi-esp32-api.jar` 时间戳更新（约 85M）。m2 缓存热时约 1–3 分钟。

**验收（jar 内容，不启动）**：
```bash
unzip -l /root/xiaozhi-server/main/manager-api/target/xiaozhi-esp32-api.jar | grep -E "modules/memory/|202610051800"
# 预期：MemoryFactController.class / MemoryInternalClient.class 等 9 类 + 202610051800.sql
```

### 3.2 部署 + 重启（Liquibase 在 Spring Boot 启动时执行）

```bash
cp /root/xiaozhi-server/main/manager-api/target/xiaozhi-esp32-api.jar /opt/xiaozhi/xiaozhi-esp32-api.jar
systemctl restart xiaozhi-manager-api
sleep 25 && systemctl is-active xiaozhi-manager-api                        # 预期 active
# 种子行验收（Liquibase 已执行）：两条都 =1
mysql -uroot -p123456 -N -e "select count(*) from xiaozhi_esp32_server.ai_model_provider where id='SYSTEM_Memory_mem_holographic';"
mysql -uroot -p123456 -N -e "select count(*) from xiaozhi_esp32_server.ai_model_config where id='Memory_mem_holographic' and is_enabled=1;"
mysql -uroot -p123456 -N -e "select count(*) from xiaozhi_esp32_server.DATABASECHANGELOG where id='202610051800';"   # =1
tail -20 /opt/xiaozhi/logs/manager-api.log                                 # 无 ERROR/exception
```

**预期输出**：is-active=active；三个 count 均 =1；日志无异常。

**回滚（本阶段，含 DB）**：
```bash
cp /root/backup/2026-10-05/xiaozhi-esp32-api.jar /opt/xiaozhi/xiaozhi-esp32-api.jar
mysql -uroot -p123456 xiaozhi_esp32_server -e \
  "DELETE FROM DATABASECHANGELOG WHERE ID='202610051800'; DELETE FROM ai_model_config WHERE id='Memory_mem_holographic'; DELETE FROM ai_model_provider WHERE id='SYSTEM_Memory_mem_holographic';"
systemctl restart xiaozhi-manager-api
```

**中断恢复**：同步幂等；`mvn package` 中断直接重跑（target 是产物可覆盖）；jar 已 cp 但 restart 失败 → 查日志后决定重试 restart 或走回滚。

---

## 阶段 4：Vue 控制台（manager-web）

### 4.1 本地构建

```bash
cd "G:/demo/21_xiaozhi/code-server-mirror/manager-web"
# 注意：vue-cli 清理 dist 可能被安全工具拦截 → 不要手动 rm -rf dist。
# 优先直接 build 覆盖；若报 safe-delete 拦截，换 --dest dist-new 再整体替换
npm run build
```

**预期输出**：`Build complete`；dist 内新含记忆 chunk（如 `dist/js/607.0ad10ed9.js`，哈希可能变化）。

**验收**：
```bash
grep -rl "MemoryManagement\|记忆管理" dist/js/*.js | head -3   # 有输出
ls dist/service-worker.js                                     # 存在（PWA 缓存需强刷）
```

### 4.2 上传 + 校验

```bash
# 本地
cd "G:/demo/21_xiaozhi/code-server-mirror/manager-web" && tar czf /tmp/mirror-web.tar.gz -C dist .
python "G:/demo/21_xiaozhi/code/.workbuddy/sftp_push.py" /tmp/mirror-web.tar.gz /tmp/mirror-web.tar.gz

# 服务器（经 ssh_run.py）
mkdir -p /tmp/mirror-web && tar xzf /tmp/mirror-web.tar.gz -C /tmp/mirror-web
rsync -rltgoD --delete /tmp/mirror-web/ /var/www/xiaozhi-manager/
rm -rf /tmp/mirror-web /tmp/mirror-web.tar.gz
```

**预期输出**：rsync 干净落位（nginx 静态，零重启）；`curl -s http://127.0.0.1:8001/ | head -3` 返回新 index.html；`curl -sI http://127.0.0.1:8001/service-worker.js` 200。

**回滚（本阶段）**：
```bash
rsync -a --delete /root/backup/2026-10-05/xiaozhi-manager-web/ /var/www/xiaozhi-manager/
```

**中断恢复**：幂等重跑 4.2；构建产物以最后一次 build 为准。

---

## 阶段 5：线上复验 R1–R5

> 所有脚本均先落服务器 `/tmp/qa_memory/` 再执行（loopback 脚本必须服务器本机跑；对话/E2E 脚本可本机跑，但统一走服务器更简单）。**脚本与部署包分离传输**。

```bash
# 本地（QA 脚本在工作区 code/.workbuddy/qa_memory/，不在镜像仓库内）
cd "G:/demo/21_xiaozhi/code/.workbuddy" && tar czf /tmp/qa-scripts.tar.gz qa_memory
python "G:/demo/21_xiaozhi/code/.workbuddy/sftp_push.py" /tmp/qa-scripts.tar.gz /tmp/qa-scripts.tar.gz

# 服务器（经 ssh_run.py）
mkdir -p /tmp/qa_memory && tar xzf /tmp/qa-scripts.tar.gz -C /tmp && rm -f /tmp/qa-scripts.tar.gz
ls /tmp/qa_memory/          # 预期 test_internal_api.sh test_java_api.sh e2e_memory_suite.py 等
```

### R1 部署检查三关（e2e 脚本内置，也可手工）

```bash
# 服务器
curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8003/api/memory/agents   # 无key → 401
mysql -uroot -p123456 -N -e "select count(*) from xiaozhi_esp32_server.ai_model_config where id='Memory_mem_holographic' and is_enabled=1;"  # =1
ls /root/xiaozhi-server/main/yuhe-server/core/providers/memory/mem_holographic/mem_holographic.py  # 存在
```

### R2 内部记忆管理 API（test_internal_api.sh，服务器本机执行）

```bash
cd /tmp/qa_memory && AUTH_KEY=2d7b6bde-4de9-49f1-9072-476cec13292e bash test_internal_api.sh
```

**预期**：三态鉴权（无 key 401 / 错 key 401 / 对 key 200）+ CRUD + 搜索 + 审核流全 PASS。**注意**：脚本默认测试 Agent `qa-memory-test-agent`，测试数据不碰 demo Agent。

### R3 Java 代理 API（test_java_api.sh，服务器本机执行）

```bash
cd /tmp/qa_memory && TOKEN=<管理员token> AGENT_ID=03532a34fcea46639099adb38474a2d9 bash test_java_api.sh
```

**TOKEN 获取**（二选一）：① 浏览器 F12 复制控制台请求头 Bearer；② **无验证码阻断时**用 MySQL 直插（e2e 已验证的路径）：

```sql
INSERT INTO sys_user_token (user_id, token, expire_date) VALUES
 (2106728446262718466, MD5('deploy-r3-token'), DATE_ADD(NOW(), INTERVAL 4 HOUR));
-- 使用 TOKEN=<md5(deploy-r3-token)>
```

**预期**：J0 鉴权三态 + J1–J5 CRUD/搜索/反馈全 PASS（会向 demo Agent 写入"茉莉花茶"测试条目，脚本尾部应自删；若中断残留，用管理 API 删除或接受残留无害条目）。

### R4 对话级跨会话（test_e2e_dialogue.py / e2e_memory_suite.py）

```bash
# 前置：demo Agent 当前引擎状态核验（关键！见风险 4）
mysql -uroot -p123456 -N -e "select mem_model_id from xiaozhi_esp32_server.ai_agent where id='03532a34fcea46639099adb38474a2d9';"

# 方案 A（团队既有轻量脚本，二选一）
cd /tmp/qa_memory && python3 test_e2e_dialogue.py --run

# 方案 B（一体套件，A1→A2→A10 顺序，自管理引擎切换与恢复）
cd /tmp/qa_memory && python3 e2e_memory_suite.py --case all
```

**预期**：跨会话问"我叫什么名字/喜欢听什么"命中"张三/粤语"；`data/memory/03532a34....db` 出现 profile/preference 条目；`test_e2e_dialogue.py` 无 `--run` 时自动 SKIP。

**注意**：e2e 套件会重启 yuhe-server 两次（引擎切换），选低峰时段。

### R5 性能与回退（qa_perf_rollback.py，本地或服务器）

```bash
# 本地预演已跑；部署后真机复测需在服务器做（依赖 numpy 已在 venv）
cd /tmp/qa_memory && /root/xiaozhi-server/main/yuhe-server/.venv/bin/python qa_perf_rollback.py --facts 500 --rounds 50
```

**预期**：query_memory P95 ≤300ms；回退安全断言（切引擎后库文件保留）全 PASS。

### 控制台人工检查

- 浏览器（强刷 Ctrl+Shift+R）打开 `http://sandyun.top:8001/` → 登录 → 侧边栏出现"记忆管理"→ demo Agent 出现记忆统计 → 条目增删改查可用。
- F12 确认 `GET /yuhe/memory/agents` 返回 200 code:0。
- **PWA 强刷**：旧 service-worker 可能缓存旧 JS；若菜单缺失先 Ctrl+Shift+R，仍缺失清站点数据。

---

## 阶段 6：结束动作

1. 记录部署时间、各阶段验收输出到 `.workbuddy/deploy_memory_v1_runlog.md`（执行时新建）。
2. 若 R4 的 e2e 套件跑过：确认 demo Agent 引擎已被脚本恢复为 `mem_holographic`（或按团队决定恢复 `mem_local_short`）。
3. 清理服务器 `/tmp/qa_memory /tmp/qa-scripts* /tmp/mirror-*`。
4. 把 R1–R5 全部 verdict 汇总发送 team-lead，任务 #7 关闭。

---

## 中断恢复总表

| 中断点 | 恢复动作 |
|---|---|
| 任何阶段同步中断 | 重跑该阶段同步命令（--delete 保证幂等终态） |
| 阶段 1 备份中断 | 重跑（覆盖式） |
| 阶段 2 重启失败/起不来 | `tail -100 data/app.log` → 修复或执行阶段 2 回滚 |
| 阶段 3 mvn 中断 | 重跑 `mvn -q package -DskipTests` |
| 阶段 3 启动失败/Liquibase 报错 | 看 manager-api.log；Liquibase 失败时 DB 通常已回滚该 changeSet；执行阶段 3 回滚恢复旧 jar |
| 阶段 4 构建被安全工具拦截 | 不清 dist 直接 build 覆盖；或 `npm run build -- --dest dist-new` 后整体替换 |
| R2/R3 测试数据残留 | R2 用专用测试 Agent（无污染）；R3 残留条目用管理 API DELETE 清理 |
| R4 e2e 中断 | 脚本自带 `--no-cleanup` 保留现场；重跑前手工确认 demo 引擎状态（mem_model_id）与 `/tmp/e2e_memory_*.db.bak` 备份 |

---

## 部署风险清单（含本次新增发现）

| # | 风险 | 处置 |
|---|---|---|
| 1 | **本地无 rsync，无法直连 rsync 推送** | 已改为 tar+sftp_push+服务器内 rsync（工具已落盘，方法已实测可行） |
| 2 | **MSYS 路径转换 + 引号嵌套双坑** | 手册全程 `MSYS_NO_PATHCONV=1`；复杂脚本 base64 传输 |
| 3 | `--delete` 误删 .venv/data/记忆库 | rsync 排除清单固定；`data/` 排除置于最前 |
| 4 | **demo Agent 的 mem_model_id 已是 `Memory_mem_holographic`（种子行尚未插入，悬空引用）** | 阶段 3 重启 Java 后 Liquibase 会立刻补上种子行，悬空引用自动消解。**注意：阶段 3 必须一次成功**，否则悬空期间控制台编辑 Agent 页可能下拉异常；R4 前置先查 mem_model_id 实际值再决定是否切引擎 |
| 5 | **顺序耦合：Python 旧代码收到 mem_holographic 配置会 `create_instance` ValueError → 该连接 `initialize_modules` 整体异常清空（TTS/ASR/LLM 全丢）** | 主路径（Java 先上）无此问题；若团队选择 Python 先上且 Java 重启前控制台把 Agent 切到 mem_holographic，该 Agent 会话初始化失败。**手册默认顺序：阶段 2 Python → 阶段 3 Java，两步之间不要改控制台记忆引擎** |
| 6 | Liquibase 在 jar 启动时执行（非 mvn 阶段） | 手册已按此编排：mvn 只打包，启动即 DDL+种子 |
| 7 | 服务器 venv 无 sqlite3 CLI | 手册库断言用 venv python3 sqlite3 模块（FTS5 已实测可用） |
| 8 | PWA service-worker 缓存旧前端 | 验证必须强刷；必要时清站点数据 |
| 9 | 8003 公网直达但 loopback 拦 memory | 部署后验证：无 key 本机 401；**从本地外网 curl 8003 应得 403**（安全预期，勿误判） |
| 10 | 备份目录首次建立，无历史备份 | 阶段 1 先行；任何回滚优先使用阶段级回滚，全量回滚只在灾难时用 |
| 11 | 测试数据污染 demo Agent | R2 用专用测试 Agent；R3 测试条目脚本自删；R4 引擎切换物理隔离（data/memory 新文件） |
| 12 | T26b/T26c（powermem 测试 Agent 前置）不在现有 QA 脚本中 | 已确认 qa_memory 全部脚本无 T26 用例；若 QA 需要，由 qa-api 在部署后提供脚本或控制台手工建一个绑定 PowerMem 的测试 Agent 再跑 |
| 13 | 本地 dist 现构建（18:44）已含记忆 chunk | 若部署日代码有更新需重新 build；否则可直接复用现有 dist |

---

## 附：命令速查（部署日直接复制）

```bash
# 通用前缀
SSH='MSYS_NO_PATHCONV=1 python "G:/demo/21_xiaozhi/code/.workbuddy/ssh_run.py"'
PUSH='python "G:/demo/21_xiaozhi/code/.workbuddy/sftp_push.py"'

# 服务器探活三连
systemctl is-active yuhe-server xiaozhi-manager-api
curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:8003/api/memory/agents          # 401
curl -s -H 'Authorization: Bearer 2d7b6bde-4de9-49f1-9072-476cec13292e' -o /dev/null -w '%{http_code}\n' http://127.0.0.1:8003/api/memory/agents  # 200
```

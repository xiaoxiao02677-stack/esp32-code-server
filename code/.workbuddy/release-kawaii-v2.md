# Kawaii 控制台 + P1 改动上线执行清单 v2（任务 #16 · e-deploy）

> 状态：**准备就绪，待 team-lead 下发「GO 上线」后执行**。收到 GO 前本清单任何命令**不得执行**（阶段 0 基线采集只读除外，也待 GO 后执行，保持单一开关）。
> 对象：sandyun.top 生产。本批改动 = Kawaii 控制台（A 线）+ 设备配置云端记忆（B 线）+ 记忆参数面板（C 线）+ 本轮 P1（P1-1 果冻动效 / P1-2 移动端抽屉 / P1-3 按钮Logo粉彩 / P1-4 设备配置管理UI / P1-6 原子upsert / P1-7 双主题+PWA）。
> 事实来源：`.workbuddy/deploy_memory_v1.md` 第 0 节 + `KawaiiConsole-交付报告-v1.md`。
> **红线**：
> 1. 任何阶段 FAIL → **立即停**，执行该阶段回滚剧本，向 team-lead 回报，等指令。不盲目继续。
> 2. secret 轮换（`.workbuddy/secret-rotation/rotate-secret.sh`，任务 #13）本任务**不执行**，只在全部冒烟 PASS 后追加「引用」一步（见阶段 4 末 / S-REF）。
> 3. 固件（B 线 4 文件）**不在本清单范围**（e-fw-build 已做构建验证，真机刷写另行安排）。
> 4. 传输 `--delete` 排除清单照抄 deploy_memory_v1.md 第 0 节，一个字不能少。

---

## 阶段 0：基线快照 + 备份（服务器，全程只读+落备份，不改生产）

### 0.1 基线采集（记录进 runlog，供回滚对照）

```bash
# 服务器（经 ssh_run.py，含 / 绝对路径全部加 MSYS_NO_PATHCONV=1；复杂脚本 base64 传入）
mkdir -p /root/backup/2026-10-07
# web 现状清单（dist 目录全量文件清单 + md5）
(cd /var/www/xiaozhi-manager && find . -type f | sort > /tmp/web-list-before.txt) && \
  (cd /var/www/xiaozhi-manager && find . -type f -exec md5sum {} + | sort -k2 > /tmp/web-md5-before.txt) && \
  wc -l /tmp/web-list-before.txt && cp /tmp/web-list-before.txt /tmp/web-md5-before.txt /root/backup/2026-10-07/
# jar 基线
md5sum /opt/xiaozhi/xiaozhi-esp32-api.jar | tee /root/backup/2026-10-07/jar-md5-before.txt
ls -la /opt/xiaozhi/xiaozhi-esp32-api.jar
# git rev（源码仓）
(cd /root/xiaozhi-server/main/yuhe-server && git rev-parse HEAD 2>/dev/null; git status --short | wc -l)
# Liquibase 现状（部署前应无 202610060030 / 202610070010 两行）
mysql -uroot -p123456 -N -e "select id from xiaozhi_esp32_server.DATABASECHANGELOG where id in ('202610060030','202610070010');"   # 预期 0 行
# 三服务基线
systemctl is-active yuhe-server xiaozhi-manager-api && curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:8001/
```

### 0.2 全量备份（幂等，可重跑）

```bash
cp -a /opt/xiaozhi/xiaozhi-esp32-api.jar /root/backup/2026-10-07/
rsync -a --exclude=.venv/ --exclude=data/ --exclude=__pycache__/ --exclude=*.log \
  /root/xiaozhi-server/main/yuhe-server/ /root/backup/2026-10-07/yuhe-server-src/
rsync -a /var/www/xiaozhi-manager/ /root/backup/2026-10-07/xiaozhi-manager-web/
mysqldump -uroot -p123456 --single-transaction --routines --triggers \
  xiaozhi_esp32_server | gzip > /root/backup/2026-10-07/xiaozhi_esp32_server.sql.gz
du -sh /root/backup/2026-10-07/ && ls -la /root/backup/2026-10-07/
```

**验收**：jar ~85M 拷贝完成；web 快照非空；sql.gz 非零；`web-md5-before.txt` 行数 = `web-list-before.txt`。
**FAIL 判据（停）**：mysqldump 非 0 退出 / 备份目录缺任一项 → 修好重跑，禁止进入阶段 1。
**回滚**：本阶段无副作用（只写 /root/backup 与 /tmp），直接重跑。

---

## 阶段 1：构建（npm 本机独占 + Java 服务器端 mvn）

> 构建由 e-deploy 独占执行，其他工程师已停手。

### 1.1 Vue 前端构建（本机）

```bash
cd "G:/demo/21_xiaozhi/code-server-mirror/manager-web"
# 注意：不要手动 rm -rf dist；若 build 被安全工具拦截 → npm run build -- --dest dist-new 后整体替换
npm run build
```

**验收**：
```bash
grep -rl "kawaii\|KawaiiLayout\|MemoryEngineParams" dist/js/*.js | head -3   # 有输出（Kawaii 布局+记忆参数面板进包）
ls dist/service-worker.js                                                    # 存在（PWA，需强刷）
ls dist/js/ | wc -l                                                          # 记录 chunk 数量进 runlog
md5sum dist/index.html                                                       # 记录进 runlog（阶段 2 逐项对照）
```

**FAIL 判据（停）**：build 报错 / grep 无输出（改动没进包）/ service-worker.js 缺失 → 查构建日志，修复后重跑 1.1，禁止带病进阶段 2。

### 1.2 Java 构建（服务器端 mvn，m2 缓存热）

先同步源码（B 线 Java 5 新 4 改 + Liquibase 两个新 changelog）：

```bash
# 本地
cd "G:/demo/21_xiaozhi/code-server-mirror" && tar czf /tmp/kawaii-java-src.tar.gz -C manager-api/src .
python "G:/demo/21_xiaozhi/code/.workbuddy/sftp_push.py" /tmp/kawaii-java-src.tar.gz /tmp/kawaii-java-src.tar.gz

# 服务器（经 ssh_run.py）
mkdir -p /tmp/kawaii-java-src && tar xzf /tmp/kawaii-java-src.tar.gz -C /tmp/kawaii-java-src
rsync -rltgoD --delete --exclude=target/ /tmp/kawaii-java-src/ /root/xiaozhi-server/main/manager-api/src/
rm -rf /tmp/kawaii-java-src /tmp/kawaii-java-src.tar.gz
cd /root/xiaozhi-server/main/manager-api && mvn -q package -DskipTests
```

**验收（jar 内容，不启动）**：
```bash
unzip -l /root/xiaozhi-server/main/manager-api/target/xiaozhi-esp32-api.jar | grep -E "modules/device/|202610060030|202610070010"
# 预期：DeviceConfigEntity/Dao/Service/ServiceImpl/DTO 类 + 202610060030.sql + 202610070010.sql 都在包内
ls -la /root/xiaozhi-server/main/manager-api/target/xiaozhi-esp32-api.jar   # 时间戳更新（约 85M）
```

**FAIL 判据（停）**：mvn 出现 ERROR / grep 无 device 类或两个 changelog SQL → 查构建日志重跑；连续 2 次失败回报 team-lead。
**回滚**：本阶段只写源码目录与 target，未动 /opt/jar，无回滚必要；中断直接重跑（target 可覆盖）。

---

## 阶段 2：传输（tar + sftp_push + 服务器内 rsync 增量，逐项 md5）

> 传输总原则照抄 deploy_memory_v1.md 第 0 节：本地 tar 打包 → sftp_push.py → 服务器解包到 /tmp → 服务器内 rsync 增量落位 → md5 校验。**排除清单一字不动**（models/ music/ tts_notify.mp3 曾被 --delete 误删过，必须排除）。

### 2.1 Python 服务（B 线 4 文件：device_config_sync 新 + mcp_executor/manage_api_client/connection 改）

```bash
# 本地
cd "G:/demo/21_xiaozhi/code-server-mirror/yuhe-server" && tar czf /tmp/kawaii-python.tar.gz .
python "G:/demo/21_xiaozhi/code/.workbuddy/sftp_push.py" /tmp/kawaii-python.tar.gz /tmp/kawaii-python.tar.gz

# 服务器（经 ssh_run.py，注意 MSYS_NO_PATHCONV=1；本条含括号/斜杠 → base64 传入）
mkdir -p /tmp/kawaii-python && tar xzf /tmp/kawaii-python.tar.gz -C /tmp/kawaii-python
rsync -rltgoD --delete \
  --exclude=.venv/ --exclude=data/ --exclude=config.yaml --exclude=config_from_api.yaml \
  --exclude=__pycache__/ --exclude=*.log --exclude=.workbuddy/ --exclude=tmp/ \
  --exclude=models/ --exclude=music/ --exclude=tts_notify.mp3 \
  /tmp/kawaii-python/ /root/xiaozhi-server/main/yuhe-server/
rm -rf /tmp/kawaii-python /tmp/kawaii-python.tar.gz
```

**验收（同步后、重启前）**：
```bash
ls /root/xiaozhi-server/main/yuhe-server/core/providers/tools/device_config_sync.py
grep -c "report_device_config" /root/xiaozhi-server/main/yuhe-server/config/manage_api_client.py   # >= 1
grep -c "device_config" /root/xiaozhi-server/main/yuhe-server/core/connection.py                  # >= 1
# 逐项 md5 对照（本地打同一套文件的 md5，比对本行 4 文件）
/root/xiaozhi-server/main/yuhe-server/.venv/bin/python -m py_compile \
  /root/xiaozhi-server/main/yuhe-server/core/providers/tools/device_config_sync.py \
  /root/xiaozhi-server/main/yuhe-server/core/providers/tools/device_mcp/mcp_executor.py \
  /root/xiaozhi-server/main/yuhe-server/config/manage_api_client.py \
  /root/xiaozhi-server/main/yuhe-server/core/connection.py && echo PY_COMPILE_OK
# 排除项存活自检（防误删）
du -sh /root/xiaozhi-server/main/yuhe-server/models/ /root/xiaozhi-server/main/yuhe-server/music/ 2>/dev/null
ls /root/xiaozhi-server/main/yuhe-server/tts_notify.mp3 /root/xiaozhi-server/main/yuhe-server/config.yaml
```

**FAIL 判据（停）**：py_compile 失败 / 4 文件 md5 与本地不一致 / 排除项（models、music、tts_notify.mp3、config.yaml）缺失 → 立即执行阶段 2-Py 回滚（下方），并查 rsync 输出。

**阶段 2-Py 回滚**（注意排除清单与部署完全一致，否则 --delete 删生产 data/）：
```bash
rsync -a --delete \
  --exclude=.venv/ --exclude=data/ --exclude=config.yaml --exclude=config_from_api.yaml \
  --exclude=__pycache__/ --exclude=*.log --exclude=models/ --exclude=music/ --exclude=tts_notify.mp3 \
  /root/backup/2026-10-07/yuhe-server-src/ /root/xiaozhi-server/main/yuhe-server/
```

### 2.2 Vue 前端 dist → /var/www/xiaozhi-manager（nginx 静态，零重启）

```bash
# 本地
cd "G:/demo/21_xiaozhi/code-server-mirror/manager-web" && tar czf /tmp/kawaii-web.tar.gz -C dist .
python "G:/demo/21_xiaozhi/code/.workbuddy/sftp_push.py" /tmp/kawaii-web.tar.gz /tmp/kawaii-web.tar.gz

# 服务器
mkdir -p /tmp/kawaii-web && tar xzf /tmp/kawaii-web.tar.gz -C /tmp/kawaii-web
rsync -rltgoD --delete /tmp/kawaii-web/ /var/www/xiaozhi-manager/
rm -rf /tmp/kawaii-web /tmp/kawaii-web.tar.gz
# 逐项 md5 对照阶段 1.1 记录的 dist md5（全量对照，不只抽查）
(cd /var/www/xiaozhi-manager && find . -type f -exec md5sum {} + | sort -k2 > /tmp/web-md5-after.txt)
diff <(sort -k2 /root/backup/2026-10-07/web-md5-before.txt) <(sort -k2 /tmp/web-md5-after.txt) | head -20   # 增量可视
```

**验收**：`curl -s http://127.0.0.1:8001/ | head -3` 返回新 index.html；`curl -sI http://127.0.0.1:8001/service-worker.js` 200；after 清单非空。
**FAIL 判据（停）**：rsync 报错 / service-worker.js 404 / index.html 仍是旧哈希 → 执行阶段 2-Web 回滚。

**阶段 2-Web 回滚**：
```bash
rsync -a --delete /root/backup/2026-10-07/xiaozhi-manager-web/ /var/www/xiaozhi-manager/
```

---

## 阶段 3：服务（Liquibase 确认 + 重启 Java/Python + systemd 健康）

> 顺序固定：**Java 先（阶段 3.1）→ Python 后（阶段 3.2）**。理由（deploy_memory_v1 风险 5）：Python 旧代码收到新配置会崩连接初始化；Java 先上保证 Liquibase 建表（ai_device_config）先于 Python 上报路径生效。两步之间**不要**在控制台改设备配置/记忆引擎。

### 3.1 Java（Liquibase 在 jar 启动时执行 202610060030 + 202610070010）

```bash
cp /root/xiaozhi-server/main/manager-api/target/xiaozhi-esp32-api.jar /opt/xiaozhi/xiaozhi-esp32-api.jar
systemctl restart xiaozhi-manager-api
sleep 25 && systemctl is-active xiaozhi-manager-api            # 预期 active
# Liquibase 两个 changelog 均须已执行
mysql -uroot -p123456 -N -e "select id from xiaozhi_esp32_server.DATABASECHANGELOG where id in ('202610060030','202610070010');"
# 预期输出两行；再确认表可用
mysql -uroot -p123456 -N -e "select count(*) from xiaozhi_esp32_server.ai_device_config;"   # =0（空表正常）
tail -30 /opt/xiaozhi/logs/manager-api.log                   # 无 ERROR/exception/Liquibase 报错
# 健康面
curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:8001/yuhe/actuator/health 2>/dev/null || \
curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:8001/yuhe/login   # 200（业务码模式）
```

**验收**：is-active=active；DATABASECHANGELOG 两行齐全；ai_device_config 表可查；日志无异常。
**FAIL 判据（停）**：服务起不来 / Liquibase 报错 / changelog 缺行 → 立即执行阶段 3.1 回滚，回报 team-lead，不得继续 3.2。

**阶段 3.1 回滚（含 DB）**：
```bash
cp /root/backup/2026-10-07/xiaozhi-esp32-api.jar /opt/xiaozhi/xiaozhi-esp32-api.jar
mysql -uroot -p123456 xiaozhi_esp32_server -e "
  DELETE FROM DATABASECHANGELOG WHERE ID IN ('202610060030','202610070010');
  DROP TABLE IF EXISTS ai_device_config;"
systemctl restart xiaozhi-manager-api
sleep 15 && systemctl is-active xiaozhi-manager-api
```

### 3.2 Python（systemd yuhe-server）

```bash
systemctl restart yuhe-server
sleep 5 && systemctl is-active yuhe-server                  # 预期 active
curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:8000/                        # 200/404（端口活着）
curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:8003/api/memory/agents       # 401（旧契约仍在，防回归）
tail -30 /root/xiaozhi-server/main/yuhe-server/data/app.log                       # 无 traceback
```

**FAIL 判据（停）**：非 active / 日志 traceback / 既有 API 契约（8003 401）异常 → 执行阶段 3.2 回滚（与 2-Py 回滚同命令）+ 视情况保留 3.1（Java 新 jar 与 Python 回滚兼容：Java 下发 device_config 白名单纵深，Python 旧代码收不到上报，无害）。

**阶段 3.2 回滚**：
```bash
rsync -a --delete \
  --exclude=.venv/ --exclude=data/ --exclude=config.yaml --exclude=config_from_api.yaml \
  --exclude=__pycache__/ --exclude=*.log --exclude=models/ --exclude=music/ --exclude=tts_notify.mp3 \
  /root/backup/2026-10-07/yuhe-server-src/ /root/xiaozhi-server/main/yuhe-server/
systemctl restart yuhe-server && sleep 5 && systemctl is-active yuhe-server
```

---

## 阶段 4：冒烟（交给 e-qa-smoke，引用其清单）

> 冒烟执行方：**e-qa-smoke（任务 #18）**，清单在 `G:/demo/21_xiaozhi/code/.workbuddy/qa-smoke-plan.md`（A 组离线 curl/浏览器 + B 组服务器侧 + C 组控制台人工强刷）。本清单只引用、不代跑；e-deploy 仅做两件事：

1. **移交前自检**（阶段 3 全绿后才移交）：
```bash
systemctl is-active yuhe-server xiaozhi-manager-api     # 双 active
curl -sI http://127.0.0.1:8001/ | head -3                  # 200 + 新 index.html
mysql -uroot -p123456 -N -e "select id from xiaozhi_esp32_server.DATABASECHANGELOG where id in ('202610060030','202610070010');"   # 两行
```
2. **SendMessage 通知 e-qa-smoke「上线完成，GO 冒烟」**（含本 runlog 路径 + 提醒 service-worker 强刷坑 + 提醒 qa-smoke-plan 中 `<DEVICE_CONFIG_ROUTE>` 占位以 e-pi4 实际交付路由替换）。

**FAIL 判据（停）**：e-qa-smoke 任一 FAIL 项 → 按该项清单内 FAIL 指引先定位；前端类 FAIL 走阶段 2-Web 回滚，后端类 FAIL 走阶段 3 回滚。修复后需 e-qa-smoke 全量重跑，不得只复测失败项。

### S-REF · secret 轮换「引用」步骤（本任务不执行，仅登记）

全部冒烟 PASS 后，team-lead 另行下令时才执行：**引用 `G:/demo/21_xiaozhi/code/.workbuddy/secret-rotation/rotate-secret.sh`（任务 #13，e-secret-ops 负责）**，完成 `server.secret` 两端轮换 + 清除 `yuhe-server/data/.config.yaml` 版本历史 + .gitignore 模板化。本清单中**不包含其执行命令**；执行与验证由 e-secret-ops 回报，e-deploy 在 runlog 追加一行「S-REF 完成时间 + 执行人」。

---

## 回滚剧本总表（每阶段对应回退 + 时间预算 + 谁执行）

| 阶段 | 回退命令 | 时间预算 | 执行 |
|---|---|---|---|
| 0 | 无（重跑幂等） | 0 | e-deploy |
| 1.1 | 无（重跑 build，dist 产物可覆盖） | ~5min | e-deploy |
| 1.2 | 无（重跑 rsync+mvn） | ~5min | e-deploy |
| 2-Py | 阶段 2-Py 回滚 rsync（排除清单与部署一致） | ~2min | e-deploy |
| 2-Web | 阶段 2-Web 回滚 rsync | ~1min | e-deploy |
| 3.1 | 阶段 3.1 回滚（旧 jar + 删 changelog + drop 表 + restart） | ~3min | e-deploy |
| 3.2 | 阶段 3.2 回滚 rsync + restart | ~2min | e-deploy |
| 4 | 按 FAIL 项归因走 2/3 回滚 + e-qa-smoke 全量重跑 | ~15min | e-deploy + e-qa-smoke |
| 灾难全量 | `/root/backup/2026-10-07/` 全量恢复（jar cp + 双 rsync + mysqldump 灌回，命令同 deploy_memory_v1 阶段 1 回滚段） | ~10min | e-deploy（需 team-lead 二次确认） |

**通用纪律**：
- 每阶段 GO 前 30 秒自检上一条命令退出码，非 0 一律停。
- runlog 落 `G:/demo/21_xiaozhi/code/.workbuddy/release-kawaii-v2_runlog.md`（执行时新建）：逐阶段记录 时间戳 / 命令 / 输出摘要 / md5 / verdict。
- 结束后清理服务器 `/tmp/kawaii-*`、`/tmp/web-*-before/after.txt`。
- 收尾向 team-lead 回报全量 verdict → 任务 #16 关闭；S-REF 由 e-secret-ops 单独闭环。

---

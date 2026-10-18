# Kawaii 控制台线上冒烟清单（任务 #18 · e-qa-smoke）

> 状态：**准备完成，待 team-lead 下发「GO + 上线完成」后执行**。
> 对象：sandyun.top:8001（nginx 8001，静态根 /var/www/xiaozhi-manager，/yuhe/ 反代 127.0.0.1:8002 Java manager-api）。
> 环境事实来源：`.workbuddy/deploy_memory_v1.md` 第 0 节 + `deploy_memory_v1_runlog.md`。
> 关键坑（执行时逐条对照）：
> 1. **MSYS 坑**：Git Bash 会把以 `/` 开头的参数转成 `C:/...`。所有含 `/root/...`、`/var/...`、`/tmp/...` 绝对路径的 ssh_run.py 命令**必须前缀 `MSYS_NO_PATHCONV=1`**。
> 2. **引号坑**：ssh_run.py 参数含括号/内嵌引号时 bash 先解析崩溃。**复杂脚本一律 base64 传入**：`echo <B64> | base64 -d > /tmp/x.sh && bash /tmp/x.sh`。
> 3. **service-worker**：前端有 PWA service-worker（dist 含 service-worker.js），旧 SW 会缓存旧 JS。**所有浏览器验证必须强刷（Ctrl+Shift+R），必要时 DevTools → Application → 注销 Service Worker + 清除站点数据**；截图留证前先完成强刷。
> 4. **manager-api 是 HTTP 200 + 业务码模式**（全局异常处理不抛 5xx）：判"登录不 500"要看 HTTP 码 + 业务码字段，不能只看 HTTP 4xx。
> 5. MySQL：`mysql -uroot -p123456 xiaozhi_esp32_server`；changelog 断言走 DATABASECHANGELOG 表。
> 6. 部署工具：`python G:/demo/21_xiaozhi/code/.workbuddy/ssh_run.py "CMD" ["CMD2"...]`；回滚物料在服务器 /root/backup/ 批次当日目录（jar + web 快照 + mysqldump）。

---

## A. 可离线跑项（本机 curl / 浏览器，不需 ssh）

### A1 站点可达 200
```bash
curl -sI http://sandyun.top:8001/ | head -5
```
- **PASS**：HTTP 200，`Content-Type: text/html`。
- **FAIL**：4xx/5xx/超时/非 HTML → 截图 A1-fail（curl 输出全文）。

### A2 关键路由 SPA fallback（22 页 sample 抽 5 + 1 个不存在页）
抽样 5 页：`/home`、`/device-management`、`/model-config`、`/memory-management`、`/login`。
```bash
for p in /home /device-management /model-config /memory-management /login /definitely-not-exist-page; do
  code=$(curl -s -o /tmp/spa_$(echo $p | tr -d /).out -w '%{http_code}' "http://sandyun.top:8001$p")
  echo "$p -> $code $(head -c 60 /tmp/spa_$(echo $p | tr -d /).out | tr -d '\n' | head -c 40)"
done
```
- **PASS**：6 个 URL 全部 200 且响应体均为 index.html（SPA fallback 生效；不存在页也回 index.html，由前端路由守卫处理）。
- **FAIL**：任一 404/5xx，或响应体不是 index.html（说明 nginx location 规则被改）。

### A3 新 P1 路由（设备配置管理页）可达
> 路由已确认（e-pi4-config-ui 交付 + e-deploy 上线）：`/device-config-management`（name: DeviceConfigManagement）。
```bash
curl -s -o /dev/null -w '%{http_code}' http://sandyun.top:8001/device-config-management
```
- **PASS**：200（SPA fallback）；浏览器强刷后侧边栏出现新菜单项、页面渲染无白屏。
- **FAIL**：浏览器白屏/菜单缺失 → 先执行"SW 强刷步骤"再复测；仍失败截图 A3-fail。

### A4 login 流程不 500（经 nginx 反代 /yuhe/）
```bash
# 公开端点探活
curl -s -o /dev/null -w 'pub-config %{http_code}\n' http://sandyun.top:8001/yuhe/user/pub-config
curl -s -o /dev/null -w 'captcha %{http_code}\n' "http://sandyun.top:8001/yuhe/user/captcha?uuid=smoke"
# 空 body login：允许业务报错，不允许 500
curl -s -w '\nlogin %{http_code}\n' -X POST -H 'Content-Type: application/json' -d '{}' http://sandyun.top:8001/yuhe/user/login
```
- **PASS**：三条 HTTP 均 200（login 空 body 时业务码非 0 属预期）；captcha 返回图片（Content-Type image/*）。
- **FAIL**：任一 5xx / 连接拒绝 / 反代 404（`/yuhe/` 反代断链）→ 截图 A4-fail + 直接跳 B 段在部署机定位。

### A5 JS chunk 加载无 404（对照 dist 构建产物清单）
```bash
# 1) 本地生成产物清单（以部署批次最终 dist 为准）
cd G:/demo/21_xiaozhi/code-server-mirror/manager-web
ls dist/js/*.js dist/css/*.css > /tmp/dist-manifest.txt
ls dist/js/*.js dist/css/*.css dist/service-worker.js | wc -l
# 2) 逐一 curl 验证 200（本机执行）
while read f; do
  code=$(curl -s -o /dev/null -w '%{http_code}' "http://sandyun.top:8001/$f")
  [ "$code" != "200" ] && echo "MISSING:$f -> $code"
done < /tmp/dist-manifest.txt
echo CHUNK_CHECK_DONE
# 3) service-worker 本体
curl -sI http://sandyun.top:8001/service-worker.js | head -3
```
- **PASS**：全部 200，`CHUNK_CHECK_DONE` 前无 MISSING 行；service-worker.js 200。
- **FAIL**：出现 MISSING 行 → 说明线上 dist 与构建产物清单不一致（漏传/多传），截图 A5-fail + 记录缺失清单。

### A6 service-worker 版本更新强刷说明（验证 SOP）
1. 浏览器打开 `http://sandyun.top:8001/` → F12 → Application → Service Workers：确认已注册且 active 的是**新构建的** service-worker.js（对比 content-length/哈希或更新后的注册脚本）。
2. 若仍为旧版：点 Unregister → 清站点数据（Application → Storage → Clear site data）→ Ctrl+Shift+R。
3. 复验：Network 面板刷新一次，确认加载的 chunk 文件名/哈希属于**新 dist 清单**（A5 的清单），无对旧哈希文件的 404 请求。
4. **留证截图 S6**：Service Workers 面板（active 状态）+ Network 首屏 chunk 请求列表。
- **PASS**：强刷后 chunk 全命中新清单；**FAIL**：出现旧哈希 404 或 SW 无法更新 → 记录并截图。

---

## B. 需部署机执行项（ssh_run.py）

> 前缀约定：`SSH='MSYS_NO_PATHCONV=1 python "G:/demo/21_xiaozhi/code/.workbuddy/ssh_run.py"'`
> 单条简单命令直接 `python ssh_run.py "CMD"`；含括号/内嵌引号/多行脚本 → 本地 base64 编码后走 `echo <B64> | base64 -d > /tmp/qa_smoke_x.sh && bash /tmp/qa_smoke_x.sh`。

### B1 nginx 日志抽样（error + access 4xx/5xx）
```bash
python "G:/demo/21_xiaozhi/code/.workbuddy/ssh_run.py" \
  "tail -50 /var/log/nginx/error.log" \
  "awk '\$9 ~ /^5|/ {print}' /var/log/nginx/access.log | tail -30" \
  "grep -c ' 404 ' /var/log/nginx/access.log || true"
```
- 注意 awk 里的 `$9` 含 shell 特殊字符，**必须 base64 传输**（坑 2），上面命令仅示意；执行时用 base64 包装版。
- **PASS**：error.log 尾部无新增 worker 报错（部署时刻之后的行）；access.log 4xx/5xx 抽样仅含预期项（如 8003 外网 403 走的是 Python 不是 nginx）。
- **FAIL**：出现 `no such file`/`open() ... failed` 指向 /var/www/xiaozhi-manager 下缺失文件 → 与 A5 交叉定位漏传文件。

### B2 Java 端 /yuhe/ 探活
```bash
python "G:/demo/21_xiaozhi/code/.workbuddy/ssh_run.py" \
  "systemctl is-active xiaozhi-manager-api" \
  "curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:8002/yuhe/user/pub-config" \
  "curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:8001/yuhe/user/pub-config" \
  "tail -20 /opt/xiaozhi/logs/manager-api.log"
```
- **PASS**：is-active=active；8002 与 8001 两条 pub-config 均 200；manager-api.log 尾部无 ERROR/exception（Liquibase 启动报错也会在这里现形）。
- **FAIL**：Java 未 active 或日志有 Liquibase/DDL 报错 → 触发回滚条件 C3。

### B3 ai_device_config 表可查 + Liquibase changelog 断言
```bash
python "G:/demo/21_xiaozhi/code/.workbuddy/ssh_run.py" \
  "mysql -uroot -p123456 -N -e 'show tables like \"ai_device_config\";' xiaozhi_esp32_server" \
  "mysql -uroot -p123456 -N -e \"select count(*) from xiaozhi_esp32_server.DATABASECHANGELOG where id in ('202610060030','202610070010');\""
```
- 内嵌引号多层 → **必须 base64 版**。等价 SQL（留档）：
```sql
show tables like 'ai_device_config';
select id from xiaozhi_esp32_server.DATABASECHANGELOG where id in ('202610060030','202610070010') order by id;
select count(*) from xiaozhi_esp32_server.ai_device_config limit 5;
```
- **PASS**：`ai_device_config` 表存在；DATABASECHANGELOG 中 **202610060030 与 202610070010 两条都在**（count=2，且 B2 Java active 说明 202610070010 的 DDL 已执行成功）。
- **FAIL**：表缺失或 changelog 缺 202610070010 → Java 端 Liquibase 未完成，触发回滚条件 C3（DB 侧先保留现场，勿手工 DELETE changelog 行）。

---

## C. 判据总表 + 截图点位 + 回滚触发条件

### C1 通过判据（全绿才算冒烟 PASS）
| 段 | 项 | 判据 |
|---|---|---|
| A1 | 站点 200 | HTTP 200 + text/html |
| A2 | SPA fallback | 5 个抽样页 + 1 个不存在页全 200 且回 index.html |
| A3 | P1 新路由 | 200 + 强刷后菜单/页面正常 |
| A4 | login 不 500 | 三条 HTTP 200（业务码允许非 0） |
| A5 | chunk 无 404 | dist 清单全 200，service-worker.js 200 |
| A6 | SW 强刷 | active SW 为新构建，无旧哈希 404 |
| B1 | nginx 日志 | 部署时刻后无新增 error / 无指向新 dist 文件的 404 |
| B2 | Java 探活 | active + 8002/8001 pub-config 200 + 日志无异常 |
| B3 | DB | ai_device_config 存在 + changelog 含 202610060030、202610070010 |

### C2 截图留证点位（执行时逐一截图归档到 `.workbuddy/reports/`）
- **S1** 登录页（强刷后首屏）
- **S2** /home 控制台（双栏骨架 + KawaiiSidebar 全菜单，能看到新菜单项）
- **S3** 设备配置管理页（P1 新路由，渲染完整）
- **S4** 设备管理页（DeviceManagement，配置入口可见）
- **S5** F12 Network 首屏（chunk 全 200）+ Console（无红色 error）
- **S6** F12 Application → Service Workers（active = 新构建）
- **S7** 部署机 B1/B2 终端输出（nginx error 抽样 + manager-api.log 尾部）
- **S8** 部署机 B3 终端输出（show tables + changelog count）

### C3 回滚触发条件（任一命中 → 立即上报 team-lead，经确认后执行回退）
| # | 条件 | 回退动作（参照 deploy_memory_v1.md 阶段回滚） |
|---|---|---|
| 1 | 站点/chunk 大面积 404，白屏无法恢复（A1/A2/A5 FAIL 且非个别文件） | 前端回退：`rsync -a --delete <批次备份>/xiaozhi-manager-web/ /var/www/xiaozhi-manager/` |
| 2 | /yuhe/ 反代全断（B2 8002 无响应且 Java 未 active） | Java 回退：`cp <批次备份>/xiaozhi-esp32-api.jar /opt/xiaozhi/ && systemctl restart xiaozhi-manager-api` |
| 3 | Liquibase 执行失败 / 202610070010 异常致 Java 起不来 | 先保留 DB 现场（mysqldump 该 changeSet 相关表）；Java 回退旧 jar；DB 若已污染按批次备份 sql.gz 定点恢复，**不手工删 changelog 行** |
| 4 | 冒烟失败且 30 分钟内无法定位根因 | 全量回退（前端 + Java），DB 保留现场，转 team-lead 裁定 |

- **不回滚的情况**：个别 chunk 缺失但可补传、纯文案/样式问题（P1 视觉项）→ 记录缺陷，下批次修复。

---

## D. 回报格式（执行完成后发 team-lead）
```
【冒烟结果矩阵】
A1 站点200        PASS/FAIL
A2 SPA fallback   PASS/FAIL（5+1）
A3 P1新路由       PASS/FAIL（路由=<确认值>）
A4 login不500     PASS/FAIL
A5 chunk无404     PASS/FAIL（清单 N 个文件，M 个 MISS）
A6 SW强刷        PASS/FAIL
B1 nginx日志      PASS/FAIL
B2 Java探活       PASS/FAIL
B3 DB/changelog   PASS/FAIL（changelog count=?）
截图：S1-S8 已归档 .workbuddy/reports/<日期>-smoke/
失败项证据：<逐条列 curl 输出/日志片段/截图路径>
回滚触发：无 / 已触发条件 #N（附现场）
```

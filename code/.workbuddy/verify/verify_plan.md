# sandyun.top 生产发布 · 验收清单（人工）

> 配套脚本：`verify/check_prod.py`（只读采集 + 断言）、`verify/python_push_probe.py`（Python 端点契约探针）
> 本清单不修改生产任何状态；所有"写"类动作都在第 4 节，由人工在浏览器里做一次。

发布对象与期望指纹：

| 对象 | 期望 |
|---|---|
| Java jar | `/opt/xiaozhi/xiaozhi-esp32-api.jar`，md5 `4efef7161ab3ed69474bdb27ee5b468b`，unit `xiaozhi-manager-api` active |
| Python `core/services/wake_word_service.py` | md5 `38c7fe7734618af416c4f35818663b42` |
| Python `core/http_server.py` | 含 `"/api/device-config/push"` 路由（本次未给基线 md5，只验内容 + 记录 md5） |
| 前端 `/var/www/console-v2/admin/` | 换成 `dist-admin`：index.html md5 `4fb703fa03ac224938d5115edea770eb`，引用 `/admincc/assets/index-CR0JikiI.js`（md5 `9f5d974f3893d8c9733064123e7ccec5`，510157 B） |

**路径更正（重要）**：Python 侧文件是 `core/http_server.py`，**不存在** `core/api/http_server.py`。
`core/api/` 下是各 handler（`wake_word_handler.py` 等）。生产根目录按 systemd unit 是
`/root/xiaozhi-server/main/yuhe-server`。

---

## 0. 判定纪律：四条"不能靠它判断"的坑

这四条决定了下表为什么这么写。任何人补测时都不要绕开。

### 坑 1｜Java 侧 HTTP 状态码全程不可信
`Oauth2Filter.onAccessDenied` 与 `RenExceptionHandler` 都没有 `@ResponseStatus`，未登录访问任何
`/yuhe/**`（**包括根本不存在的路径**）都返回 `200` + body `{"code":401}`。
所以「200」既可能是成功也可能是 401，而 404 永远不会出现 —— 401 把 404 盖掉了。

```bash
# 自证：不存在的路径也返回 200+401
curl -sk -o /dev/null -w '%{http_code}\n' https://127.0.0.1:9443/yuhe/__not_exist__ -H 'Host: sandyun.top'
# 期望：200（body 是 {"code":401,...}）。若返回 404，说明异常处理器行为变了，下方所有状态码结论作废。
```

→ 接口存在性**唯一可靠证据**是免登录的 `GET /yuhe/v3/api-docs*`（`ShiroConfig` 里
`/v3/api-docs/** = anon`），从返回 JSON 的 `paths` / `components.schemas` 里查字段。

### 坑 2｜Python 侧正好相反：401 才是"路由已注册"
aiohttp 没有全局鉴权拦截，`/api/memory|tts|llm|model` 才走 `memory_loopback_middleware`；
`/api/device-config/push` 不在该中间件覆盖范围，鉴权在 handler 内部做。

| 现象 | 结论 |
|---|---|
| `POST /api/device-config/push` 无 token → `401 {"code":401}` | 路由已注册（发布成功） |
| 同上 → `404 "404: Not Found"` | 路由未注册（`http_server.py` 没生效，或 `set_wake_word_service()` 没调用导致 `handler=None`） |
| 同上 → `503` | 路由在，但 `WakeWordService` 未初始化 |

### 坑 3｜前端 hash 不能只看 200
旧 index.html 照样 200，只是引用老 hash。必须三项对齐：磁盘 md5 → 返回体里 `grep -o` 计新 hash 次数 → 直接拉新 asset 比字节数。
（minified 是单行，**不要用 `grep -c` 数行**，要用 `grep -o ... | wc -l`。）

### 坑 4｜JVM 可能持有旧 inode
`mv` 覆盖 jar 后若没真正重启，unit 时间戳正常、`is-active` 正常，跑的还是旧代码。
必须比对 `/proc/<pid>/fd` 里指向 jar 的 fd 的 inode 与磁盘 inode，或看 fd 是否带 `(deleted)`，
再用「进程启动时间 vs jar mtime」交叉验证。

```bash
PID=$(systemctl show -p MainPID --value xiaozhi-manager-api)
ls -l /proc/$PID/fd | grep -i jar          # 期望路径结尾没有 "(deleted)"
stat -Lc '%i' /opt/xiaozhi/xiaozhi-esp32-api.jar
stat -Lc '%i' /proc/$PID/fd/<上面看到的fd号>   # 两个 inode 必须相同
```

---

## 1. 基础设施层（进程 / 端口 / 文件指纹）

> 对应 `check_prod.py` 的 J-01~J-06、P-01~P-06、F-01~F-03。跑脚本即可，下表用于人工复核或脚本报 FAIL 时定位。

### 1.1 Java（manager-api）

| 编号 | 测什么 | 怎么测 | 期望 | 不满足时第一排查动作 |
|---|---|---|---|---|
| J-01 | 服务态 | `systemctl is-active xiaozhi-manager-api` | `active` | `journalctl -u xiaozhi-manager-api -n 120 --no-pager`，先看有没有 `BeanCreationException` / 端口占用 |
| J-02 | 启动时间可解析 | `systemctl show -p ExecMainStartTimestamp --value xiaozhi-manager-api` | 能换算 epoch（运行了多久只作展示）。**是否本轮重启由 J-05 判**（jar mtime vs 进程启动），不用"30 分钟内"这种墙钟阈值——验收常在发布数小时后做 | 时间解析不出来 = systemd 输出格式变了；**不要**只看 `ActiveEnterTimestamp` |
| J-03 | 磁盘 jar 指纹 | `md5sum /opt/xiaozhi/xiaozhi-esp32-api.jar` | `4efef7161ab3ed69474bdb27ee5b468b` | 上传/落盘失败或落到别的路径（用 `/proc/<pid>/cmdline` 确认真实 `-jar` 路径） |
| J-04 | 运行中 jar = 磁盘 jar | `ls -l /proc/<pid>/fd \| grep -i jar` + `stat -Lc '%i'` 比 inode | fd 的 inode == 磁盘 inode，且无 `(deleted)` | 有 `(deleted)` 或 inode 不同 = 仍在跑旧 inode：`systemctl restart` 后重测 |
| J-05 | jar 与进程新老关系 | `stat -Lc '%Y' <jar>` 与 `ExecMainStartTimestamp` 转 epoch 比较 | 进程启动时间 ≥ jar mtime | 进程比 jar 老 = 覆盖后没重启 |
| J-06 | 端口 | `ss -lntp \| grep ':8002 '` | 有 LISTEN，属主是 java | 端口被占/未监听：看 journal 的 `APPLICATION FAILED TO START` |

> **重启后立刻验要等**：Java 起服基线 **25~30s**（历史：14:37:06 启动 → 14:37:33 Tomcat started）；
> 脚本加 `--wait-ready 90` 会先轮询到两个服务 active 再采集，避免把「还在起」误判成 FAIL。
> 手动复核可用：`curl -o /dev/null -w '%{http_code}' http://127.0.0.1:8002/yuhe/`（期望 200，轮询上限给 90s）。
>
> **J-07 回滚件**：`ls -1 /opt/xiaozhi/xiaozhi-esp32-api.jar.bak*`，期望 >=1 个（本次为 `.bak-wakeword-20261017`）。没有 .bak 不阻塞发布，但回滚要重新上传，记 WARN。

### 1.2 Python（yuhe-server）

| 编号 | 测什么 | 怎么测 | 期望 | 不满足时第一排查动作 |
|---|---|---|---|---|
| P-01 | 单进程 | `ps -eo pid,lstart,etimes,args \| grep -E '[p]ython[^ ]* app\.py'` | **恰好 1 行** | ≥2 行 = 新旧并存，老进程占着 8000/8003，新代码看似"没生效"。先 `kill` 老 PID 再 `systemctl restart yuhe-server` |
| P-02 | unit 态 | `systemctl is-active yuhe-server` | `active` | 若不是 systemd 托管，以 P-01 为准（脚本该条降级为 WARN） |
| P-03 | 服务文件指纹 | `md5sum $ROOT/core/services/wake_word_service.py` | `38c7fe7734618af416c4f35818663b42` | md5 不符 = 文件没换或换到别处；用 `readlink /proc/<pid>/cwd` 确认 `$ROOT` |
| P-04 | 新路由在源码里 | `grep -oF '/api/device-config/push' $ROOT/core/http_server.py \| wc -l` | ≥1 | 0 = `http_server.py` 没同步；注意别去查 `core/api/http_server.py`（不存在） |
| P-05 | handler 有下发函数 | `grep -c handle_push_device_config $ROOT/core/api/wake_word_handler.py` | ≥1 | 0 = handler 未同步，路由注册了也会 `AttributeError` → 500 |
| P-06 | 端口 | `ss -lntp \| grep -E ':(8000\|8003) '` | 8000、8003 都有 LISTEN | 缺 8003 = HTTP 服务没起（`SimpleHttpServer.start` 异常，看 app.log 的「HTTP服务器启动失败」） |

> 8000 = WebSocket，8003 = HTTP（OTA/vision/push）。8002 = Java。

### 1.3 前端（console-v2 admin）

| 编号 | 测什么 | 怎么测 | 期望 | 不满足时第一排查动作 |
|---|---|---|---|---|
| F-01 | 磁盘 index.html | `md5sum /var/www/console-v2/admin/index.html` | `4fb703fa03ac224938d5115edea770eb` | 不符 = 没换成 `dist-admin`，或换到 `dist/`；确认 `rsync` 源目录 |
| F-02 | index 引用新 hash | `grep -oF 'index-CR0JikiI.js' .../index.html \| wc -l` | ≥1 | 0 = 旧 index（老 hash），或缓存未清 |
| F-03 | 新 asset 指纹 | `md5sum` + `stat -c %s` 目标 asset | md5 `9f5d974f...`、510157 B | 大小不符 = 半拷贝/被截断；不存在 = assets 没一起同步 |

---

## 2. 接口层（OpenAPI + Python 探针 + 静态入口）

| 编号 | 测什么 | 怎么测 | 期望 | 不满足时第一排查动作 |
|---|---|---|---|---|
| I-04 | OpenAPI 可匿名访问 | `curl -sk 'https://127.0.0.1:9443/yuhe/v3/api-docs/agent' -H 'Host: sandyun.top'` | 200 且体积 >2KB 的真 JSON | 拿不到 = jar 没起 / Shiro 里 `/v3/api-docs/**=anon` 被改；先做 J-01 |
| I-05 | DTO 含本轮新字段 | 在 `/v3/api-docs` 或 `/v3/api-docs/agent` 里 `grep -oF wakeWordThreshold \| wc -l`、同理 `interruptThreshold` | 各 ≥1 | 0 = jar 里没有这两个字段（旧 jar / 字段名不同）。脚本还会把**所有含 `hreshold` 的键**打印出来，便于宽松比对 |
| I-06 | 401 掩盖 404 前提仍在 | `curl -sk .../yuhe/__vfy_not_exist_9f3a__` | 200 + `{"code":401}` | 返回 404 说明异常处理器行为变了，本次所有"状态码"结论需重新审视 |
| I-07 | Python 新路由已注册 | `curl -s -o /dev/null -w '%{http_code}' -X POST http://127.0.0.1:8003/api/device-config/push`（无 token） | `401`（不是 404） | 404 = 路由没注册（P-04/P-05 回溯）；503 = `WakeWordService` 未初始化 |
| I-08 | 路由对照组 | 同法探老路由 `GET /api/wake-word/devices` 与 `/api/memory/agents` | 老路由也 401（memory 非回环 403 亦可） | **分层定位**：新 404 + 老 401 → 只缺新增 4 行（`core/http_server.py`）；两条都 404 → 8003 这一层的问题（端口/nginx/前缀），别先查代码 |
| I-01 | `/admin/` 入口 | `curl -sk https://127.0.0.1:9443/admin/ -H 'Host: sandyun.top'` 并检查 body 含新 hash | 200 且 `hash_hits≥1` | 200 但 hits=0 = 走的是旧 index：查 nginx `root`/`alias` 与 `try_files` |
| I-02 | `/admincc/` 入口 | 同上，路径 `/admincc/` | 200 且 `hash_hits≥1` | 两个入口必须都能拿到新产物；只有 1 个通过说明 nginx 只改了一处 |
> **为什么要 I-08 对照组**：新路由缺失时，进程照样活着、心跳正常、老链路的负向用例也全绿，但新功能是空的 —— 这种「活着但残废」只有路由探针能抓到。对照组用来排除「其实是 8003 整体不通」这种误判，避免把 nginx/端口问题当成代码问题。

| I-03 | 新 asset 经 nginx 可取 | `curl -sk -o /dev/null -w '%{http_code} %{size_download}' .../admincc/assets/index-CR0JikiI.js` | 200 且 510157 B | 404/403 = nginx 静态根与部署目录不一致（asset 在 `/var/www/console-v2/admin/assets`，URL 前缀是 `/admincc/assets`） |

> 端口语义（选错端口会得到"假故障"，本轮已踩过一次）：
>
> | 端口 | 语义 | 能否直接 curl |
> |---|---|---|
> | 8003 | python aiohttp **明文 HTTP**（应用层真值） | ✅ 鉴权/路由断言都走这里 |
> | 8002 | Java Spring Boot（context-path `/yuhe`） | ✅ 但状态码不可信（见坑 1） |
> | 9443 | nginx TLS 普通 vhost | ✅ 验静态入口/反代 |
> | 9444 | nginx TLS + `proxy_protocol` | ❌ 只给 stream:8001 用，直连必 `000` |
> | 8001 | 公网 TLS 的 stream 代理入口 | ✅ 验公网链路 |
>
> `check_prod.py` 默认用 `https://127.0.0.1:9443` + `Host: sandyun.top` 走本机回环，不出网、不绕 DNS。
> **不要用 9444**：那是 `listen 127.0.0.1:9444 ssl proxy_protocol`，只接受 stream:8001 转发时加的 PROXY protocol 头，
> 直连会在 TLS 握手阶段被 RST（nginx `error.log` 记 `broken header ... while reading PROXY protocol`，curl 得到 `code=000`）。
> 这会伪装成「前端没发布」——本轮就因此误报过 4 条 FAIL，换 9443 后全绿。要验公网链路用 `https://sandyun.top:8001`。
> 端口不是 9443 时：`--web-base https://127.0.0.1:443`（视 nginx 监听而定）。

### 2.1 Python push 端点契约探针（`python_push_probe.py`）

放到服务器上跑，**先读 `data/.config.yaml` 里的 `server.auth_key`（回退 `manager-api.secret`）**；
解析不到时用 `--auth-key` 手动给。脚本只打印 token 来源与长度，不打印明文。

```bash
cd $ROOT && cp verify/python_push_probe.py .
./.venv/bin/python python_push_probe.py                 # 零副作用用例集
./.venv/bin/python python_push_probe.py --auth-key xxx  # 自动解析失败时
```

覆盖的用例（真实契约来自 `core/api/wake_word_handler.py:87-117` 与 `core/services/wake_word_service.py:157-276`）：

| 用例 | 请求 | 期望 | 说明 |
|---|---|---|---|
| X-01 | POST 无 token | 401 + `code=401` | **地基断言**：404 说明路由没注册，后续全部作废 |
| X-02 | GET 同路径 | 405 | 方法不匹配同样证明路由存在 |
| X-03 | 错误 token | 401 | 防止鉴权被改空（历史上曾有"空 token 放行"） |
| X-04 | `payload={}` | 400 | handler 第一道闸 |
| X-05 | `payload="str"` | 400 | 非对象 |
| X-06 | 有 payload、无 agent/device | 400 | "至少需要指定一个" |
| X-07 | 仅白名单外键 `{evil_key:1}` | 400 | 键被静默丢弃 → `payload 无合法配置键` |
| X-08 | `{evil_key:1, volume:50}` | 200 且 data 全 0 | 陌生键不影响合法键 |
| X-09 | 阈值 101 / -1 / 999 | 400 | 越界被丢弃 → 无合法键 |
| X-10 | 阈值 1.5 | 400 | 非整数被丢弃 |
| X-11 | `volume=true` | 400 | 代码显式排除 bool |
| X-12 | `{wake_word_threshold:40, interrupt_threshold:15}` | 200 且 data 全 0 | **零副作用**：不存在的 agent + 无 device_id → `target_ids` 为空 |
| X-13 | 边界 0 / 100 | 200 | 0~100 闭区间 |
| X-14 | 非法 JSON | 400 | `JSONDecodeError` 分支 |

> 该端点**没有 dry-run**。所有"应成功"的用例都用 `agent_id=probe-nonexistent-agent-9f3a` 且不给 `device_id`：
> `_push_device_config` 的 `target_ids` 为空会直接返回全 0（`wake_word_service.py:358-364`），既不直投也不进离线队列。
> **若某个成功用例返回 `sent/offline > 0`，说明目标集合里混进了真实设备，立刻停手排查。**

> 副作用说明：X-01/X-03 故意不带/带错 token，会在 `data/app.log` 留下 1~2 条
> `[core.api.wake_word_handler] 鉴权失败（token为空或服务端未配置auth_key）` 的 WARNING；
> **这是探针自己造成的，不是故障**，别拿它当 L-02 的失败依据。

---

## 3. 业务层（DB 落库 + 真实链路）

> 本层只有"人工点一次管理端"才能产生数据。脚本只做只读查询：不给 `--db-cmd` 就记 SKIP。

### 3.0 四条实勘结论（不懂这四条，断言必然误判）

**① datetime 列存的是 UTC，不是本地时间。**
jar 内 JDBC URL 写死 `serverTimezone=UTC`，系统是 `Asia/Shanghai`；实测服务器 `now()` = 21:07 CST 而 `utc_timestamp()` = 13:07。
所以：

```sql
-- 正确：两端都用 UTC 比
SELECT device_id, update_date, CONVERT_TZ(update_date,'+00:00','+08:00') AS update_cst,
       TIMESTAMPDIFF(MINUTE, update_date, UTC_TIMESTAMP()) AS mins_ago_utc
FROM ai_device_config;

-- 错误：会恒定差 8 小时，得出"没更新"的假结论
-- WHERE update_date > NOW()
```

**② `update_date` 不能当"阈值已写入"的判据。**
壁纸批量推送也会重写这一列；binlog 行镜像证实**至少两次**写入 `config_json` **逐字节不变**、只把 `update_date` 推了一次（05:55:23Z、06:03:11Z）。
> 注：**不要**把这条扩展成「发布日全天只有两次写入」——整份 `binlog.000028` 实为 29 个事件（13:46:02–21:27:57 CST），发布前有大量单行编辑，`44:bd` 的 `wake_word` 当天还走过 `鬼鬼 → 你好 → 开心 → 早上好`（19:42–19:47）。本 kit 只在**发布窗口内**做判断。
→ 断言只落在 **key 是否存在 + 取值是否合规 + 双键是否等长** 上，时间只作展示。

**③ `wake_word_display` 是本次新增键，"它出现"才是新链路真的跑过的正向证据。**
`wake_word` 缺键是预期（Java 有值才注入）；存量 3 台的 `wake_word` 仍是汉字（历史形态，binlog 证明从未被清空）。

**④ 读配置不写库，所以 DB 只能证明"没写"，不能证明"没读"。**
判断"配置链路有没有被调用过"的**决定性依据是 Java 日志里 `ai_device_config` 的查询数**；
库侧指纹不变只能说明没有写入。反例：21:11:33 设备重连，`last_connected_at` 更新了，但那台设备的配置**没有被读过也没有被写过**——
如果只看 DB，会把"没读"误说成"没触发"。
另一侧证据（直接）：`binlog.000028` 在 21:27:57 之后**再无 `ai_device_config` 事件**，而 21:28:35 有一次 `ai_device` 心跳写入 → **上线登记只写 `ai_device`，不改配置**（此前用"指纹前后相同"只是间接推理，已升级）。
另外 `performance_schema.events_statements_summary_by_digest` **不区分发起方、无逐次时间点**，不能用来划"21:04 之后"的窗口；
里面 `SELECT /*!40001 SQL_NO_CACHE */ * FROM ai_device_config` 是 **mysqldump 的固定签名**（备份流量，23 次 / 21:17:41），不是应用读表。

其余已实勘基线：库名 `xiaozhi_esp32_server`（`yuhe` 库不存在）；`ai_device_config(device_id varchar(32) PRI, config_json json 原生类型, update_date datetime)`；`create_date` 全 NULL 不作判据；发布前基线 `c_wake_word=3 / c_display=0 / c_wake_word_threshold=0 / c_interrupt_threshold=0`，5 台里 3 台 `wake_word` = `["琳琳","玲玲","灵灵"]`、`["早上好"]`、`["你好"]`，另 2 台**从未配置**（不是被清空）；本次换包**无 liquibase 变更**；`ai_agent_wake_word` 恒 0 行（死代码，不可作判据）。

### 3.1 两层唤醒词，别交叉断言

| 层 | 载体 | 内容 | 上限 | DB 可断言 |
|---|---|---|---|---|
| ① 硬件唤醒引擎（esp-sr） | `config_json.wake_word` | **仅 agent 词**，ASCII 无调拼音 | ≤5（每条 ≤60） | 能 |
| ② 服务端 ASR 文本匹配 | 运行时 `conn.config["wakeup_words"]` | agent 词 **∪ 全局 10 词**（汉字） | 无 | **不能**（不落库） |

- 全局 10 词在 `sys_params.wakeup_words`（`嗨乐鑫;小爱同学;…;嘿你好呀`），**从不写入 device_config**，DB 实测 0 命中。
- 不要断言「13 词 vs 5 词丢词」，不要断言「全库无中文」（②层的来源永远是中文，发布不改它）。

### 3.2 执行顺序（硬性）：先保存，再查库

**发布窗口内不改写 `config_json`**：`binlog.000028` 在 21:04:19（新包启动）到 21:27:57（人工保存）之间，没有 `ai_device_config` 的写事件（21:03:01 / 21:11:33 / 21:28:35 三次全是 `ai_device` 心跳）。存量中文 `wake_word` 只有在经接口保存一次后才转拼音。
→ 必须先做完 §4 的人工保存，再跑 DB 断言；否则"没保存过"与"功能没生效"在库上完全同形。

**「设备重连」不算触发**（21:11:33 实测）：一台设备重连成功、`ai_device.last_connected_at` 从 `10:04:30` 推到 `13:11:33`（UTC），
但 `ai_device_config` 的 `update_date` **一点没动**。重连只走设备校验/上线登记，连"读后回写"都没有。
（指纹只在"同一时刻"可比：保存一次后 `18bf62c3…` 就作废了，**不要拿摘要值做断言**，用行级 `config_json` 前后对照 + `update_date`。）
→ 等设备自然重连，永远等不到变化。

**能触发配置链路的只有两个入口（二选一）**：

| 入口 | 是否写库 | 说明 |
|---|---|---|
| 管理端保存一次唤醒词 | **会写**（先按 §3.4 快照） | 走完整 Java 链路，能验拼音转换 + 落库 |
| **设备断电重启** | 零写入 | boot 才建 WS，`background_initialize` 里 `POST /config/agent-models` 才拉配置；同时 flush 21:06 那条离线队列 |

拔网线、心跳恢复、OTA 都**不触发**：`设备上线`/`心跳` 的 logger 是 `[core.heartbeat]`，只有 WS 建立时才会拉配置（见 §5.0）。

> ⚠️ **21:27:57 那次保存是两条独立 UPDATE**（binlog 两个 `Update_rows` 事件）：
> ① `早上好 → guigui` + `wake_word_display:["guigui"]`；② 同值 + `interrupt_threshold:0`。
> 即唤醒词/display 先落、阈值后落。**是否同一事务未验证**，所以：B-01 只断言**最终态**；
> 报告里**不要写"三个键原子写入"**；将来若要加"中途崩溃不留半套"的断言，得先确认事务边界。

### 3.3 断言（对应 `check_prod.py` B-01~B-04）

```sql
-- 计数总览（发布前基线：3 / 0 / 0 / 0）
SELECT
 (SELECT COUNT(*) FROM ai_device_config WHERE JSON_CONTAINS_PATH(config_json,'one','$.wake_word'))           AS c_wake_word,
 (SELECT COUNT(*) FROM ai_device_config WHERE JSON_CONTAINS_PATH(config_json,'one','$.wake_word_display'))   AS c_wake_word_display,
 (SELECT COUNT(*) FROM ai_device_config WHERE JSON_CONTAINS_PATH(config_json,'one','$.wake_word_threshold')) AS c_wake_word_threshold,
 (SELECT COUNT(*) FROM ai_device_config WHERE JSON_CONTAINS_PATH(config_json,'one','$.interrupt_threshold')) AS c_interrupt_threshold;

-- 逐台明细（时间列是 UTC，显示时换算成 CST）
SELECT c.device_id, d.alias, a.agent_name,
       JSON_EXTRACT(c.config_json,'$.wake_word')         AS wake_word,
       JSON_LENGTH (JSON_EXTRACT(c.config_json,'$.wake_word'))         AS n_wake,
       JSON_EXTRACT(c.config_json,'$.wake_word_display') AS wake_display,
       JSON_LENGTH (JSON_EXTRACT(c.config_json,'$.wake_word_display')) AS n_disp,
       JSON_EXTRACT(c.config_json,'$.wake_word_threshold') AS ww_thr,
       JSON_EXTRACT(c.config_json,'$.interrupt_threshold') AS int_thr,
       c.update_date AS upd_utc,
       CONVERT_TZ(c.update_date,'+00:00','+08:00') AS upd_cst
FROM ai_device_config c
LEFT JOIN ai_device d ON d.id = c.device_id
LEFT JOIN ai_agent  a ON a.id = d.agent_id
ORDER BY c.device_id;
```

| 编号 | 断言 | 期望 | 不满足时第一排查动作 |
|---|---|---|---|
| B-01 | 阈值写入行为 | 判「**填了能不能正确写进去**」，不判「用户填没填」：`interrupt_threshold=0` 落库且 `JSON_TYPE=INTEGER` ⇒ 边界值 0 未被 falsy 吞掉（前端不丢 0、后端 `!= null`）；`wake_word_threshold` 留空 = **显式语义**（前端 `Agents.vue:344-350` 主动不发键，用设备默认 40），不算缺失。越界值才 FAIL | 全 0 台 = 还没保存过（先做 §4）；越界 = 后端没做 0~100 校验 |
| B-02 | 双键成对 | 凡出现 `wake_word_display` 的行：`JSON_LENGTH(wake_word)==JSON_LENGTH(wake_word_display)`、`wake_word` **无汉字**、`<=5`；只有 `wake_word` 没有 display 的行 = 存量，只提示；**有 display 没 wake_word = 孤儿，直接 FAIL**。⚠️ 只判**结构成对**，不判"展示可读"（见下方 ASCII 说明） | 孤儿/不等长 = 成对剔除被破坏（会"喊 A 显示 B"）；新链路行仍中文 = 拼音转换没生效 |
| B-03 | 硬件词数上限 | 每台 `JSON_LENGTH(wake_word) <= 5` | 截断逻辑失效（`WAKE_WORD_MAX_COUNT`） |
| B-04 | display 镜像原始输入 | `wake_word_display` 每项含汉字。非汉字 = **WARN**（体验取舍：屏幕显示拼音；非错位、非发布缺陷），**不判 FAIL** —— ASCII 是用户原始输入的镜像，不是错位 | 若要做成中文，用汉字再存一次（`鬼鬼` → `wake_word=["gui gui"]` + `display=["鬼鬼"]`） |

> ⚠️ **B-02 的能力边界**：只做**形状校验**（键成对 / 长度相等 / `wake_word` 为 ASCII / ≤5），
> **不做逐位内容比对**（`wake_word[i]` 是否恰为 `display[i]` 的拼音）。长度一致但内容错位（如 `["琳琳"]`+`["玲玲"]`）抓不到，
> 报告里不能写成"值也被校验过"。另：`n_disp == 0`（键存在但空数组）在当前生产**无实例**，属防御分支。

> ⚠️ **ASCII 输入（21:27:58 实况）**：`wake_word=["guigui"]`、`wake_word_display=["guigui"]`。
> `wake_word_display` 的语义是**镜像用户原始输入**——用户输 ASCII，它就等于 ASCII，这是设计正确行为，**不是错位**。
> 判定：**B-02 结构判 PASS**（双键成对等长）；**B-04 判 WARN**（屏幕显示拼音，属体验取舍）。
>
> **已知行为（非缺陷）**：唤醒词/display 变更在**当前 WS 连接内不生效**，需设备重连后落地；
> 重连前若设备仍以旧唤醒词上送，服务端 `wakeup_words` 已更新，该次唤醒不播放回复、语音按普通对话送 LLM。
> 实测：21:28:08 下发新词表后，21:28:09 同连接内上送「早上好」→ 无唤醒回复；21:28:19 断开、21:28:22 重连后
> 上送 `guigui` → 正常播放回复。（现有日志无法区分「必须重连」与「同连接内再等几秒」，此处只写可执行口径，不宣称已证明因果。）
>
> **汉字→拼音已被证实**：21:26:05 握手时库里中文 `["早上好"]` 被 Java 现场转成 `["zao shang hao"]`，不依赖保存动作。

> B-02 特意**不看 `update_date`**：壁纸批量写会刷新时间但不动 `wake_word`，用时间判新旧会把存量中文误判成"刚写入的中文"。

### 3.4 触发前的快照（因为保存会写库）

人工保存会写 `ai_device_config`（新增 `wake_word_display`、`wake_word` 拼音化）。回滚 jar 回不到"发布前的库状态"，所以触发前先留一份：

```bash
mysql -uroot -p123456 xiaozhi_esp32_server -e \
 "SELECT device_id, config_json, update_date FROM ai_device_config" > /tmp/aidc_before_save_$(date +%H%M).tsv
```

### 3.5 `ai_device` 比对：只比绑定与版本，时间字段一律豁免

`ai_device.last_connected_at` 是 **python 上报 → Java 异步落库**，设备一动就会变。拿它做"发布前后逐字段全等"必然误报。

| 设备 | 快照文件里（UTC，21:08~21:09 导出） | 生产现值（UTC，21:28:35 心跳后） | 差异 |
|---|---|---|---|
| `44:bd:8d:7b:3a:e4` | 13:03:01 | **13:28:35** | 有差异（21:28:35 心跳，保存后 37s） |
| `14:c1:9f:d1:33:48` | 10:04:30 | **13:11:33** | 有差异（心跳） |

```sql
-- 通过条件：5 行、agent 绑定与基线一致、app_version 全为 2.5.1
SELECT id, agent_id, app_version FROM ai_device ORDER BY id;
```

- **豁免字段**：`last_connected_at`、`update_date`。只有这两个会因心跳变化，不涉配置与绑定。
- **回滚预期写成"预期表"，不要写"查询某位点的库状态"**：`13805375` 是 binlog 位点，不是可查询状态；
  生产无副本实例，取它只能"在副本上 `--start-position=4 --stop-position=13805375` 重放后再查"。

| 回滚路径 | `44:bd` `last_connected_at` | `14:c1` `last_connected_at` |
|---|---|---|
| 逻辑回灌 21:09 dump | `13:28:35` → `13:03:01` | `13:11:33` → `10:04:30` |
| PITR 到 `13805375`（20:55:32 CST 位点） | `13:28:35` → `11:48:18` | `13:11:33` → `10:04:30` |

- 两条回滚路径都会把 `44:bd` 的 `config_json` 退回 `["早上好"]`（21:27:58 保存前的形态）；这一项两条路径**一致**，可作通用断言。
- **两条路径的 `last_connected_at` 结果不同**，不要用同一张"期望值"表套两次；两种基准（21:08/21:09 快照 vs 20:55:32 位点）
  **互相比对必然不等，且不等于异常**。
- 回滚验收统一口径：只比 `agent_id` 绑定 + `app_version`，`last_connected_at` / `update_date` 一律豁免。
- `last_connected_at` 只能说明"设备连到了 python、manager-api 能写库"，**不能说明设备拿到了配置**。
- **回滚后 `n_display` 从 1 变 0 是预期**：那 1 条是 21:27:58 保存产生的，21:35 的 post-save 存证在 `/root/deploy-verify/20261017T2135Z/postsave_device_config.sql`（43 行 / 4822 B / `35fed18f…`），**不在冻结目录**、`ROLLBACK.sh` 不触碰它。所以不要断言"回滚后 display 仍为 1"。
- 列名：`ai_device` 主键是 `id`，`ai_device_config` 主键才是 `device_id`（值为 MAC）；写错会 `Unknown column` 中断整段断言。
- 对照样本：`14:c1` 是 `wake_word=["琳琳","玲玲","灵灵"]` 且 `wake_word_display=NULL` —— 属"有 wake 无 display"的存量形态，**期望值里不要给它写 display**。

---

## 4. 无法自动化的部分（管理端 E2E，人工做一次）

**为什么不能自动化**：登录口令用 SM2 公钥加密（`LoginController:232-237`，公钥存在 sys_params），
且必须过图形验证码（`GET /user/captcha?uuid=`，`POST /user/login` 校验）。验证码天然无法自动化，
所以"编辑 agent → 拉滑块 → 保存 → 设备热生效"这条链只能人工点一次。

### 4.1 人工步骤（约 3 分钟）

1. 浏览器打开 `https://sandyun.top:8001/admincc/#/admin/agents`，F12 → Network。
   - 期望：`index-CR0JikiI.js` 在 Network 里被加载（**不是** `index-XXXX.js` 老 hash），且无 404。
2. 登录（账号 + 密码 + 图形验证码）。
   - 期望：`POST /yuhe/user/login` 返回 `{"code":0,...}`。
3. 选中一台**已绑定真实设备且设备在线**的 agent → 编辑。
   - **保存前先留库快照**（§3.4），因为这一步会真的写 `ai_device_config`。
   - 期望：能看到「唤醒词灵敏度」「实时打断灵敏度」两个滑块（这是本轮前端产物的可见证据）。
   - 若看不到：说明前端不是新产物（回到 F-01/F-02），或 `GET /yuhe/agent/{id}` 返回的 VO 里没有这两个字段（回到 I-05）。
4. 把唤醒词灵敏度拖到 40、实时打断灵敏度拖到 15 → 保存。
   - 期望：`PUT /yuhe/agent/{id}` 返回 **200 且 body `{"code":0}`**（注意：未登录也会 200，所以必须看 body 的 code）。
5. 立刻在服务器上跟日志（两个文件都要看）：
   ```bash
   tail -f /root/xiaozhi-server/main/yuhe-server/data/app.log
   journalctl -u xiaozhi-manager-api -f
   ```
   - 期望 Python 侧出现：`向设备 <device_id> 推送唤醒词阈值`、`向设备 <device_id> 推送实时打断阈值`
     （日志格式见 `wake_word_service.py:441`：`向设备 {device_id} 推送{log_tag}`，log_tag 为「唤醒词阈值」「实时打断阈值」）。
   - 若同时在编辑页保存了唤醒词，还应出现（**正向铁证**）：
     `已下发云端设备配置: {"wake_word": ["ni hao"], "wake_word_display": ["你好"], ...}` ——
     **两个数组成对出现才算通过**，只有 `wake_word` 没有 `wake_word_display` 视为不合格。
   - **失败信号**：接口 500 / 日志出现 `NoClassDefFoundError`、`ExceptionInInitializer`、`pinyindb` 相关报错。
   - 期望 Java 侧出现：`[AgentService] 唤醒词阈值推送成功 agentId=... payload={wake_word_threshold=40}`
     （`AgentServiceImpl.pushDeviceConfigToDevices` 的成功分支）。
6. 看设备串口日志（第 5 节）。
7. 跑 B-01/B-02 SQL（或 `check_prod.py --db-cmd ...`），确认 `ai_device_config` 对应行
   `update_date` 是刚才的时间、阈值在 0~100、`wake_word` 已转拼音且与 `wake_word_display` 等长。
   - **这一步是业务层唯一有效证据**：发布本身不写库，只有"保存一次"才会产生可判定的数据。
8. 刷新编辑页，确认滑块**回显** 40 / 15（回显取自 `ai_device_config`，见 `AgentServiceImpl:285-289`）。
   - 不回显 = 落库失败或回显路径没读到，回到 B-01。

### 4.2 可选反例（需要登录态，拷 token 用 curl 做）

编辑页的接口都需要 `Authorization`。从 DevTools 任一请求的 Request Headers 里拷出该值，然后：

```bash
# 反例：唤醒词含英文字母混排 → 期望业务码 10219（唤醒词包含无法转换为拼音的字符），
# 而不是"200 但设备没变"。
curl -s -X POST "https://sandyun.top:8001/yuhe/agent/wake-word/<agentId>"   -H 'Content-Type: application/json'   -H 'Authorization: <从 DevTools 拷贝>'   -d '{"wakeWords":"你好abc"}'
# 期望：{"code":10219,...}；若返回 0 且设备没变，说明校验链有洞。
```
> 该端点在本轮未改动，属"回归不被破坏"的检查，可选。做与不做都不影响本轮结论。

### 4.3 常见失败分支

| 症状 | 大概率原因 | 下一步 |
|---|---|---|
| 滑块不显示 | 前端旧产物 | F-01/F-02；确认浏览器强刷（Ctrl+F5） |
| `PUT /agent/{id}` 返回 `{"code":400}` | DTO 校验失败（阈值非 0~100） | 看 body 的 msg |
| `PUT` 成功但 Python 无推送日志 | Java 侧没走到 `applyDeviceConfigToDevices`；或 `server.secret` 为空（代码里为空直接 return）；或 http_port 参数不对 | `journalctl -u xiaozhi-manager-api` 找 `[AgentService] ... 推送异常/推送失败`；确认 sys_params 里 `server.secret` 与 `device_config_http_port` |
| Python 推送日志出现但 `sent=0, offline=1` | 设备不在线（进了离线队列，重连时补投） | 让设备上线后重试；或查 `get_online_devices()` 的心跳合并逻辑 |
| Python 推送日志为 `跳过...推送` | 设备 `need_bind` 未绑定，或来自 MQTT 网关 | 绑设备 / 换直连设备测 |
| 设备无 `云端...已更新` 日志 | 固件版本不含该分支 | 核对固件版本；本轮验收以服务端日志 + DB 为准，固件日志作为加强证据 |

---

## 5. 设备侧证据链（唤醒词 / 阈值 / "唤醒了却被当普通对话"）

> 先记住两层（与 §3.1 同一件事，现场排查时最容易混）：
> **硬件层**只认 `device_config.wake_word`（ASCII 拼音、≤5、仅 agent 词）；
> **文本匹配层**是运行时 `conn.config["wakeup_words"]` = agent 词 ∪ 全局 10 词（汉字，不落库）。
> 两条链各有各的日志，别拿 A 层的期望去判 B 层。

### 5.0 前置：先确认"有 WS 会话"，再谈设备侧

`设备上线 [yuhe-xxx]` 与 `心跳 [yuhe-xxx]` 的 logger 都是 `[core.heartbeat]`（心跳通道 12399），
**只证明设备还活着，不证明配置下发过**。发布重启后的实测：心跳 21:03:15 就恢复了，但 WS 连接日志 0 条、
`收到 hello` 0 条、`已下发云端设备配置` 停在 19:48:14 —— 设备只是"心跳在线"，没有会话。

WS 会话的特征行（logger 是 `[core.connection]`）：

- `conn - Headers: ...`
- `配置输出音频采样率为: ...`

一次正常握手在 `data/app.log` 里的**可观测**顺序：

```
异步获取差异化配置成功
已下发云端设备配置: {"wake_word": [...], "wake_word_display": [...]}
```

> ⚠️ **已知盲区：`wake_word_service` 的 INFO 从不落盘。**
> `core/utils/stdlib_log_bridge.py:5-7` 写明 root logger 无 handler、effective level=30（WARNING），
> 桥接只注册了 `wallpaper_ack` / `wallpaper_handler` / `wallpaper_service` 三个模块；
> `wake_word_service` / `wake_word_handler` **不在其中**。
> 所以 `尝试下发 N 条离线唤醒词`、`向设备 X 推送唤醒词` 这两类行**永远 grep 不到**（19:34~19:48 六次真实下发也没有）。
> → 推送链路的**成功路径不可观测**、失败路径（`logger.error`）可见。
> **任何依赖这两条日志的断言都是死码，已从 kit 删除**；正向只认 `已下发云端设备配置`（`core.connection` 走项目 formatter，INFO 可见）。

| 现象 | 判定 |
|---|---|
| 没有任何 WS 特征行 | WARN「尚未验证」，不判失败 → `check_prod.py` **L-05** |
| 有 WS、没有 `异步获取…` | **FAIL**：拉配置失败并静默降级（`connection.py:854-864` 刻意不打 ERROR），设备用全局默认配置 |
| 有 `异步获取…` 但没有 `已下发…` | WARN：该设备 `device_config` 可能为空（只有 wallpaper），非故障 |
| 三步齐全且两键同现 | PASS |
| 变更后同连接内 detect 文本与词表不匹配 | **已知行为（非缺陷）**：该次唤醒不播放回复、语音按普通对话送 LLM；需设备重连后落地（21:28:09 漏；21:28:19 断开、21:28:22 重连后恢复）。机制细节现有日志不可区分，未定论 |

> 离线队列在进程内存里：**设备断电重启前不要再重启 python**，否则 21:06 那条 `zao shang hao` 会丢。
> 另：不要期望"离线队列 flush 日志 + 云端配置下发日志"两条互证 —— 前者不落盘，实际只有 `已下发` 一条。

### 5.1 服务端下发的 payload 形态（决定一切）

`push_wake_words()` 组帧（`wake_word_service.py:125-129`）：

```json
{"type":"device_config","payload":{"wake_word":["ni hao xiao he"],"wake_word_display":["你好小禾"]}}
```

- `wake_word` = **无调拼音**（设备 MultiNet 需要），`wake_word_display` = **汉字**（屏幕显示）。
- 两个数组**按下标严格对齐**；任一侧被单独 filter 就会"喊 A 显示 B"。
- 推送成功后，服务端把 `conn.config["wakeup_words"]` 同步为**汉字**（`wake_word_service.py:131-152`），
  且只有"全组 display 齐备"才覆盖，缺失就整组不动。
- 设备上若非会话态（握手阶段），Java 侧 `ConfigServiceImpl` 会把库里的中文 `wake_word` **现场转拼音**再下发；
  所以"库里有中文"是历史形态，不代表设备拿到中文。


### 5.2 设备串口应出现的日志（`board.cc` ApplyDeviceConfig）

| 场景 | 日志（原文） |
|---|---|
| 唤醒词生效 | `云端唤醒词已生效: N 个 [...]（开机即用，已存本地）` |
| 唤醒词未变 | `云端唤醒词未变化，跳过更新（N 个）` |
| 唤醒词清空 | `已清空云端唤醒词，恢复默认` |
| 唤醒词阈值 | `云端唤醒词阈值已更新: 40%` |
| 实时打断阈值 | `云端实时打断阈值已更新: 15` |
| 音量/亮度收尾 | `应用云端配置 volume=keep brightness=keep` |

阈值同时写 NVS（`wake_word_config` / `interrupt_config`），重启后自恢复。

### 5.3 "唤醒了却被当普通对话"这个 bug 怎么判

判定点在 `core/handle/textHandler/listenMessageHandler.py:97`：

```python
is_wakeup_words = filtered_text in conn.config.get("wakeup_words")
```

- `filtered_text` 是 ASR 出来的**中文文本**；
- `conn.config["wakeup_words"]` 必须是**汉字**列表。一旦里面是拼音（如 `ni hao xiao he`），
  `in` 判断永远 False → 走 else 分支（`:110`）把用户原话丢给 LLM，表现就是"明明唤醒了，却被当普通聊天"。
- 这个列表是 **agent 词 ∪ 全局 10 词**（`core/connection.py:948-961` 合并）。所以喊「嗨乐鑫」这类
  全局词也能命中；反过来，设备能在**硬件层**唤醒（固件内置词表）但文本层列表里没有该词时，
  仍然会走"普通对话"分支 —— 这正是该 bug 的另一种触发形态，排查时两者都要看。

两个分支的可观测差异：

| 分支 | 行为 |
|---|---|
| 命中唤醒词（`:106`） | `startToChat(conn, "嘿，你好呀")` —— 唤醒应答，LLM 首句固定是「嘿，你好呀」 |
| 未命中（`:110`） | `startToChat(conn, original_text)` —— 把识别到的原话当普通提问 |

**唤醒词链路的正向断言口径**（保存一次、或设备断电重启建立 WS 后，同时满足才算通过）：

- `wake_word` 每项匹配 `^[a-z][a-z ]*$`（纯 ASCII、无汉字、无调号）；
- `wake_word_display` 每项含汉字；
- `len(wake_word) == len(wake_word_display)` 且**按下标一一对应**（喊第一个词，屏幕显示第一项）。

**判定方法（3 步）**：

1. 喊一次唤醒词，抓服务端 `data/app.log` 里该设备的 ASR 文本（应是汉字，如"你好小禾"）。
2. 看紧接着送给 LLM/TTS 的第一句是不是「嘿，你好呀」。
   - 是 → 命中正常。
   - 不是（是用户原话）→ 命中失败，去查 `conn.config["wakeup_words"]` 是否被写成了拼音。
3. 现场取证（不改代码，只读）：在设备唤醒后立刻执行
   ```bash
   grep -n "wakeup_words" /root/xiaozhi-server/main/yuhe-server/data/app.log | tail -5
   ```
   或临时看连接态（二选一，注意别在生产上做写操作）：
   `python3 -c "..."` 直接读内存不现实，务实做法是**看推送日志 + 看设备屏幕显示**：
   屏幕显示汉字但语音喊汉字没反应 ⇒ 几乎可以断定 `wakeup_words` 里是拼音。

> 这条 bug 的历史成因写在 `wake_word_service.py:136-146` 的注释里：`display` 参差时
> `any()` 判定 + `d or w` 取值，会把拼音塞进 `wakeup_words`。修复后是"全组 display 齐备才覆盖"，
> 所以验收时要**特意测一次"只改唤醒词、display 同步"**：喊新词应命中，屏幕显示应与所喊一致。

### 5.4 "喊 A 显示 B"（下标错位）怎么判

- 一次配 2~5 个唤醒词（例如「你好小禾；早上好」），设备屏幕逐条核对显示文本与所喊的词是否一一对应。
- 错位 = 服务端 `wake_word` / `wake_word_display` 两侧被各自压缩了下标（`wake_word_service.py:228-266` 的成对剔除逻辑没生效）。

---

## 6. 一页纸执行顺序

```bash
# 0) 目录（Windows Git Bash）
cd G:/demo/21_xiaozhi/code/.workbuddy

# 1) 主验证（只读，约 10~20 秒）——退出码 0 表示无 FAIL
#    刚重启完就验：加 --wait-ready 90（Java 基线 25~30s）
"D:/INSTALL/python313/python.exe" verify/check_prod.py --wait-ready 90 --save

# 2) Python 端点契约探针（上传后在生产上跑）
"D:/INSTALL/python313/python.exe" sftp_push.py verify/python_push_probe.py \
  /root/xiaozhi-server/main/yuhe-server/python_push_probe.py
"D:/INSTALL/python313/python.exe" ssh_run.py \
  "cd /root/xiaozhi-server/main/yuhe-server && ./.venv/bin/python python_push_probe.py; rm -f python_push_probe.py"

# 3) 人工 E2E（第 4 节，浏览器点一次）

# 4) 业务层（第 3 节）——**必须先做完 3) 的人工保存**，否则库里仍是旧数据
"D:/INSTALL/python313/python.exe" verify/check_prod.py \
  --db-cmd "mysql -uroot -p123456 xiaozhi_esp32_server" --save
```

判定：
- `check_prod.py` 有 FAIL → 未达验收标准，按对应行的"第一排查动作"处理；
- 全 PASS/WARN → 基础设施 + 接口层通过，仍需第 4 节人工点一次才算验收完成；
- **L-02 的 PASS 必须带「窗口外历史异常」**：`data/app.log` 用两套 writer，无前缀的 `Traceback/ERROR` 靠「继承上一条时间戳」归属；
  PASS 只说明**本轮切片内**没有异常，报告里必须同时写清历史异常有几条、首条在哪个行号，不能写「均为本轮新增」；
- **外部依赖 ERROR 单独归类**：`获取天气失败`（第三方 KEY/Token 鉴权失败）与本次发布无关，不计入 L-02 的 FAIL，
  但必须在报告里点名条数，由人工确认是否落在验收范围内；
- **L-03 = WARN 是「尚未验证」，不是「通过」**：拼音链路（pinyin4j 首次调用才初始化）此时完全没有一手证据，必须保存一次唤醒词、或让设备**断电重启建立一次真实 WS 会话**后重跑（拔网线/心跳恢复不会触发）；L-03、L-05 与 B-02 都转 PASS 才算真过；
- 回滚：本轮发布前的快照与回滚脚本见发布前快照任务产出的 runbook（不在本文件重复）。

## 7. 结果记录（贴到发布记录里）

| 层级 | 结果 | 备注 |
|---|---|---|
| 基础设施（J-01~J-07 / P / F） | PASS / FAIL / WARN | J-07 = 回滚件是否在位 |
| 接口（I-01~I-08） | | |
| Python 探针（X-01~X-14） | | |
| 业务（B-01~B-04） | | 需先人工保存一次；B-01 判「填了能否正确写入」（0 边界值可落库），B-04 非汉字 = WARN（体验取舍） |
| 日志（L-01~L-05） | | L-04 = 负向用例命中（预期 WARNING，不是故障）；L-03/L-05=WARN 表示正向链路还没被触发过，必须保存一次或断电重启后再验 |
| 设备（5.1~5.4） | | 需真机 |
| 结论 | 可交付 / 回滚 | 作废版本：`..._213235.md`（B-02 误判 FAIL，等级错误），以最新一份为准 |

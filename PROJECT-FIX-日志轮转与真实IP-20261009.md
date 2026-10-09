# 日志追加 + logrotate + 设备真实 IP 修复

日期：2026-10-09
范围：systemd 日志落盘方式、logrotate 配置、nginx stream/http 链路

---

## 一、日志：改追加 + 轮转

### 排查结论：`>` 覆盖写已经不存在了

全盘扫过一遍，**没有找到任何 `>` 覆盖写**：

| 位置 | 现状 |
|---|---|
| `xiaozhi-server.service` | `StandardOutput=append:.../data/app.log`（10-09 WS 修复时已改） |
| `xiaozhi-manager-api.service` | `StandardOutput=append:/opt/xiaozhi/manager-api.log` |
| `/root/*.sh`、`/opt/xiaozhi/*.sh` | 无（压根没有启动脚本，全走 systemd） |
| `~/.bash_history` | 无 `>` 记录 |
| loguru（`tmp/server.log`） | 默认 append，自带 10MB 轮转 + 30 天保留 |

**真正的问题是另一个**：两个 unit 都是追加，但**没有任何轮转**，文件无限膨胀——
`manager-api.log` 已经 **65MB**、`app.log` **6MB**，而且从不切割。

### 改了什么

新增 `/etc/logrotate.d/xiaozhi`：

```
/root/.../data/app.log
/opt/xiaozhi/manager-api.log
{
    daily
    rotate 14
    maxsize 200M
    compress
    delaycompress
    missingok
    notifempty
    copytruncate      # 关键，见下
    dateext
    dateformat -%Y%m%d
    su root root
}
```

**为什么必须 `copytruncate` 而不是默认的 `create`**：
systemd 用 `StandardOutput=append:` 直接持有文件 fd。默认的 `create` 会 rename 旧文件再新建同名文件，
但 systemd 持有的仍是旧 inode —— 表面上"轮转了"，实际新文件永远是空的、旧文件继续膨胀到磁盘满。
`copytruncate` 是拷贝留档后原地截断，fd 不变，systemd 完全无感。

`tmp/server.log` **不纳入**：loguru 自己按 10MB 轮转、保留 30 天，再交给 logrotate 会和它抢文件。

### 实测结果

| 项 | 轮转前 | 轮转后 |
|---|---|---|
| `app.log` | 6,162,089 B | 0 B（新文件） |
| `app.log-20261009` | — | 6,162,089 B（留档） |
| `manager-api.log` | 65,755,723 B | 0 B（新文件） |
| `manager-api.log-20261009` | — | 65,755,723 B（留档） |

**断流验证**：轮转后 15 秒内 `app.log` 从 9784 B 涨到 15862 B，`manager-api.log` 涨到 92 KB，
两个服务都持续写入，**fd 没断**。

---

## 二、nginx：设备真实 IP 进日志

### 根因

链路是 4 跳：`设备 → nginx stream:8001 → nginx http:9001 → Python:8000`。
stream 转发后，http 层看到的对端就是 `127.0.0.1`，于是
`proxy_set_header X-Real-IP $remote_addr` 写进去的就是 `127.0.0.1`。

**Python 侧其实早就支持**（`core/connection.py:212` 读 `x-real-ip` / `x-forwarded-for`），
所以**代码一行都不用改**，纯粹是 nginx 配置缺了 PROXY protocol。

### 改了什么

1. **stream 层**（`nginx.conf`）：加 `proxy_protocol on;`，上游改指新端口
2. **新增 http server**：`127.0.0.1:9002`（明文）+ `127.0.0.1:9444 ssl`，
   listen 带 `proxy_protocol`，配 `set_real_ip_from 127.0.0.1` + `real_ip_header proxy_protocol`
3. **新增 stream 访问日志** `/var/log/nginx/stream-8001.log`（已被 `/etc/logrotate.d/nginx` 的 `*.log` 覆盖）

### 为什么用独立端口 9002/9444，而不是直接给 9001/9443 加 proxy_protocol

9001/9443 是**公网直连端口**，实测有 censys / infrawat.ch / modat.io / Go-http-client 等扫描流量。
一旦在这些端口上开 proxy_protocol，**所有不发 PROXY 头的直连都会握手失败**。

独立端口 + 只绑 `127.0.0.1` 的好处：
- 对现有 9001/9443 **零影响**（直连时 `$remote_addr` 本来就是真 IP）
- 不新增公网暴露面
- 出问题只要把 stream 的 map 改回 `127.0.0.1:9001 / 9443` 并去掉 `proxy_protocol on;` 即可**秒级回滚**

### ⚠️ 我踩的坑（已修复，务必记住）

第一版我只在新 server 块里写了 `/xiaozhi/v1/` 和 `/xiaozhi/` 两个反代 location。
**结果 `https://sandyun.top:8001/` 掉回了 nginx 欢迎页，`/admincc/` 从 200 变 404。**

原因：`nginx.conf` 注释里写着「浏览器 https://8001 → 9443（SSL web）」——
**8001 的 HTTPS 同时承载管理后台网页**。stream 按 TLS 分流的那一支既走设备 wss，也走浏览器。

修复：把新块做成 `xiaozhi-manager` 的**完整副本**（`/`、`/assets/`、`/admincc/`、`/cc/`、`/xiaozhi/` 全带），
只改 listen 和加 real_ip。已在配置文件里写了醒目注释，提醒后续改 `xiaozhi-manager` 时必须同步这里。

### 实测结果

从外网分别用 `ws://` 和 `wss://` 连 `sandyun.top:8001` 做握手探针：

| 时间 | 客户端 IP | device-id | 说明 |
|---|---|---|---|
| 14:45:46 | **127.0.0.1** | `14:c1:9f:d1:33:48` | 改前 · 真实设备 |
| 14:46:40 | **127.0.0.1** | `14:c1:9f:d1:33:48` | 改前 · 真实设备 |
| 14:51:13 | **117.67.194.234** | `ppfix-plain` | 改后 · ws:// 探针 |
| 14:51:17 | **117.67.194.234** | `ppfix-tls` | 改后 · wss:// 探针 |

stream 层日志同步记录：`117.67.194.234 [09/Oct/2026:14:51:17 +0800] -> 127.0.0.1:9444`

**网页回归**（改坏后修复的验证）：

| 路径 | 经 8001（新块） | 直连 9443（旧块） |
|---|---|---|
| `/` | 200 `<title>屿禾工坊</title>` | 200 同标题 |
| `/admincc/` | 200 | 200 |
| `/cc/` | 200 | 200 |

### 还顺手加的

`X-Forwarded-For` 用 `$remote_addr` **覆盖**而非 `$proxy_add_x_forwarded_for`：
后者会拼接客户端自带的 XFF，而 Python 取 `split(",")[0]` 会拿到**伪造值**。

---

## 三、备份与回滚

| 文件 | 备份 |
|---|---|
| `/etc/nginx/nginx.conf` | `nginx.conf.bak-20261009T064900Z` |
| `/etc/nginx/sites-available/xiaozhi-manager` | `xiaozhi-manager.bak-20261009T064900Z` |
| `/etc/logrotate.d/xiaozhi` | 新建（无旧文件） |

**回滚真实 IP**：把 `nginx.conf` 里 stream 的 map 改回 `127.0.0.1:9001 / 9443`，
删掉 `proxy_protocol on;`，`nginx -t && systemctl reload nginx`。旧端口一直没动，10 秒可回。

---

## 四、收尾：端口收敛 + 公共 location 抽 snippet

### 1. 端口收敛（9001/9443 收为仅本机）

先取证据再动手，不凭猜：

| 证据 | 结果 |
|---|---|
| 给访问日志加 `$server_port` 采样 150s | 9001/9443 **零请求**，只有 9002 有设备连接 |
| 历史日志 `host:port` 统计（近 5 天，9796 条） | 只有 `sandyun.top:8001`，**9001/9443/8443 一次都没出现** |

结论：设备与浏览器全都走 8001，9001/9443 已沦为纯内部上游 → 收成 `listen 127.0.0.1:...`。
8443 保持公网不变（它是独立的 HTTPS 入口，与本次改造无关）。

### 2. 公共 location 抽成 snippet

新增 `/etc/nginx/snippets/xiaozhi-common.conf`，装 `root` / `index` 和全部 location；
两个 server 块各自只留 listen、ssl、real_ip，然后 `include` 同一份。
**从根上消除"改一处漏一处"**——就是那个把 `/admincc/` 搞成 404 的坑。

### ⚠️ 又一个坑：reload 改不了 listen 地址，必须 restart

第一次部署后 `nginx -t` 通过、`reload` 也"成功"，但 `ss` 里仍是 `0.0.0.0:9001`。
查 error.log 才看到：

```
[emerg] bind() to 127.0.0.1:9443 failed (98: Address already in use)
[emerg] bind() to 127.0.0.1:9001 failed (98: Address already in use)
[emerg] still could not bind()
```

原因：**旧 worker 还占着 `0.0.0.0` 的 listen socket**（它们身上挂着长连接不会主动退出），
新的 `127.0.0.1` 地址绑不上。nginx 会静默继续用旧 socket 服务 —— 所以没造成中断，
但改动**完全没生效**，而且不看 error.log 根本发现不了。

**改 listen 地址必须 `systemctl restart nginx`，reload 不够。**（已执行，重启后绑定正常。）

### 3. 最终状态

```
0.0.0.0:8001     stream 入口（设备 ws/wss + 浏览器 https）
0.0.0.0:8443     独立 HTTPS 入口（未动）
127.0.0.1:9002   stream 明文下游（proxy_protocol）
127.0.0.1:9444   stream TLS 下游（proxy_protocol）
127.0.0.1:9001   旧端口，仅回环（保留作秒级回滚兜底）
127.0.0.1:9443   旧端口，仅回环（保留作秒级回滚兜底）
```

回归验证（重启后）：

| 项 | 结果 |
|---|---|
| `https://8001/` `/admincc/` `/cc/` | 全部 200，标题 `屿禾工坊` |
| `https://8443/` | 200（公网入口不受影响） |
| `192.168.50.4:9001` / `:9443` | **REFUSED**（已从非回环收掉） |
| `127.0.0.1:9001` / `:9443` | 200（回滚兜底仍在） |
| ws:// 探针 | stream → 9002，Python 日志 `117.67.194.234` |
| wss:// 探针 | stream → 9444，Python 日志 `117.67.194.234` |

### 4. 真实设备闭环确认

```
14:45:46  127.0.0.1       14:c1:9f:d1:33:48   改前
14:46:40  127.0.0.1       14:c1:9f:d1:33:48   改前
15:00:49  117.67.194.234  14:c1:9f:d1:33:48   改后 ← 真实设备拿到真实 IP
```

原来是 `127.0.0.1`，现在能直接看到设备公网 IP，**可以按 IP 定位问题了**。

---

## 五、备份与回滚

| 文件 | 备份 |
|---|---|
| `/etc/nginx/nginx.conf` | `nginx.conf.bak-20261009T064900Z` |
| `sites-available/xiaozhi-manager` | `xiaozhi-manager.bak-20261009T070300Z` |
| `sites-available/xiaozhi-device-pp` | `xiaozhi-device-pp.bak-20261009T070300Z` |

**回滚真实 IP**：把 `nginx.conf` 里 stream 的 map 改回 `127.0.0.1:9001 / 9443`，
删掉 `proxy_protocol on;`，然后 **`systemctl restart nginx`**（reload 不行，见上）。

**回滚端口**：把 `xiaozhi-manager` 里的 `listen 127.0.0.1:9001` / `127.0.0.1:9443 ssl`
改回 `listen 9001` / `listen 9443 ssl`，restart。

## 六、小提示

`app.log` 目前只保留 14 天。若要更长的保留期（比如跨月追查某台设备的历史问题），
改 `/etc/logrotate.d/xiaozhi` 里的 `rotate 14` 即可。

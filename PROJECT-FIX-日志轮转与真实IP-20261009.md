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

## 四、遗留建议（未做，需你点头）

1. **9001 / 9443 仍公网暴露**，设备现在走 9002/9444 了，这两个端口对设备已无必要。
   改成 `listen 127.0.0.1:9001` 可收掉公网面，但**要先确认没有外部客户端直连**（我曾看到扫描流量，
   但不确定是否有合法直连）。
2. **9002/9444 与 9001/9443 的 location 是两份拷贝**，改 `xiaozhi-manager` 时必须同步改
   `xiaozhi-device-pp`，否则两边行为会漂移。更彻底的做法是把公共 location 抽到
   `/etc/nginx/snippets/` 里 `include`，但这次为了可回滚没动。
3. 当前 `app.log` 只保留 14 天。若要更长保留期（比如按设备追查历史问题），改 `rotate 14` 即可。

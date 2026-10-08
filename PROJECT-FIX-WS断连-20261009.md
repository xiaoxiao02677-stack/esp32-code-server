# WebSocket 频繁断开 —— 根因定位与修复

> 日期：2026-10-09 03:00 ｜ 排查方式：6 个 agent 并行 + 线上取证 + 固件源码交叉验证
> 代码树：`G:/demo/21_xiaozhi/code-server-mirror/`（服务端）· `G:/demo/21_xiaozhi/code/xiaozhi-esp32`（固件）
> 状态：**已修复并上线验证完毕**

---

## 一、先回答你问的两个数字

| 问题 | 答案 |
|---|---|
| **WS 最多并发多少？** | **实测 800 并发全部成功，未触顶**（100/200/400/800 逐级加压，失败 0）。代码层**没有任何并发限制**（无 semaphore / 连接池）。<br>修复前理论硬顶约 **950** 条 —— 瓶颈是文件描述符：服务端 soft nofile 仅 **1024**，实测每连接约 1.05 个 fd。修复后 `LimitNOFILE=65535`，fd 不再是瓶颈，真实上限转为内存与每连接 5 线程的线程池（`core/connection.py:126`）。 |
| **WS 关闭一个空闲会话是多少秒？** | **3660 秒（61 分钟）**。<br>构成：`close_connection_no_voice_time` = **3600**（来自 manager-api 的 `sys_params` id=302）**+ 60** = 3660，见 `core/connection.py:186-188`。<br>第一道 3600s 播一句结束语再关，第二道 3660s 硬关；超时检查每 **10 秒** 轮询一次。<br>⚠️ 改本地 `config.yaml` **无效**：只要 `data/.config.yaml` 配了 `manager-api.url`，本地 config 会被整层丢弃（`config/config_loader.py:42-46`）。要改请改「参数管理」或 DB `sys_params`。<br>实测：空闲 420s 未关闭，与 3660s 吻合。历史上出现过 180s（120+60），是当时 API 没下发该参数、落回代码默认值 120 所致。 |

---

## 二、为什么会频繁断开（按贡献度排序）

### 🥇 根因 1：服务进程死了 6.5 小时，systemd 完全没管（P0）

```
$ systemctl status xiaozhi-server
Active: inactive (dead) since Thu 2026-10-08 20:06:27 CST; 6h ago
Main PID: 2506 (code=exited, status=0/SUCCESS)
```

unit 写的是 `Restart=on-failure`。而 `app.py` 收到 SIGTERM/SIGINT 后走 `wait_for_exit()` 正常返回，**以退出码 0 结束** —— **`on-failure` 对退出码 0 不生效**。于是 20:06 退出后再没人拉起，直到 02:39 我手工启动。

后果（nginx access.log）：01 点 **16 次 499** + 02 点 **5 次 502**，设备每 10 秒重试一次，全部失败。

### 🥈 根因 2：后端抖一次，在线设备被判死刑（P0，代码 bug）

`core/connection.py:833`（原实现）：

```python
except Exception as e:
    self.need_bind = True          # ← 把「网络抖动/接口超时」当成「设备未绑定」
```

而 `_check_timeout()` 对 `need_bind=True` 的连接，**改用 `first_activity_time`（连接建立时刻）做倒计时**：

```python
last_activity_time = self.last_activity_time
if self.need_bind:
    last_activity_time = self.first_activity_time   # ← 之后永不续期
if current_time - last_activity_time > self.timeout_seconds * 1000:
    await self.close(self.websocket)
```

**语义错配**：`need_bind` 本意是"设备未注册"，但取配置失败也会置 True。于是 —— **正在正常对话的设备，到点必被踢**。manager-api 抖一次，该时间窗内建立的所有连接全部中招，表现为"用着用着就断，然后马上重连"。

### 🥉 根因 3：端到端零心跳，两端都不知道对方死没死（P1）

| 环节 | 状态 |
|---|---|
| 服务端协议层 | `websocket_server.py:81` `ping_interval=None` —— **完全不发 Ping** |
| 服务端应用层 | `sys_params` id=311 `enable_websocket_ping=false` —— 设备 ping 也丢弃、不回 Pong |
| 固件协议层 | 从不做 WS Ping（底层库 `web_socket.cc:258` 有 `Ping()` 但**零调用**） |
| 固件 TCP 层 | `sdkconfig` 中 `KEEPALIVE` 出现 **0 次**，无 `SO_KEEPALIVE` |
| 固件协议文档 | `docs/websocket.md` 全文无心跳章节 |

固件唯一的收包超时是 120 秒（`protocol.cc:112-121`），且它**不主动关连接**，只让 `IsAudioChannelOpened()` 返回 false。结果：半开连接（掉电/断网/NAT 回收）**服务端要等 3660 秒才发现**。

### 4. nginx 磁盘配置非法（P0 隐患，随时可能爆炸）

`console-v2` 那段被**重复粘贴了 3 份**（原文件 32-47、49-64、66-81 行），导致：

```
$ nginx -t
[emerg] duplicate location "/" in /etc/nginx/sites-enabled/xiaozhi-manager:51
```

当前 nginx 还在跑，是因为 worker 加载的是 19:53 的旧配置，而磁盘文件 20:30 才被改坏。**这意味着：任何一次 `nginx -s reload` 都会失败；服务器一旦重启，nginx 直接起不来 → 全线断连。**

### 5. 文件描述符 1024（P2）

服务端 soft nofile 仅 1024，理论并发硬顶 ~950。已放开。

---

## 三、已排除的嫌疑（别再往这些方向查）

| 嫌疑 | 实测结论 |
|---|---|
| nginx `proxy_read_timeout` 60s 默认值 | ❌ **不是**。显式配置为 **3600s**（`sites-available/xiaozhi-manager:21-22`），实测空闲 95s 连接未断 |
| nginx stream 层超时 | ❌ `proxy_timeout 3600s`（`nginx.conf:97`） |
| CPU / 内存 / 负载 | ❌ CPU 99.2% idle，可用内存 3417MB，负载 0.21，无 OOM kill |
| 固件播完 TTS 主动关连接 | ❌ **不存在**。`application.cc:666-680` 只切状态机，不碰连接；`docs/websocket.md` 也明确 TTS stop 不关 socket |
| 固件 idle / 省电关连接 | ❌ `application.cc:1447-1461` `CanEnterSleepMode()` 显式挡住（通道开着不允许睡） |
| 固件等 PONG 超时 | ❌ 固件从不发 ping，也没注册 `OnPong` |
| 服务端崩溃 | ❌ 日志中 `Traceback` / `Exception` / `Connection error` 均 **0 次** |
| 服务端主动超时踢人 | ❌ `连接超时，准备关闭` **0 次**（本窗口内） |

---

## 四、修复清单

| # | 文件 | 改动 | 性质 |
|---|---|---|---|
| 1 | `/etc/systemd/system/xiaozhi-server.service` | `Restart=on-failure` → **`Restart=always`**；新增 `LimitNOFILE=65535` | **P0 止血** |
| 2 | `xiaozhi-server/core/connection.py:833-846` | 取配置异常时 `need_bind=True` → **`False`**，交回可续期的 `last_activity_time`，并 `set()` 绑定完成事件 | **P0 代码 bug** |
| 3 | `xiaozhi-server/core/websocket_server.py:76-95` | `ping_interval=None` → **`ping_interval=30 / ping_timeout=60`**（可通过 `server.ws_ping_interval` / `ws_ping_timeout` 覆盖） | P1 保活 |
| 4 | `/etc/nginx/sites-available/xiaozhi-manager` | 删除重复的 2 份 console-v2 块（保留 1 份）；WS 段新增 `proxy_buffering off` / `proxy_request_buffering off` / `proxy_connect_timeout 10s` | **P0 隐患** |
| 5 | 运行方式 | 从手工 `setsid nohup` 切换为 `systemctl` 托管 | 运维 |

### 为什么心跳参数取 30 / 60

- **开启是安全的**：固件 `78__esp-ml307/src/web_socket.cc:392` 收到 Ping(0x9) 会**自动回 Pong(0xA)**，无需改固件。已交叉验证。
- **30s** 足以制造双向流量、防止 NAT/防火墙回收空闲连接（NAT 空闲超时通常 60~300s）。
- **60s 的 ping_timeout** 是刻意放宽 —— 弱网偶发丢包不会误杀健康连接；真正死掉的连接最多 **90 秒**内被回收（原来要 3660 秒）。
- 已知边界：Ping 帧**不会**刷新固件的 120s `last_incoming_time_`（固件只在收到文本/二进制帧时刷新，`websocket_protocol.cc:198`），所以服务端 Ping 保的是 NAT 与死连接检测，不替代固件侧重建通道逻辑。

---

## 五、验证结果

```
[1/5] 上传 Python 代码      connection.py / websocket_server.py  md5 一致，服务器 py_compile OK
[2/5] nginx                 nginx -t 通过（此前失败）→ reload → 8001/9001 正常监听
[3/5] systemd               Restart=always  LimitNOFILE=65535
[4/5] 切换托管              is-active: active，8000/8003 监听，Max open files = 65535
```

**保活实测（裸 socket 抓帧，不依赖 WS 库）：**

```
观察 100s（每收到 Ping 立即回 Pong，模拟真实固件）
  收到 Ping x3  发出 Pong x3
  Ping 到达时刻(s): [30.0, 60.0, 90.0]
  Ping 间隔(s): [30.0, 30.0]
  连接是否仍 OPEN: 是
→ 保活正常且不会误杀健康连接
```

**自愈实测（`Restart=always` 生效）：**

```
杀前 PID=58895   →   kill -9  →   12 秒后  杀后 PID=59727
✅ systemd 已自动拉起，systemctl is-active: active
```

**并发实测：**

```
soft nofile: (1024, 1048576)     ← 客户端自身限制
  N= 100  ok= 100  fail= 0   耗时=0.32s
  N= 200  ok= 200  fail= 0   耗时=0.49s
  N= 400  ok= 400  fail= 0   耗时=2.45s
  N= 800  ok= 800  fail= 0   耗时=5.66s
→ 800 并发全部成功，未触顶
```

**收尾健康检查：** 三个服务均 active；8000/8001/8002/8003/9001 全部监听；日志无 Traceback / ERROR；压测连接已全部释放（`ss :8000` 只剩 1 个 LISTEN，服务端 fd 15，线程 151，RSS 1.6GB —— 与基线一致）。临时脚本已清理。

---

## 六、残留建议（未改，需你决策）

1. **日志丢了现场**：`/tmp/xiaozhi-server.log` 用 `>` 覆盖写入，服务一重启历史就没了，无法回溯。建议改 `>>` 追加 + logrotate（systemd 的 `data/app.log` 已是 append，可考虑统一）。
2. **stream 层丢失设备真实 IP**：`nginx.conf:93-98` 的 `proxy_pass` 未配 `proxy_protocol`，日志里所有设备 IP 都是 `127.0.0.1`，无法按设备定位问题。
3. **日志里 session_id 全相同**，并发时无法区分连接归属；建议加 `conn_uid`。
4. **`_background_initialize()` 是 fire-and-forget**（`connection.py:250`），不受 `stop_event` 约束，断连后仍在跑（实测断连后还打印 `TTS上报线程已启动`、函数列表打印两次）。重连风暴时会状态踩踏。
5. **每连接一个 `ThreadPoolExecutor(max_workers=5)`**（`connection.py:126`），高并发下线程数 = 连接数 × 5，是放开 fd 之后的下一个瓶颈。
6. **`data/.mcp_server_settings.json` 缺失**（日志 WARNING 6 次）、**天气插件 Key 失效**（Authentication failed）、**聊天标题上报「智能体未找到」**（3 次）—— 均不导致断连，但建议一并处理。

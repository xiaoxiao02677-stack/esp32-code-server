# 服务器蠕虫入侵事件报告(XMRig 挖矿木马)

- **目标主机**:sandyun.top:22223 → 192.168.50.20(Ubuntu 24.04,`demo-VMware20-1`,测试环境)
- **处置时间**:2026-10-13 17:25–17:35 (GMT+8)
- **事件等级**:高(已获 root 权限的入侵 + 挖矿木马 + systemd 持久化)
- **处置结果**:✅ 已彻底清除,已重启后仍存活的风险点已排除(持久化已拔除)

---

## 1. 结论摘要

入侵者通过 **SSH 弱口令爆破**成功登录 root,植入了一个 **XMRig 6.26.0 挖矿木马**及其**伪装成 `systemd-journald` 的看门狗/持久化组件**。木马吃满全部 CPU(2561%),对外连接矿池 `185.112.146.184:6280`。

用户此前手动 `kill` 并重启过,但恶意 **systemd unit 覆盖了系统同名服务**,导致**每次开机自动复活**——这正是"清不干净"的根因。

---

## 2. 攻击时间线

| 时间 (CST) | 事件 |
|---|---|
| 2026-10-13 15:07:34 | 攻击者 `209.97.136.238`(DigitalOcean)**用密码成功登录 root**(`Accepted password for root`) |
| 2026-10-13 15:07 起 | 同一 IP 持续爆破,累计 **2402** 次失败尝试 |
| 2026-10-13 16:14–16:15 | `/etc/ssh/sshd_config` 被改写;`/etc/systemd/system/systemd-journald.service` 与 `/usr/local/bin/systemd-journald` 落地 |
| 2026-10-13 16:15:16 | 恶意 unit + 木马二进制创建(**持久化植入点**) |
| 2026-10-13 16:xx | 用户察觉,`kill -9`、`rm /var/tmp/4035188231`、重启(历史记录可见) |
| 2026-10-13 16:59:02 | 重启后恶意 unit 把木马重新拉起(PID 1525 → 子进程矿机 3337) |
| 2026-10-13 17:33 | 本次处置:隔离并清除全部组件,恢复真实 journald |

---

## 3. 恶意指标 (IOC)

### 文件
| 路径 | 说明 | SHA256 |
|---|---|---|
| `/usr/local/bin/systemd-journald` | **看门狗/伪装木马**,3.82 MB,静态 ELF、无节头(加壳),权限 0700,非任何包所属 | `3c9a51fc92087d1b0d1cdc4aa8c51847b46de39a948a0844e12fd69d17cfd2e8` |
| `/dev/shm/1269538733` | **XMRig 6.26.0 矿机**,7.55 MB,静态 PIE | `78774375e567f22479880778fdbb20aa106c56ca37b1d0d3c075e9798066df88` |
| `/etc/systemd/system/systemd-journald.service` | **恶意持久化 unit**(覆盖系统同名服务) | `635789f649bde6fc1f0a2bb173e0b04e595b909a6c2b05c5da257ae86e5da5d9` |
| `/tmp/.ses` | 木马会话标记(纪元时间戳 + UUID) | `ba7e10922bf788141e0aaa2f4452a69579a150ab6fb6ebef19313ed12a108c8d` |
| `/var/tmp/4035188231`(历史) | 早期阶段的同族载荷(已被用户删) | — |

### 网络
- 攻击源 IP:**`209.97.136.238`**(爆破 + 成功登录)
- 矿池 C2:**`185.112.146.184:6280`**(矿机外联)

### 进程
- 看门狗:PID 1525 `/usr/local/bin/systemd-journald`(持有 30+ `pidfd`,监控/守护)
- 矿机:PID 3337 `/dev/shm/1269538733`(CPU 2561%)

### 关键恶意 unit 内容
```ini
[Unit]
Description=System Service for systemd-journald
After=network.target

[Service]
ExecStart=/usr/local/bin/systemd-journald
Nice=-20
Restart=always
RestartSec=3
KillMode=process

[Install]
WantedBy=multi-user.target
```
> 利用手法:该文件在 `/etc/systemd/system/` 中**覆盖**了 `/usr/lib/systemd/system/systemd-journald.service`。由于 `systemd-journald.socket` 属系统默认启用,socket 激活时启动的同名服务被劫持为恶意程序——因此开机必复活。

---

## 4. 处置动作(可回滚,均已备份)

备份目录:`/root/ir_quarantine_20261013T093320Z/`(含原件、哈希、`ps`/`ss` 现场快照)

1. 停止 `systemd-journald.socket` + `service`,阻断 socket 激活重生
2. `kill -9` 看门狗(1525)与矿机(3337)
3. 移出恶意 unit `/etc/systemd/system/systemd-journald.service` → `daemon-reload`
4. 删除载荷:`/dev/shm/1269538733`、`/usr/local/bin/systemd-journald`、`/tmp/.ses`
5. 恢复真实 journald(vendor unit,MainPID 运行 `/usr/lib/systemd/systemd-journald`)
6. 复查:无重生、无矿池连接、`/dev/shm` 空、`dpkg -V systemd openssh-server` 完好、负载回落

### 清除前后对比
| 项目 | 清除前 | 清除后 |
|---|---|---|
| 负载 (1 min) | 30.75 | 13.2 ↓(持续回落) |
| 恶意进程 | 1525 / 3337 | 无 |
| journald | `/usr/local/bin/systemd-journald`(假) | `/usr/lib/systemd/systemd-journald`(真) |
| 矿池连接 | 有 | 无 |
| 持久化 | 恶意 unit | 无 |

---

## 5. ⚠️ 待完成的安全加固(需决策)

1. **root 密码已泄露** → 必须立即修改(攻击者已知晓并成功登录过)
2. **SSH 配置被削弱**:当前 `PermitRootLogin yes` + `PubkeyAuthentication no` + 密码登录开启
   - 建议:恢复公钥登录、关闭密码登录、`PermitRootLogin prohibit-password`
3. **防火墙未启用**(ufw inactive,iptables 默认 ACCEPT),且 22 端口经 22223 转发暴露公网
   - 建议:封禁 `209.97.136.238`,启用 ufw,限制来源 IP
4. **建议重启一次验证**持久化已彻底拔除
5. 确认无用后,可删除隔离目录 `/root/ir_quarantine_20261013T093320Z/`

---

## 6. 备注

- 攻击者未新增系统用户(仅 root 为 uid0),未篡改 `/root/.ssh/authorized_keys`(仅用户本人的 gitee 公钥),未发现 `ld.so.preload` 或内核级 rootkit,系统包校验完好。
- 诱因:**公网暴露的 SSH + root 弱口令**。本次为纯机会型挖矿僵尸网络,非定向攻击。

---
*报告生成:2026-10-13 17:35 (GMT+8) | 处置方式:SSH 远程 + paramiko*

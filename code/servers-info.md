# 服务器信息汇总报告

> 生成时间：2026-10-24 21:33 | 来源：项目记忆（.workbuddy/memory/）全量梳理
> 涵盖：SSH 连接、yuhe 主站（生产/测试）、小七星链 8009、数据库、部署工具链

---

## 一、服务器连接总览

两台 VM 共用同一个域名入口 `sandyun.top`，靠 SSH 端口区分：

| 环境 | SSH 连接 | 主机名 | root 密码 |
|------|---------|--------|----------|
| **生产服** | `ssh -p 22222 root@sandyun.top` | sand-VMware20-1 | `Ymm6088.`（含结尾句点） |
| **测试服** | `ssh -p 22223 root@sandyun.top` | demo-VMware20-1 | `Ymm6088.`（同） |

⚠️ SSH banner 限流：paramiko/频繁连接会报 `Error reading SSH protocol banner`，等 8~15 秒重试即可（部署脚本建议带 10+5n 秒退避）。

⚠️ Git Bash 推送坑：`sftp_push.py` 硬编码 22222（生产）；推测试服必须 paramiko 显式 `connect(port=22223)`，曾发生误推生产事故。MSYS 环境传 `/` 开头参数需 `MSYS_NO_PATHCONV=1`。

---

## 二、生产服（22222）服务拓扑

### 1. yuhe 管理主站 —— 真实入口 **https://sandyun.top:8001/**

> 443 / 5001 端口是跳转页，不是前端！8001 必须 HTTPS（http 访问报 400）。

| 组件 | 位置 | 端口 | 说明 |
|------|------|------|------|
| Java 后端 | `/opt/xiaozhi/yuhe-esp32-api.jar` | 8002 | systemd `xiaozhi-manager-api`，外置配置 `/opt/xiaozhi/application-dev.yml`（只覆盖 URL/Tomcat/AES key） |
| Python 服务 | `/root/xiaozhi-server` | 8000 (WS) / 8003 (http) | WebSocket 语音链路 + HTTP API |
| 管理前端 | `/var/www/console-v2/{app,admin}` | nginx 8001 | 两目录同批更新（app/ 根路径 + admin/） |
| MySQL | 本机 | - | **root/123456**（jar 内置），库 `xiaozhi_esp32_server` |
| Redis | 本机 | - | 配置缓存，改 sys_params 后须 `DEL server:config` |

- **部署顺序**：Java → Python（三文件同批）→ Web（验 inode 确认生效）
- MySQL datetime 为 UTC，比北京时间早 8 小时
- 音色探测已上线（Python `tts_voice_probe_handler.py`，46 个百炼 3.1 音色）

### 2. 生产测试口

- 测试 OTA/WS 走 8144 明文（见测试服一节，实际在测试服）

---

## 三、测试服（22223）服务拓扑

> 10-23 已重组目录结构，注意新路径。

| 组件 | 位置 | 说明 |
|------|------|------|
| Python 服务 | `/root/yh/app/xiaozhi-server` | 测试版语音链路 |
| Java 后端 | `/root/yh/deploy/opt-xiaozhi/yuhe-esp32-api.jar` | **多一层 deploy 目录，忘了 cp 就会白改**；dev profile |
| 前端 | `/var/www/console-v2/admin` | 单端点布局 |
| MySQL | debian-sys-maint 账号 | 凭据在 `/etc/mysql/debian.cnf`（root 免密不可用；与生产凭据不同），库同名 `xiaozhi_esp32_server` |
| 外部入口 | https://sandyun.top:8101 / http://8144 | 8144 是 OTA/WS 明文口 |
| YH 心跳 | 8199 | 设备心跳端口 |

- 测试程序化登录链：`uuid → captcha → Redis 读值 → SM2 加密 → POST /user/login → token UPDATE sys_user_token`（冒烟时 token 须同时顺延 expire_date）
- 活跃超管账号是 `demo`（不是 admin）
- 测试服库名 `xiaozhi_esp32_server`（不是 yuhe）；音色列名 `languages`（复数）；订单表 `order_table`（shipping_status 语义 0待处理/1已发货/2已完成/3已取消）

---

## 四、数据库对照表

| 项 | 生产（22222） | 测试（22223） | 8009（生产机上） |
|----|--------------|--------------|------------------|
| 类型 | MySQL | MySQL | SQLite |
| 凭据 | root / 123456 | debian-sys-maint（/etc/mysql/debian.cnf） | 文件型，无凭据 |
| 库/文件 | xiaozhi_esp32_server | xiaozhi_esp32_server | /opt/qxlik-api/data/qxlik.db |
| 特殊 | datetime UTC 早 8h | Redis 存验证码/token | 无 sqlite3 CLI，用 python3 模块 |

---

## 五、部署工具链（本地 Windows）

| 工具 | 路径/用法 | 目标 |
|------|----------|------|
| `sftp_push.py` | `python sftp_push.py <local> <remote>` | **生产 22222**（硬编码端口） |
| `ssh_run_test.py` | `python ssh_run_test.py "cmd"` | 测试 22223 |
| 临时部署脚本 | `.workbuddy/*.py`（paramiko 直连） | 按脚本内 PORT 区分 |
| mvn 构建 | `JAVA_HOME=/d/INSTALL/jdk21` + `/d/INSTALL/maven/mvn/bin/mvn.cmd` | Java 模块（OOM 时 `MAVEN_OPTS=-Xmx1024m`） |
| 前端构建 | vite（admin 模式 base=/admincc/ → dist-admin；默认 base=/ → dist） | console-v2 |

---

## 六、关键操作红线（踩过的坑）

1. **配置真源是 Java `/config/server-base`**——config.yaml 大部分键无效；改系统参数走 `sys_params`：先 UPDATE 再 `redis-cli DEL server:config` 再重启
2. **Java 模型配置改 DB 后**必须 `DEL model:data:{id} model:name:{id}` 缓存
3. **Liquibase 红线**：勿改已执行的 changeset
4. **前端两目录同批更新**（生产 app/ + admin/），验 inode 确认
5. **SSH banner 限流**：频繁连接触发，等 8~15s 重试
6. **exec_command 引号地狱**：bash 嵌套双引号截断 + $ 展开，复杂 SQL/Python 一律 SFTP 传脚本文件再执行
7. **8001/8101 必须 HTTPS**；8009 是 HTTP
8. **测试服 deploy 目录中间层**：jar 改了不 cp 等于白改

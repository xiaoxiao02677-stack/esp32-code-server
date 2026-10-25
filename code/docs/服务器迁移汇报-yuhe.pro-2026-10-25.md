# 服务器迁移汇报：服务器A → 服务器C（yuhe.pro）

**日期**：2026-10-25
**状态**：✅ C 端迁移完成，全链路验证通过；最终架构为 **sandyun.top 主 / yuhe.pro 兜底**

> **📌 2026-10-25 最终裁决**：yuhe.pro 当前线路延迟偏大，**不做固件主站**。
> 固件主连 sandyun.top（服务器A），yuhe.pro（服务器C）全套服务保持运行，
> 作为 OTA / WebSocket 的兜底站点。兜底机制代码已随本次裁决恢复到源码树
> （从补丁选择性重放，机制细节见第四节）。C 侧配置零改动。
> 完整迁移改动备份：`code/docs/patches/yuhe-pro-primary-fallback-20261025.patch`。

---

## 一、迁移总览

| 项 | 迁移前（服务器A） | 迁移后（服务器C） |
|---|---|---|
| 域名 | sandyun.top:8001（非标端口） | **yuhe.pro:80/443**（HTTPS 标准端口，HTTP 自动 301 跳转） |
| 控制台入口 | https://sandyun.top:8001/ | **https://yuhe.pro/console/** |
| Java API | sandyun.top:8002 | https://yuhe.pro/yuhe/（反代本地 8002） |
| Python WS | sandyun.top:8001/yuhe/v1/ | **wss://yuhe.pro/yuhe/v1/**（反代本地 8000） |
| 视觉/mcp | sandyun.top:8003 直连 | https://yuhe.pro/mcp/（反代本地 8003） |
| OTA 下载 | sandyun.top:8002/yuhe/ota/ | https://yuhe.pro/yuhe/ota/ |
| YH 心跳（TCP/UDP 12399） | sandyun.top:12399（**固件主用，保持**） | yuhe.pro:12399（已验证可用，备胎） |
| WS 旁路 UDP 心跳 | sandyun.top:8002/udp（**固件主用**） | yuhe.pro:8002/udp（已放行，备胎） |
| 固件主连地址 | — | **仍是 sandyun.top**（见第四节，C 只作 OTA/WS 兜底） |
| 服务器A | — | **配置保持不动，固件主连 + 兜底双角色** |
| 宝塔面板 | — | 网站目录 /www/wwwroot/yuhe.pro，nginx 站点由宝塔管理 |

服务器C 与原有**屿禾工坊商城**（WordPress，根路径）共存于同一个 nginx 站点 `yuhe.pro`，通过 `^~` 前缀 location 分流，商城不受影响。

---

## 二、服务器C 部署清单

| 组件 | 位置 | 说明 |
|---|---|---|
| Java manager-api | /opt/yuhe/yuhe-esp32-api.jar（120M） | systemd: `yuhe-manager-api`，端口 8002 |
| Python xiaozhi-server | /opt/yuhe/xiaozhi-server（3.4G 含 venv+models） | systemd: `yuhe-xiaozhi-server`，端口 8000/8003 |
| 外置配置 | /opt/yuhe/application-dev.yml | 仅覆盖 datasource（宝塔 MySQL 密码）与 api-key-secret |
| 数据库 | 宝塔 MySQL `xiaozhi_esp32_server`（2.2G，全量导入） | 服务名 **mysqld**（宝塔专用，非 mysql） |
| Redis | 宝塔自带，本地 6379 无密码 | 配置缓存/验证码/壁纸回执 |
| OTA 固件文件 | /opt/yuhe/uploadfile/（40 个 .bin，57M） | Java 工作目录相对路径，与 A 完全一致 |
| 前端控制台 | /www/wwwroot/yuhe.pro/console/（700K） | console-v2 最新版，base=/console/ 构建 |
| 固件烧录工具 | /www/wwwroot/yuhe.pro/console-v2/firmware-flash/ | 保留原路径 /firmware-flash/ |
| nginx 站点 | 宝塔 vhost `yh.conf`（备份 yh.conf.bak-migrate-10250635） | 商城与 yuhe 服务共用 |
| TLS 证书 | LetsEncrypt yuhe.pro（有效期至 2027-01-19） | 商城既有证书直接复用 |

### systemd 自启（全部 enabled）

- `yuhe-manager-api`：`Requires=mysqld.service redis-server.service`（注意宝塔服务名是 mysqld）
- `yuhe-xiaozhi-server`：`Restart=always`（对齐 A 的断连修复经验）、`LimitNOFILE=65535`

### 环境排障记录（服务器C）

1. **redis 启动失败**（libjemalloc.so.2 exit 127）：/usr/local/lib 下损坏的 jemalloc 与 ldconfig 优先级冲突 → 重装 libjemalloc2 + 移除损坏副本
2. **Java dependency job failed**：systemd 单元误写 `mysql.service` → 改为宝塔的 `mysqld.service`
3. **MySQL root 密码**：宝塔存储于 /www/server/panel/data/default.db（sqlite config 表 mysql_root 列）

---

## 三、全链路验证结果（全部通过）

### 公网 HTTPS（从服务器A 外部视角访问 yuhe.pro）

| 验证项 | 结果 |
|---|---|
| https://yuhe.pro/console/ 控制台入口 | 200 |
| /console/assets/index-*.js 静态资源 | 200 |
| /yuhe/agent/list 管理 API | 200 |
| /yuhe/user/captcha 验证码接口 | 200（PNG 图片 + Redis 落码） |
| /firmware-flash/ 固件烧录工具 | 200 |
| 商城首页（根路径） | 200 |
| http://yuhe.pro/* → https | 301 跳转正确 |
| TLS 证书 | CN=yuhe.pro，LE 签发，2027-01-19 到期 |

### 设备链路（模拟设备实测）

| 验证项 | 结果 |
|---|---|
| 设备 OTA check（已激活 MAC） | ✅ 下发 `websocket.url = wss://yuhe.pro/yuhe/v1/` |
| WS 升级握手（wss://yuhe.pro/yuhe/v1/） | ✅ HTTP 101 |
| Python 服务启动 | ✅ WS 8000 / HTTP 8003 / TCP+UDP 心跳 12399 / WS-UDP 8002 |
| Java 服务启动 | ✅ 8002 监听，/yuhe/ 与 /xiaozhi/ 双路径 200 |
| SM2 登录链路 | ✅ 验证码 → SM2 加密 → 解密比对（密码错报 10004，证明链路通） |
| /mcp/vision 反代 | ✅ 200 |

### 服务器A 兜底确认

- xiaozhi-manager-api / xiaozhi-server 均 active，前端 200
- 全部配置、systemd 单元、nginx **零改动**（mtime 均为历史时间）

---

## 四、固件改造（主 sandyun.top + 兜底 yuhe.pro）

改造文件（`hardware/sets/yuhe-esp32/main/`）：

| 文件 | 改动 |
|---|---|
| `Kconfig.projbuild` | 新增 `OTA_FALLBACK_URL`、`WEBSOCKET_FALLBACK_URL` 两个配置项（默认空） |
| `ota.cc` | `GetCheckVersionUrl()` 支持兜底切换；`ReportPrimaryResult()` 连续 3 次失败（5xx/连接失败，4xx 不计）切兜底，成功恢复主 URL |
| `ota.h` | 新增 `ReportPrimaryResult`/`IsFallbackActive` 声明与状态成员 |
| `protocols/websocket_protocol.cc` | `OpenAudioChannel()` 主 URL 连接失败时重建 websocket 连兜底地址；`SetupWebsocket()` 统一鉴权头与回调 |
| `protocols/websocket_protocol.h` | 新增 `SetupWebsocket` 私有声明 |
| `build.py` | prod 环境：主 `http://sandyun.top:8002/yuhe/ota/` + `CONFIG_YH_SERVER_HOST="sandyun.top"`，兜底 `https://yuhe.pro/yuhe/ota/` + `wss://yuhe.pro/yuhe/v1/`；`warn_stale_build_dir` 兼容双域名产物识别 |
| `ota_publish.py` | `DEFAULT_SERVER` 保持 `http://sandyun.top:8002/yuhe`（与固件主连一致），验证码从 A 的 Redis 读 |
| `README.md`（sets） | 环境表更新：生产主 sandyun.top（含 yuhe.pro 兜底说明）、YH 心跳 sandyun.top:12399 |

### 兜底机制说明（最终架构：固件主连 sandyun.top，yuhe.pro 作冗余）

- **OTA**：主 `http://sandyun.top:8002/yuhe/ota/`；连续 3 次失败（阈值 `kPrimaryFailThreshold=3`）自动切 `https://yuhe.pro/yuhe/ota/`，任一次成功自动恢复主地址
- **WebSocket**：主地址由 A 下发（`ws://sandyun.top:8001/yuhe/v1/`）；连接失败回退 `wss://yuhe.pro/yuhe/v1/`（单次回退，下次连接仍先试主）
- **YH 心跳（TCP 12399）**：主用 sandyun.top:12399（与迁移前完全一致）；yuhe.pro:12399 已验证可用（HELLO→HEARTBEAT 闭环），纯 TCP 无自动回退
- **宏未配置时**（如旧 sdkconfig）：代码内 `#ifndef` 兜底空串，行为与旧固件完全一致，零风险
- **注意**：C 的 sys_params 当前指向 yuhe.pro 自己（`server.websocket=wss://yuhe.pro/...`）——设备只有 OTA 切到 C 时才会拿到 C 的地址，主连 A 时不受影响；若希望 C 作纯兜底镜像，可把 C 的 sys_params 改回 sandyun.top（本次未改，保持 C 自洽）
- **域名迁国内规划**：yuhe.pro 后续备案迁国内后延迟下降，届时固件主连可再切回 yuhe.pro（只改 build.py 一行 + 重烧）

### 验证状态

- ✅ 语法检查（yh_syntax_check.py）：5 文件全部 OK
- ✅ 差异审计（sets_diff_audit.py）：白名单外差异 0（3 项本轮改动已入白名单并写明理由）
- ⏳ **固件编译 + 烧录：由用户手动执行**（`build.py --server prod`），建议先烧一块测试板验证兜底切换

---

## 五、前端部署决策（重要变更说明）

1. **最初部署的是 manager-web 旧版**（vue-cli，10-10 构建）——后发现 A 上真正在用的是 **console-v2**（vite，10-24 构建，屿禾工坊控制台），已改用本地 `yh/console-v2` 源码重新构建部署
2. console-v2 的 `vite.config.js` 已支持 `VITE_PUBLIC_BASE` 环境变量（默认 `/`，构建时传 `/console/`），构建产物与 A 上运行版同源（JS hash 一致）
3. console-v2 单构建内含全部路由（顾客端 + 管理端 32 模块），A 上旧双构建（app/admincc）无需复刻
4. 前端 API 基址 `/yuhe`（api.js `API_BASE='/yuhe'`）→ 已配 nginx `/yuhe/` 反代；兼容保留 `/xiaozhi/` 反代（Java 双路径同响应）
5. 登录分流由后端 `defaultRouteAfterLogin` 完成（超管→/admin，普通→/customer），无 admincc 依赖

### 关键配置点（服务器C）

- **`.config.yaml`**（Python data/）：`vision_explain: https://yuhe.pro/mcp/vision/explain`、`public_audio_base_url: https://yuhe.pro`、websocket 同步 wss、auth_key/secret 与 DB 一致
- **config_loader.py 白名单补丁**：透传 `public_audio_base_url`（原白名单会丢弃该键，推送音频会退回 sandyun.top 旧地址）
- **nginx location（yh.conf 内，全部 `^~` 前缀**——商城配置里有 WordPress 静态资源正则，不加 `^~` 会被抢走）：
  - `/console/` → 静态（try_files SPA 兜底）
  - `/yuhe/v1/` → 127.0.0.1:8000（WS 升级透传）
  - `/yuhe/`、`/xiaozhi/` → 127.0.0.1:8002
  - `/mcp/`、`/audio/`、`/tmp/` → 127.0.0.1:8003

---

## 六、遗留事项与注意事项

### 需要用户处理

1. **固件编译烧录**：`build.py --server prod` 构建 **sandyun.top 主 + yuhe.pro 兜底**固件（用户手动执行），建议先烧一块板实测
2. **老设备切换**：老固件（烧着 sandyun.top 主连的）**无需任何操作**，行为不变；新固件烧录后获得兜底能力（主连失败自动切 yuhe.pro）
3. **音色探测等依赖公网 8003 直连的功能**：C 侧已统一走 https://yuhe.pro/mcp/（vision/audio/websocket 三处已修）；主链路仍在 A 的 8003，不受影响

### 服务器C 维护要点

- 宝塔 MySQL 服务名是 `mysqld`（systemd 单元已正确引用）
- MySQL root 密码在宝塔 default.db；Java 外置配置 application-dev.yml 已写入
- 商城 WordPress 与 yuhe 服务共用 yh.conf——**宝塔面板里改站点配置时注意保留 yuhe location 块**（备份在 yh.conf.bak-migrate-10250635）
- TLS 证书 2027-01-19 到期（宝塔可自动续期）
- **ufw 新增放行**：12399/tcp+udp（YH 心跳）、8002/udp（WS 旁路心跳）——宝塔面板防火墙与 ufw 是两套，如果面板里也开了防火墙需同步放行
- YH 心跳服务在 Python 进程内（core/heartbeat.py）：TCP+UDP 双协议 12399 + WS 旁路 UDP 8002，重启 `yuhe-xiaozhi-server` 即可

### 服务器A（主站）

- **零改动**，继续运行。sandyun.top:8001/8002/8003 全部保留，固件主连 + YH 心跳都在 A
- 设备侧：A 故障期间固件自动切 yuhe.pro 兜底；C 的 OTA 下发的是 C 自己的地址（sys_params 自洽），设备会留在 C 直到某次主 URL 成功恢复 A
- yuhe.pro 域名备案迁国内、延迟下降后，可把固件主连切到 C（只改 build.py 一行 + 重烧）

---

## 七、验证数据汇总

| 指标 | 值 |
|---|---|
| 服务器C 内存占用 | Python 3.1G / Java 483M / 系统总 5.4G（可用 2.3G，8G 机器） |
| 磁盘 | 27G / 78G（34%） |
| DB 大小 | 2.2G（13 台设备 + 40 固件记录） |
| 服务自启 | 4/4 enabled + active |
| 固件白名单外差异 | 0 |
| 语法检查 | 5/5 通过（ota/WS）+ 2/2（yh_protocol 复核） |
| YH 心跳实测 | yuhe.pro:12399 HELLO→HEARTBEAT→离线闭环成功 |

# 生产 server.secret 轮换操作清单（P0-1）

> 状态：操作包已就绪，**轮换本体需人工在部署机执行**（时间窗 00:00–07:00）。
> 本清单与 `.workbuddy/secret-rotation/`（e-secret-ops 产出）配套使用，此处为入口索引 + 镜像侧已完成的兜底动作。

## 一、背景事实（已核实）

- secret 当前值 `2d7b6bde-…` 明文存在于两处：Python `xiaozhi-server/data/.config.yaml:9` 与 MySQL `xiaozhi_esp32_server.sys_params`（param_code='server.secret'）。
- 该 secret 是 **Python↔Java 服务端互调密钥**（manage_api_client Bearer / ServerSecretFilter）。设备固件不持有（已核实：`xiaozhi-esp32/main` 全量 grep `secret`/`SERVER_SECRET` 零命中），轮换不影响设备连接。
- 镜像 git 仓（code-server-mirror，单提交 31c20d1，无 remote）init 提交已含明文 secret → 需清史。

## 二、镜像侧已完成（本轮）

| 动作 | 文件 |
|---|---|
| .gitignore 入库兜底 | `xiaozhi-server/.gitignore`（新增，含 `data/.config.yaml`） |
| 配置模板（secret 占位符） | `xiaozhi-server/data/.config.yaml.example`（新增） |

## 三、部署日人工执行（按序）

1. **轮换**：`.workbuddy/secret-rotation/rotate-secret.sh` —— 双端同步换新 UUID + 清 Redis 缓存键 + 重启双服务 + 401/200 冒烟（8003 仅 loopback，须部署机本机跑）。
2. **清史**：`.workbuddy/secret-rotation/clean-history.md` —— `.gitignore` 已就位 → `git rm --cached data/.config.yaml` → `commit --amend`（单提交必须 amend）→ `reflog expire + gc --prune=now`；amend 后 31c20d1 基线作废，AOCI 基线需重取 HEAD。
3. **回滚**：`.workbuddy/secret-rotation/runbook.md` —— 从 `/root/backup/secret-rotation/$TS/` 恢复旧值 + 反向冒烟。
4. **知会**：轮换完成后更新团队口径（新 secret 分发渠道、qa_memory AUTH_KEY 同步）。

## 四、风险提示

- ServerSecretFilter 走 `fromCache=true`（Redis 优先）：脚本已含清缓存步骤；无 redis-cli 时以「旧 secret 冒烟 401」为兜底判据。
- 轮换窗口避开 QA e2e 时段（该套件会重启 xiaozhi-server 两次）。
- 备份目录含明文新旧 secret（已 chmod 600），建议加密离线留底。

# server.secret 轮换总 Runbook（P0-1）

> 操作包：`rotate-secret.sh`（部署机执行）＋ `clean-history.md`（本地 git 仓库执行）。
> **所有步骤均需人工在对应环境执行，本操作包制作阶段零执行。**
> 事实基线见 `.workbuddy/deploy_memory_v1.md`「环境事实」节；本文不重复。

---

## 一、执行总顺序（不可颠倒）

| 步 | 动作 | 环境 | 依据 |
|---|---|---|---|
| 1 | 部署机快照备份（复用 deploy_memory_v1 阶段 1 命令，mysqldump 全库） | 部署机 | 旧 secret 行也在 dump 里，双保险 |
| 2 | **轮换**：`bash rotate-secret.sh` | 部署机 | 先让旧值失效，后续清史即使泄露旧历史也无实害 |
| 3 | 冒烟通过 + 双端一致性复核（脚本 CHECK-7 已覆盖） | 部署机 | 旧 secret 必须 401 |
| 4 | **清史**：`clean-history.md` 步骤 1（git rm --cached + amend + reflog expire + gc） | 本地镜像 | 旧值仍在 init 提交 31c20d1 中 |
| 5 | **.gitignore 兜底**：由另一工程师建 `xiaozhi-server/.gitignore`（含 `data/.config.yaml`、`data/memory/`），入库 | 本地镜像 | 防再次手误 `git add -A` 带入库；本 runbook 只引用，不代建 |
| 6 | 团队知会（clean-history.md 步骤 4 模板）：新 secret 分发口径、qa_memory 脚本 AUTH_KEY 更新、基线 hash 作废 | 全团队 | — |

顺序理由：**先轮换后清史**——若先清史后轮换，清史→轮换的窗口期内旧值仍有效，且清史工具链（BFG 临时文件、filter-repo 对象库）会短暂留存旧值副本；先轮换让旧值作废，清史只剩「防未来泄露」意义。

## 二、时间窗选择（设备影响面）

- **推荐窗口：00:00–07:00 低峰**。轮换总时长约 5 分钟，其中服务停机约 1–2 分钟。
- 影响机制（按 deploy_memory_v1 链路事实推导）：
  1. `systemctl restart xiaozhi-manager-api`（约 25–30s）：nginx 8001 反代 8002 期间拒绝/超时。设备拉取配置（`/xiaozhi/v1/...` 配置端点）失败 → **固件按自身重连退避自动重试，无需人工干预**；连接中的设备 WS 断线，固件重连风暴集中在重启完成后 10s 内，8003/WS 端扛得住（9.9G 内存、单实例现状运行正常）。
  2. `systemctl restart xiaozhi-server`（约 5s）：已连 Python 侧的会话 WS 断开，设备重连后重建会话；正在进行的语音回合会丢失该轮上下文（记忆库在 `data/memory/*.db`，不随重启丢数据）。
  3. **secret 生效窗口风险**：DB/YAML 已更新但服务未重启的分钟级窗口内，Java 走 Redis 缓存仍可能按旧值放行（脚本第 5 步已清缓存键）；若设备固件内置旧 secret，轮换后设备上报/拉配置会 401，直至设备侧获取到含新 secret 的配置（或重新配网/OTA）。**开放项：需 team-lead 确认部署机固件的 secret 分发方式（是否随 config 下发）；若为烧录内置，则轮换日需同步固件重发，否则设备批量失联——这是本操作包最大的未知风险，窗口前必须关闭。**
- 避开：QA e2e 套件运行时段（会重启 xiaozhi-server 两次）、部署日阶段 3（Liquibase 启动窗口）。

## 三、回滚（旧 secret 从备份恢复）

任一 CHECK 失败即停（脚本自动），按以下步骤在部署机恢复（需人工执行）：

```bash
# 变量：TS=备份时间戳（ls /root/backup/secret-rotation/ 取最新）；OLD 值取自
# /root/backup/secret-rotation/$TS/old-secret.txt（即 2d7b6bde-…）
TS=$(ls -1 /root/backup/secret-rotation | sort | tail -1)
OLD=$(cat /root/backup/secret-rotation/$TS/old-secret.txt)

# 1) DB 回旧值
mysql -uroot -p123456 xiaozhi_esp32_server -e \
  "update sys_params set param_value='$OLD' where param_code='server.secret';"

# 2) YAML 回旧值（用备份整份覆盖，最安全）
cp -a /root/backup/secret-rotation/$TS/config.yaml.pre-update \
  /root/xiaozhi-server/main/xiaozhi-server/data/.config.yaml

# 3) 清 Redis 候选缓存键（同 rotate-secret.sh 第 5 步）
# 4) 重启两端
systemctl restart xiaozhi-manager-api && sleep 25
systemctl restart xiaozhi-server && sleep 5
systemctl is-active xiaozhi-manager-api xiaozhi-server

# 5) 反向冒烟：旧值应回到 200
curl -s -o /dev/null -w '%{http_code}\n' -H "Authorization: Bearer $OLD" \
  http://127.0.0.1:8003/api/memory/agents   # 预期 200
```

回滚成功后：清史（步骤 4）如果已执行，**不要**因此重推旧值入库；本地 init 提交可再 amend 回（.config.yaml 被 .gitignore 后本就不入库），团队知会改为「轮换暂停，维持旧值」。

## 四、关键风险点（随包发给 team-lead）

1. **Redis 缓存残留**（本操作包主要技术风险）：`ServerSecretFilter` 走 `getValue("server.secret", fromCache=true)`，改 DB 不清缓存则新旧值交叉期鉴权行为不确定——脚本第 5 步已处理，但服务器若无 redis-cli 时降级为「靠冒烟旧值 401 兜底」，兜底失败即回滚。
2. **设备侧 secret 分发方式未确认**（见二.3 开放项）：若固件内置，轮换=设备批量失联，需与固件重发联动。
3. 冒烟端点选 `/xiaozhi` 鉴权面的 `http://127.0.0.1:8003/api/memory/agents`（部署手册已验证 401/200 语义）；8003 仅 loopback 放行，冒烟必须在部署机本机跑，本地外网 curl 得到 403 属正常，勿误判。
4. `amend` 重写 init 提交后旧 hash `31c20d1` 作废，依赖该 hash 的基线比对（aoci baseline 280K baseline.json）需重新取 HEAD——知会事项。
5. 备份目录 `/root/backup/secret-rotation/` 中 `old-secret.txt` 是明文旧值，`rotation-RESULT.log` 含明文新值：均已 chmod 600，但**该目录本身在历史上明文泄露过的旧值治理语义下属于敏感资产**，需团队约定留底位置（建议加密离线存储），并避免 mysqldump 归档目录与 secret-rotation 目录被同路径 tar 外传。
6. 时间窗与 QA e2e（会两次重启 xiaozhi-server）冲突：轮换日避开 QA 批次（任务 #11/#17）。

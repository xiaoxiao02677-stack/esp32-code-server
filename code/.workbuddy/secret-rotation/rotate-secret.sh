#!/usr/bin/env bash
# =============================================================================
# rotate-secret.sh —— 生产 server.secret 两端同步轮换（MySQL sys_params + Python data/.config.yaml）
#
# 【必须人工在部署机（sandyun.top）执行】本脚本只随操作包落盘，制作阶段严禁运行。
# 参考 deploy_memory_v1.md「环境事实」：
#   - MySQL: root/123456, 库 xiaozhi_esp32_server, 表 sys_params (param_code='server.secret', param_value)
#   - Python 配置: /root/xiaozhi-server/main/xiaozhi-server/data/.config.yaml L9 (manager-api.secret)
#   - Java jar: /opt/xiaozhi/xiaozhi-esp32-api.jar, systemd: xiaozhi-manager-api / xiaozhi-server
#
# 关键事实（代码走读 2026-10-06 验证）：
#   - ServerSecretFilter.getServerSecret() = sysParamsService.getValue("server.secret", fromCache=true)
#   - fromCache=true 时先读 Redis sysParamsRedis，miss 才读库并回填。
#   - 因此改 DB 后若 Redis 里还留着旧值，鉴权仍按旧 secret 放行 → 必须清 Redis 键，
#     或由 systemctl restart xiaozhi-manager-api 重建缓存（缓存键 miss 后回填新值）。
#
# 幂等性：重复执行会再次生成新 secret 并完成轮换（旧值备份目录按时间戳隔离）。
#         若中途失败已停止，重跑前先看 /root/backup/secret-rotation/ 下最新备份，
#         用回滚命令（见 runbook.md）恢复后再重跑。
# 失败即停：set -euo pipefail + 每步 CHECK 校验点，任一步失败立即 exit 1。
# =============================================================================
set -euo pipefail

# ---------- 常量（与部署手册一致，勿改） ----------
PY_ROOT="/root/xiaozhi-server/main/xiaozhi-server"
CONFIG_FILE="${PY_ROOT}/data/.config.yaml"
DB="xiaozhi_esp32_server"
MYSQL="mysql -uroot -p123456"
PARAM_CODE="server.secret"
BACKUP_ROOT="/root/backup/secret-rotation"
TS="$(date +%Y%m%d-%H%M%S)"
BACKUP_DIR="${BACKUP_ROOT}/${TS}"
JAR="/opt/xiaozhi/xiaozhi-esp32-api.jar"

NEW_SECRET=""
OLD_SECRET=""
BACKUP_FILE=""

step() { echo; echo "===== [CHECK $1] $2 ====="; }
die()  { echo "!!! 失败：$1 —— 已停止，未执行后续步骤。请查看 runbook.md 回滚步骤。" >&2; exit 1; }

# ---------- 0. 前置检查（幂等，可安全重跑） ----------
step 0 "前置检查"
[ -f "$CONFIG_FILE" ] || die "配置文件不存在：$CONFIG_FILE"
command -v mysql >/dev/null || die "服务器缺少 mysql 客户端"
systemctl is-active xiaozhi-manager-api >/dev/null || die "xiaozhi-manager-api 未 active"
systemctl is-active xiaozhi-server >/dev/null || die "xiaozhi-server 未 active"

# 记录轮换前基线（双端一致性自检，防止带着脏状态开转）
OLD_SECRET=$($MYSQL -N -e "select param_value from ${DB}.sys_params where param_code='${PARAM_CODE};" \
  | tail -1)
OLD_SECRET_YAML=$(grep -m1 'secret:' "${CONFIG_FILE}" | sed 's/^[[:space:]]*secret:[[:space:]]*//' | tr -d '"'"'"'')
[ -n "$OLD_SECRET" ] || die "DB 中 ${DB}.sys_params(${PARAM_CODE}) 为空"
[ "$OLD_SECRET" = "$OLD_SECRET_YAML" ] \
  || die "轮换前双端不一致（DB=${OLD_SECRET} vs YAML=${OLD_SECRET_YAML}）——先人工对齐再执行本脚本"
echo "CHECK-0 通过：当前 secret 双端一致（${OLD_SECRET:0:8}… 前缀）"

# ---------- 1. 生成新 UUID ----------
step 1 "生成新 secret"
if NEW_SECRET="$(uuidgen 2>/dev/null)"; then :; else
  NEW_SECRET="$(python3 -c 'import uuid;print(uuid.uuid4())')" || die "uuidgen 与 python3 均不可用"
fi
[ "$NEW_SECRET" != "$OLD_SECRET" ] || die "生成的 secret 与旧值相同（概率事件，重跑脚本）"
echo "CHECK-1 通过：新 secret = ${NEW_SECRET:0:8}…（完整值仅写入备份与日志）"

# ---------- 2. 备份现值（先备份后改） ----------
step 2 "备份旧 secret"
mkdir -p "$BACKUP_DIR"
BACKUP_FILE="${BACKUP_DIR}/old-secret.txt"
printf '%s\n' "$OLD_SECRET" > "$BACKUP_FILE"
cp -a "$CONFIG_FILE" "${BACKUP_DIR}/config.yaml.bak"
$MYSQL "${DB}" -e "select param_code,param_value from sys_params where param_code='${PARAM_CODE};" \
  > "${BACKUP_DIR}/sys_params_row.bak"
ls -la "$BACKUP_DIR"
[ -s "$BACKUP_FILE" ] || die "备份文件为空"
echo "CHECK-2 通过：旧值已备份 → ${BACKUP_FILE}（回滚用；请同步下载到本地留底）"

# ---------- 3. 更新 MySQL sys_params ----------
step 3 "更新 MySQL sys_params"
$MYSQL "${DB}" -e "update sys_params set param_value='${NEW_SECRET}' where param_code='${PARAM_CODE};"
$MYSQL -N -e "select param_value from ${DB}.sys_params where param_code='${PARAM_CODE};" \
  | grep -qx "$NEW_SECRET" || die "DB 更新后读回值与新 secret 不符"
echo "CHECK-3 通过：DB 中 ${PARAM_CODE} 已为新值"

# ---------- 4. 更新 Python data/.config.yaml L9 ----------
step 4 "更新 data/.config.yaml"
cp -a "$CONFIG_FILE" "${BACKUP_DIR}/config.yaml.pre-update"
sed -i "s|^\([[:space:]]*\)secret:.*|\1secret: ${NEW_SECRET}|" "$CONFIG_FILE"
grep -m1 'secret:' "$CONFIG_FILE" | grep -qF "$NEW_SECRET" \
  || die "YAML 替换失败（sed 未命中，可能缩进/键名已变）——config.yaml.pre-update 仍在备份目录"
echo "CHECK-4 通过：YAML L9 已为新值（备份 ${BACKUP_DIR}/config.yaml.pre-update）"

# ---------- 5. 清 Redis 中 sys_params 旧缓存（关键！） ----------
# getValue(code, fromCache=true) 先查 Redis；不清缓存则 Java 重启后首次回填前仍可能命中旧值。
step 5 "清 Redis sys_params 缓存（旧值）"
REDIS_OK=1
if command -v redis-cli >/dev/null 2>&1; then
  # xiaozhi 默认未配 Redis 时 sysParamsRedis 为 no-op；若配了则键为 paramCode 本身或带前缀，逐个探
  for K in "sys_params:${PARAM_CODE}" "${PARAM_CODE}" "server.secret"; do
    redis-cli -h 127.0.0.1 del "$K" >/dev/null 2>&1 || true
  done
  echo "CHECK-5 通过：已 DEL 候选缓存键（redis-cli 可用）"
else
  REDIS_OK=0
  echo "CHECK-5 提示：服务器无 redis-cli。若 Java 侧 Redis 实际启用（application-dev.yml 有 spring.data.redis），"
  echo "        请人工确认已清缓存，否则继续并依赖步骤 7 冒烟的旧值 401 校验兜底（401 不通过则立即回滚）。"
fi

# ---------- 6. 重启两端服务（先 Java 后 Python；顺序与部署手册一致） ----------
step 6 "重启 xiaozhi-manager-api 与 xiaozhi-server"
systemctl restart xiaozhi-manager-api
sleep 25
systemctl is-active xiaozhi-manager-api | grep -qx active || die "xiaozhi-manager-api 重启后未 active（看 /opt/xiaozhi/logs/manager-api.log，按 runbook 回滚）"
systemctl restart xiaozhi-server
sleep 5
systemctl is-active xiaozhi-server | grep -qx active || die "xiaozhi-server 重启后未 active（看 data/app.log，按 runbook 回滚）"
echo "CHECK-6 通过：两端服务均 active"

# ---------- 7. 冒烟：新 secret 200 / 旧 secret 401 ----------
step 7 "鉴权冒烟（8003 loopback 端点 /xiaozhi/ 鉴权面）"
# 无 key 本机请求 → 401（路由存在且鉴权生效）
HTTP_NOKEY="$(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8003/api/memory/agents)"
[ "$HTTP_NOKEY" = "401" ] || die "无 key 请求返回 ${HTTP_NOKEY}（预期 401；404 说明路由未挂载，查日志）"

# 新 secret → 200（读库/缓存应为新值）
HTTP_NEW="$(curl -s -H "Authorization: Bearer ${NEW_SECRET}" -o /dev/null -w '%{http_code}' http://127.0.0.1:8003/api/memory/agents)"
[ "$HTTP_NEW" = "200" ] || die "新 secret 返回 ${HTTP_NEW}（预期 200）——若 401，说明 Redis 旧缓存未清或 Java 读库失败：先清缓存重试 curl；仍失败按 runbook 回滚"

# 旧 secret → 401（确认旧值已彻底失效）
HTTP_OLD="$(curl -s -H "Authorization: Bearer ${OLD_SECRET}" -o /dev/null -w '%{http_code}' http://127.0.0.1:8003/api/memory/agents)"
[ "$HTTP_OLD" = "401" ] || die "旧 secret 返回 ${HTTP_OLD}（预期 401）——旧值仍被放行，Redis 旧缓存残留！立即回滚或清缓存后重跑冒烟"

# 8000 基础探活（Python 侧进程健康）
curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8000/ >/dev/null || die "8000 无响应"
echo "CHECK-7 通过：无key=401 / 新secret=200 / 旧secret=401 / 8000 有响应"

# ---------- 8. 留痕 ----------
{
  echo "rotation ts=${TS}"
  echo "old_secret=${OLD_SECRET}"
  echo "new_secret=${NEW_SECRET}"
  echo "backup_dir=${BACKUP_DIR}"
  echo "smoke: nokey=401 new=200 old=401"
} > "${BACKUP_DIR}/rotation-RESULT.log"
echo
echo "===== 轮换完成 ====="
echo "新 secret 完整值：${NEW_SECRET}"
echo "备份目录：${BACKUP_DIR}（含旧值，chmod 600，务必同步一份到本地离线留底）"
chmod 600 "${BACKUP_DIR}"/old-secret.txt "${BACKUP_DIR}"/rotation-RESULT.log
echo "后续：① 提醒持有旧 secret 的脚本/QA 用例（deploy_memory_v1.md 各段、qa_memory 脚本默认 AUTH_KEY）改新值；"
echo "      ② 执行 clean-history.md 清源仓库 git 史；③ .gitignore 兜底见 runbook.md。"

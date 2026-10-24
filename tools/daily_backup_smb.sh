#!/bin/bash
# ============================================================
# 生产环境每日全量备份 → NAS (SMB)
# 目标: //sandyun.top/ai/服务器备份/sandyun-prod-full-YYYYMMDD.tar.gz
# 内容: Python 源码树(含 models/music/data, 排除 .venv/tmp/__pycache__)
#       + 前端 dist(app/admin) + Java jar + nginx/systemd 配置
#       + root crontab + MySQL 全量 dump
# 保留: NAS 上最近 7 份；失败自动发告警邮件
# 日志: /root/backups/backup.log
# cron: 0 0 * * * /root/backups/daily_backup_smb.sh >> /root/backups/backup.cron.log 2>&1
# ============================================================
set -uo pipefail

# ---------- 配置 ----------
BACKUP_ROOT="/root/backups"
STAGE="$BACKUP_ROOT/staging"
PAYLOAD="$STAGE/payload"
LOG="$BACKUP_ROOT/backup.log"
TS_DATE=$(date +%Y%m%d)
TS_HUMAN=$(date '+%F %T')
ARCHIVE_NAME="sandyun-prod-full-$TS_DATE.tar.gz"
ARCHIVE_LOCAL="$STAGE/$ARCHIVE_NAME"

# SMB 目标
SMB_SHARE="//sandyun.top/ai"
SMB_DIR="服务器备份"
SMB_AUTH="Sand%Ymm2026."
SMB_OPTS="-m SMB3 -t 60"

# MySQL
MYSQL_USER="root"
MYSQL_PASS="123456"
MYSQL_DB="xiaozhi_esp32_server"

# 失败告警邮件（QQ SMTP，与订单日报同一发件账号）
VENV_PY="/root/xiaozhi-server/main/xiaozhi-server/.venv/bin/python"

RETENTION=7

log() { echo "[$(date '+%F %T')] $*" | tee -a "$LOG"; }

# ---------- 失败告警邮件 ----------
send_alert() {
    local stage="$1" detail="$2"
    log "发送失败告警邮件: $stage"
    "$VENV_PY" - "$stage" "$detail" <<'PYEOF'
import smtplib, sys
from email.header import Header
from email.mime.text import MIMEText
from email.utils import formataddr
stage, detail = sys.argv[1], sys.argv[2]
msg = MIMEText(
    "备份阶段: %s\n\n详情:\n%s\n\n请登录服务器检查: /root/backups/backup.log" % (stage, detail),
    "plain", "utf-8")
msg["Subject"] = Header("【备份失败】sandyun-prod %s" % stage, "utf-8")
msg["From"] = formataddr((str(Header("生产备份监控", "utf-8")), "3480877831@qq.com"))
msg["To"] = "wangmingming02677@qq.com"
s = smtplib.SMTP_SSL("smtp.qq.com", 465, timeout=30)
s.login("3480877831@qq.com", "mbxkmxtyeoylcjha")
s.sendmail("3480877831@qq.com", ["wangmingming02677@qq.com"], msg.as_string())
s.quit()
print("alert mail sent")
PYEOF
}

fail() {
    local stage="$1"
    local detail
    detail=$(tail -25 "$LOG" 2>/dev/null)
    log "备份失败: $stage"
    send_alert "$stage" "$detail" >>"$LOG" 2>&1 || log "告警邮件发送也失败了"
    exit 1
}

# ---------- 防重入锁 ----------
mkdir -p "$STAGE" "$PAYLOAD/db"
exec 9>"$BACKUP_ROOT/.lock"
flock -n 9 || { log "已有备份进程在运行，跳过本次"; exit 0; }

log "===== 每日全量备份开始 ====="

# ---------- 磁盘空间预检（staging 峰值约 7GB） ----------
AVAIL_MB=$(df -Pm "$STAGE" | awk 'NR==2{print $4}')
if [ "${AVAIL_MB:-0}" -lt 7000 ]; then
    log "磁盘剩余 ${AVAIL_MB}MB < 7000MB"
    fail "磁盘空间不足"
fi

# ---------- 1/5 MySQL 全量 dump（single-transaction 不锁表） ----------
log "[1/5] mysqldump 全量 $MYSQL_DB ..."
if ! mysqldump -u"$MYSQL_USER" -p"$MYSQL_PASS" --single-transaction --quick \
        --routines --triggers --events "$MYSQL_DB" 2>>"$LOG" \
        | pigz -p 8 > "$PAYLOAD/db/$MYSQL_DB.sql.gz"; then
    fail "MySQL dump 失败"
fi
DUMP_SIZE=$(du -m "$PAYLOAD/db/$MYSQL_DB.sql.gz" | awk '{print $1}')
log "dump 完成: ${DUMP_SIZE}MB"

# ---------- 2/5 清单 + crontab ----------
crontab -l > "$PAYLOAD/crontab-root.txt" 2>/dev/null || echo "(crontab 读取失败)" > "$PAYLOAD/crontab-root.txt"
cat > "$PAYLOAD/MANIFEST.txt" <<EOF
备份时间: $TS_HUMAN
主机: sandyun.top (生产)
归档结构:
  root/xiaozhi-server/...            Python 服务源码树(含 models/music/data, 排除 .venv/tmp/__pycache__)
  var/www/console-v2/{app,admin}/    前端构建产物
  opt/xiaozhi/yuhe-esp32-api.jar     Java 后端 jar
  etc/nginx/                         nginx 配置
  etc/systemd/system/xiaozhi-*.service  systemd unit
  MANIFEST.txt / crontab-root.txt / db/ 本清单与 crontab 与 MySQL 全量 dump($DUMP_SIZE MB)
当前 jar md5: $(md5sum /opt/xiaozhi/yuhe-esp32-api.jar 2>/dev/null | awk '{print $1}')
生成脚本: /root/backups/daily_backup_smb.sh
EOF

# ---------- 3/5 打包（pigz 并行压缩） ----------
log "[3/5] tar 打包源码+前端+jar+配置+DB dump ..."
if ! tar -C / \
        --exclude='.venv' \
        --exclude='__pycache__' \
        --exclude='root/xiaozhi-server/main/xiaozhi-server/tmp' \
        -cf - \
        root/xiaozhi-server \
        var/www/console-v2/app var/www/console-v2/admin \
        opt/xiaozhi/yuhe-esp32-api.jar \
        etc/nginx \
        etc/systemd/system/xiaozhi-manager-api.service \
        etc/systemd/system/xiaozhi-server.service \
        -C "$PAYLOAD" MANIFEST.txt crontab-root.txt db \
        2>>"$LOG" | pigz -p 8 > "$ARCHIVE_LOCAL"; then
    fail "tar 打包失败"
fi
LOCAL_SIZE=$(stat -c%s "$ARCHIVE_LOCAL")
log "打包完成: $ARCHIVE_NAME ($((LOCAL_SIZE/1024/1024))MB)"

# ---------- 4/5 上传 NAS（3 次重试 + 远端大小校验） ----------
log "[4/5] 上传到 NAS: $SMB_SHARE/$SMB_DIR/$ARCHIVE_NAME ..."
UP_OK=0
for i in 1 2 3; do
    if smbclient "$SMB_SHARE" -U "$SMB_AUTH" $SMB_OPTS \
        -c "put \"$ARCHIVE_LOCAL\" \"$SMB_DIR/$ARCHIVE_NAME\"" >>"$LOG" 2>&1; then
        UP_OK=1
        break
    fi
    log "上传失败(第 $i 次)，30s 后重试"
    sleep 30
done
[ "$UP_OK" = "1" ] || fail "SMB 上传失败"

REMOTE_SIZE=$(smbclient "$SMB_SHARE" -U "$SMB_AUTH" $SMB_OPTS \
    -c "ls \"$SMB_DIR/$ARCHIVE_NAME\"" 2>/dev/null | awk '/sandyun-prod-full-[0-9]+\.tar\.gz/{print $3}')
if [ -n "$REMOTE_SIZE" ] && [ "$REMOTE_SIZE" != "$LOCAL_SIZE" ]; then
    log "大小不一致: 本地 $LOCAL_SIZE / 远端 $REMOTE_SIZE"
    fail "远端大小校验不一致"
fi
log "远端校验通过: $REMOTE_SIZE bytes"

# ---------- 5/5 NAS 保留清理（保留最近 RETENTION 份） ----------
log "[5/5] 清理 NAS 旧备份(保留最近 $RETENTION 份) ..."
OLDS=$(smbclient "$SMB_SHARE" -U "$SMB_AUTH" $SMB_OPTS \
    -c "ls \"$SMB_DIR/sandyun-prod-full-*\"" 2>/dev/null \
    | awk '/sandyun-prod-full-[0-9]+\.tar\.gz/{print $1}' | sort | head -n -"$RETENTION")
if [ -n "$OLDS" ]; then
    DEL=""
    while IFS= read -r old; do
        [ -n "$old" ] || continue
        DEL="${DEL}del \"$SMB_DIR/$old\"; "
        log "将删除旧备份: $old"
    done <<<"$OLDS"
    smbclient "$SMB_SHARE" -U "$SMB_AUTH" $SMB_OPTS -c "$DEL" >>"$LOG" 2>&1 \
        || log "旧备份清理部分失败(不影响本次备份)"
else
    log "无超期旧备份"
fi

# ---------- 本地清理（成功后仅留日志） ----------
rm -f "$ARCHIVE_LOCAL"
rm -rf "$PAYLOAD"
log "===== 备份成功: $ARCHIVE_NAME ($((LOCAL_SIZE/1024/1024))MB) ====="

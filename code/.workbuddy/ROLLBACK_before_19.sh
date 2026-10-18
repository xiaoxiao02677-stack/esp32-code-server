#!/bin/bash
# ============================================================
# Yuhe 回滚脚本
# 快照: 20261017T125532Z (UTC) / 2026-10-17 20:55 CST  —— 该快照为「发布前基线」
# 修订: 2026-10-17 21:12 CST
#   - Python 由 systemd 托管（Restart=always），改用 systemctl restart，禁用 pkill+setsid
#   - 补齐本次发布涉及的 core/api/wake_word_handler.py（共 3 个 py 文件，须同批回滚）
#   - check 改为以快照指纹自校验 + 单独对比线上（线上已被 21:02/21:04 的发布替换）
# 用法: bash ROLLBACK.sh [jar|py|py-new|jar-new|web|web-new|db|all|check]
#   all      = jar + py + web（db 仅提示，不自动执行）
#   *-new    = 正向重放到 21:02-21:05 上线版（与回滚相反方向）
#   check    = 只校验快照完整性、对比线上、服务健康断言，不动任何文件
# ============================================================
set -e
TS=20261017T125532Z
BK=/root/deploy-backup/$TS
JAR_DST=/opt/xiaozhi/xiaozhi-esp32-api.jar
PY_ROOT=/root/xiaozhi-server/main/yuhe-server
WEB_ROOT=/var/www/console-v2
TARGET=${1:-all}

# 发布前基线指纹（2026-10-17 20:55 CST）
MD5_JAR=385db9779a6891e8c4e4742454b6fcb8
MD5_WAKE_SVC=388dd075a4577e0d7cd415186e298aa0
MD5_HTTP=f9bb20ba2c49123eaed81ef6323bf203
MD5_WAKE_HANDLER=5ef2c3a370cf9833cab3747002b80aef

# 发布后版本指纹（2026-10-17 21:02:50 CST 上线，用于正向重放/AB 对比，勿与基线混淆）
MD5_NEW_WAKE_SVC=38c7fe7734618af416c4f35818663b42
MD5_NEW_HTTP=1a8f01c8399d67bc6db62da1707fa25e
MD5_NEW_WAKE_HANDLER=9588a97a9210c3db1ff9fffb0328bcc2
MD5_NEW_JAR=4efef7161ab3ed69474bdb27ee5b468b

echo "[ROLLBACK] snapshot=$TS target=$TARGET $(date '+%F %T %Z')"
[ -d "$BK" ] || { echo "FATAL: 快照目录不存在 $BK"; exit 1; }

check_all() {
  echo '--- [0a] 快照自校验（应为全 PASS，否则快照已损坏）---'
  bad=0
  md5snap() {
    act=$(md5sum "$3" | cut -d' ' -f1)
    if [ "$2" = "$act" ]; then
      echo "  PASS $1 $act"
    else
      echo "  FAIL $1 expected=$2 actual=$act"; bad=1
    fi
  }
  md5snap jar "$MD5_JAR" "$BK/jar/xiaozhi-esp32-api.jar"
  md5snap py_wake_service "$MD5_WAKE_SVC" "$BK/py/core/services/wake_word_service.py"
  md5snap py_http_server "$MD5_HTTP" "$BK/py/core/http_server.py"
  md5snap py_wake_handler "$MD5_WAKE_HANDLER" "$BK/py/core/api/wake_word_handler.py"
  tar -tzf "$BK/web-admin.tar.gz" >/dev/null && echo "  PASS web-admin.tar.gz $(tar -tzf "$BK/web-admin.tar.gz" | wc -l) entries"
  [ -s "$BK/db/ai_tables.sql" ] && echo "  PASS db/ai_tables.sql $(wc -c < "$BK/db/ai_tables.sql") bytes"
  [ -s "$BK/db/ai_tables_4tables.sql" ] && echo "  PASS db/ai_tables_4tables.sql $(wc -c < "$BK/db/ai_tables_4tables.sql") bytes"
  [ -s "$BK/db/ai_tables_full.sql" ] && echo "  PASS db/ai_tables_full.sql $(wc -c < "$BK/db/ai_tables_full.sql") bytes"
  if [ "$bad" = 0 ]; then echo '  快照结论: 可用'; else echo '  快照结论: 损坏，勿用于回滚'; return 1; fi

  echo ''
  echo '--- [0a2] 发布后快照自校验（*-new，用于正向重放）---'
  md5snap jar_new "$MD5_NEW_JAR" "$BK/jar-new/xiaozhi-esp32-api.jar"
  md5snap py_new_wake_service "$MD5_NEW_WAKE_SVC" "$BK/py-new/core/services/wake_word_service.py"
  md5snap py_new_http_server "$MD5_NEW_HTTP" "$BK/py-new/core/http_server.py"
  md5snap py_new_wake_handler "$MD5_NEW_WAKE_HANDLER" "$BK/py-new/core/api/wake_word_handler.py"
  tar -tzf "$BK/web-new.tar.gz" >/dev/null && echo "  PASS web-new.tar.gz $(tar -tzf "$BK/web-new.tar.gz" | wc -l) entries"
  if [ "$bad" = 0 ]; then echo '  new 结论: 可用（重放即恢复 21:02-21:05 上线版）'; fi

  echo ''
  echo '--- [0b] 线上现状 vs 快照基线（DIFF 表示已发布新版本）---'
  live()
  {
    if [ -f "$2" ]; then
      act=$(md5sum "$2" | cut -d' ' -f1)
      if [ "$act" = "$3" ]; then echo "  SAME $1  live=$act"; else echo "  DIFF $1  live=$act  baseline=$3"; fi
    else
      echo "  MISSING $1 ($2)"
    fi
  }
  live jar "$JAR_DST" "$MD5_JAR"
  live py_wake_service "$PY_ROOT/core/services/wake_word_service.py" "$MD5_WAKE_SVC"
  live py_http_server "$PY_ROOT/core/http_server.py" "$MD5_HTTP"
  live py_wake_handler "$PY_ROOT/core/api/wake_word_handler.py" "$MD5_WAKE_HANDLER"
  echo "  INFO web-admin 快照 $(tar -tzf "$BK/web-admin.tar.gz" | wc -l) 条目; 线上 $(find "$WEB_ROOT/admin" -type f | wc -l) 文件"
  echo ''
  echo '  说明: 21:02:50 线上 3 个 py 已替换并 systemctl restart（New PID 674256 起于 21:02:52）'
  echo '        21:04:17 线上 jar 已替换（85840471 B）并 systemctl restart（New PID 675741 起于 21:04:18）'
  echo '        因此 DIFF 为预期；本脚本回滚即恢复 20:55 的发布前基线'

  echo ''
  echo '--- [0c] 服务健康断言（判断"发布成功 vs 崩溃循环"）---'
  for svc in yuhe-server xiaozhi-manager-api; do
    st=$(systemctl is-active "$svc" 2>/dev/null || true)
    nr=$(systemctl show -p NRestarts --value "$svc" 2>/dev/null || echo '?')
    ts=$(systemctl show -p ExecMainStartTimestamp --value "$svc" 2>/dev/null || echo '?')
    echo "  $svc: active=$st NRestarts=$nr start=$ts"
  done
  echo '    判读: NRestarts 为累计值且不清零；关键看"本次 ExecMainStartTimestamp 之后无 Traceback"'
  echo -n '  yuhe-server 端口归属(8000/8003/12399): '
  ss -lntp 2>/dev/null | grep -E ':(8000|8003|12399)\b' | grep -oE 'pid=[0-9]+' | sort -u | tr '\n' ' ' || true
  echo ''
  logf=/root/xiaozhi-server/main/yuhe-server/data/app.log
  if [ -f "$logf" ]; then
    tb=$(tail -n 200 "$logf" | grep -c 'Traceback' || true)
    echo "  最近 200 行 Traceback 数: $tb（应为 0；历史段那条老记录不算）"
    echo '  预期无害日志（勿当异常）: 忽略未知 device_config 键 / 鉴权失败(token为空) / 无目标设备可推送(probe-)'
  fi
  echo '  健康口径: active=active + 三口同一 PID + 新启动段无 Traceback → 健康，无需回滚'

  echo ''
  echo '--- [0d] 只读路由探针（证明新路由已注册；不碰设备、不需 token）---'
  p_push=$(curl -s -o /dev/null -w '%{http_code}' -X POST http://127.0.0.1:8003/api/device-config/push 2>/dev/null || true)
  p_old=$(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8003/api/wake-word/devices 2>/dev/null || true)
  p_bogus=$(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8003/api/__nope__ 2>/dev/null || true)
  p_push=${p_push:-000}; p_old=${p_old:-000}; p_bogus=${p_bogus:-000}
  echo "  POST /api/device-config/push  -> $p_push   (401=路由存在且鉴权生效; 404=未注册)"
  echo "  GET  /api/wake-word/devices   -> $p_old   (401=对照组正常)"
  echo "  GET  /api/__nope__            -> $p_bogus   (404=对照组, 证明 404 判定可信)"
  case "$p_push" in
    401|403|400) echo '  PASS 新路由已注册' ;;
    404) echo '  FAIL 新路由 404：http_server.py 的新增路由未生效，或旧文件覆盖' ;;
    000) echo '  FAIL 127.0.0.1:8003 不可达（服务未起/被拦）' ;;
    *)   echo "  WARN 非预期状态码 $p_push，看响应体人工判读" ;;
  esac
  case "$p_old" in
    401|403|400) echo '  PASS 老路由对照正常' ;;
    404) echo '  FAIL 老路由也 404：8003 上不是目标服务，或路由整体丢失' ;;
    *)   echo "  WARN 对照路由返回 $p_old" ;;
  esac
  echo '  说明: 崩溃循环是显性故障；本探针抓"进程活着但路由没注册"的隐性故障'

  echo ''
  echo '--- [0e] 功能级证据（WARN，不计入失败）---'
  if [ -f "$logf" ]; then
    last_push=$(grep '已下发云端设备配置' "$logf" | tail -1 || true)
    echo "  最后一条下发记录: ${last_push:-<无记录>}"
    echo '  WARN 若该时间早于本次启动时间，说明尚无"新配置已下发"的功能级证据；'
    echo '       需一次唤醒词保存或设备重连触发。此项不判 FAIL，避免全绿假象掩盖缺口'
  fi
}

do_jar() {
  echo '--- [1/4] 恢复 Java jar（→ 85504251 B / 385db977）---'
  cp -a "$BK/jar/xiaozhi-esp32-api.jar" "$JAR_DST"
  echo -n '  实际 md5: '; md5sum "$JAR_DST"
  echo '  systemctl restart xiaozhi-manager-api'
  systemctl restart xiaozhi-manager-api
  sleep 5
  systemctl is-active xiaozhi-manager-api
  echo '  校验: systemctl status xiaozhi-manager-api --no-pager -l | head -15'
  echo '  校验: curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8002/'
}

do_py() {
  echo '--- [2/4] 恢复 Python 源码（3 个文件必须同批，混搭会启动即崩）---'
  cp -a "$BK/py/core/services/wake_word_service.py" "$PY_ROOT/core/services/wake_word_service.py"
  cp -a "$BK/py/core/http_server.py"                "$PY_ROOT/core/http_server.py"
  cp -a "$BK/py/core/api/wake_word_handler.py"      "$PY_ROOT/core/api/wake_word_handler.py"
  echo '  md5 核对（expect / actual）:'
  echo "   wake_word_service   $MD5_WAKE_SVC"; echo -n '                       '; md5sum "$PY_ROOT/core/services/wake_word_service.py" | cut -d' ' -f1
  echo "   http_server         $MD5_HTTP"; echo -n '                       '; md5sum "$PY_ROOT/core/http_server.py" | cut -d' ' -f1
  echo "   wake_word_handler   $MD5_WAKE_HANDLER"; echo -n '                       '; md5sum "$PY_ROOT/core/api/wake_word_handler.py" | cut -d' ' -f1
  echo '  systemctl restart yuhe-server   (systemd 托管 Restart=always；勿 pkill+setsid)'
  systemctl restart yuhe-server
  sleep 8
  systemctl is-active yuhe-server
  echo '  校验: systemctl status yuhe-server --no-pager -l | head -15'
  echo '  校验: tail -n 40 /root/xiaozhi-server/main/yuhe-server/data/app.log'
  echo '  校验: ss -lntp | grep -E ":8000|:8003|:12399"'
  echo '  若启动崩溃: Restart=always 每 5s 重试形成循环，看 data/app.log 末尾 traceback，修正后 systemctl restart yuhe-server'
}

do_py_new() {
  echo '--- [py-new] 正向重放：恢复 21:02:50 上线版 Python（三文件同批）---'
  cp -a "$BK/py-new/core/services/wake_word_service.py" "$PY_ROOT/core/services/wake_word_service.py"
  cp -a "$BK/py-new/core/http_server.py"                "$PY_ROOT/core/http_server.py"
  cp -a "$BK/py-new/core/api/wake_word_handler.py"      "$PY_ROOT/core/api/wake_word_handler.py"
  echo '  md5 核对（expect 发布版 / actual）:'
  echo "   wake_word_service   $MD5_NEW_WAKE_SVC"; echo -n '                       '; md5sum "$PY_ROOT/core/services/wake_word_service.py" | cut -d' ' -f1
  echo "   http_server         $MD5_NEW_HTTP"; echo -n '                       '; md5sum "$PY_ROOT/core/http_server.py" | cut -d' ' -f1
  echo "   wake_word_handler   $MD5_NEW_WAKE_HANDLER"; echo -n '                       '; md5sum "$PY_ROOT/core/api/wake_word_handler.py" | cut -d' ' -f1
  systemctl restart yuhe-server
  sleep 8
  systemctl is-active yuhe-server
  echo '  校验: systemctl show -p ExecMainStartTimestamp -p NRestarts --value yuhe-server'
  echo '  校验: tail -n 40 /root/xiaozhi-server/main/yuhe-server/data/app.log'
}

do_jar_new() {
  echo '--- [jar-new] 正向重放：恢复 21:04 上线版 jar（85840471 B / 4efef716）---'
  cp -a "$BK/jar-new/xiaozhi-esp32-api.jar" "$JAR_DST"
  echo -n '  实际 md5: '; md5sum "$JAR_DST"
  systemctl restart xiaozhi-manager-api
  sleep 5
  systemctl is-active xiaozhi-manager-api
  echo '  校验: systemctl show -p ExecMainStartTimestamp -p NRestarts --value xiaozhi-manager-api'
  echo '  校验: curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8002/'
}

do_web_new() {
  echo '--- [web-new] 正向重放：恢复 21:05 现场前端（5 文件，含旧 asset 残留）---'
  rm -rf "$WEB_ROOT/admin"
  tar -xzf "$BK/web-new.tar.gz" -C "$WEB_ROOT"
  echo -n '  恢复后文件数: '; find "$WEB_ROOT/admin" -type f | wc -l
  echo '  校验: curl -s -o /dev/null -w "%{http_code}\n" https://sandyun.top/admin/'
  echo '  注意: web-new 快照含 4 个 asset（新旧共存），仅用于复现现象，不建议作为干净发布产物'
}

do_web() {
  echo '--- [3/4] 恢复前端 admin 目录（发布前基线，3 文件/609916 B）---'
  rm -rf "$WEB_ROOT/admin"
  tar -xzf "$BK/web-admin.tar.gz" -C "$WEB_ROOT"
  echo -n '  恢复后文件数: '; find "$WEB_ROOT/admin" -type f | wc -l
  echo '  校验: ls -l /var/www/console-v2/admin/index.html /var/www/console-v2/admin/assets'
  echo '  校验: curl -s -o /dev/null -w "%{http_code}\n" https://sandyun.top/admin/'
  echo '  校验: curl -s -o /dev/null -w "%{http_code}\n" https://sandyun.top/admincc/'
  echo '  注意: nginx 无需 reload；原属主 197609:197609，如遇权限问题 chown -R 197609:197609 /var/www/console-v2/admin'
}

do_db() {
  echo '--- [4/4] 数据库（ai_agent / ai_device_config）---'
  echo '  默认跳过：数据回滚会覆盖现网，必须人工确认；本段只打印指引，不执行'
  echo ''
  echo '  [方案A1] 四表含结构全量（推荐；14076B→19749B，含 DROP TABLE IF EXISTS + CREATE TABLE）:'
  echo "    mysql -uroot -p123456 xiaozhi_esp32_server < $BK/db/ai_tables_full.sql"
  echo '    警告: 会先 DROP 再重建 ai_agent / ai_device / ai_device_config / ai_agent_wake_word 四表，'
  echo '          仅这四表的数据与结构回到 20:55 基线；执行前必须先 dump 现场'
  echo '  [方案A2] 四表纯数据（不动表结构）:'
  echo "    mysql -uroot -p123456 xiaozhi_esp32_server < $BK/db/ai_tables_4tables.sql"
  echo '  [方案A3] 两表纯数据（降级，仅 ai_agent + ai_device_config）:'
  echo "    mysql -uroot -p123456 xiaozhi_esp32_server < $BK/db/ai_tables.sql"
  echo '    注意: 只回落 A3 会让 ai_device 的 agent 绑定与 config 脱节（回显依赖 ai_device.agent_id）'
  echo '    注意: 先 dump 现场 mysqldump -uroot -p123456 --single-transaction xiaozhi_esp32_server ai_agent ai_device_config > /tmp/ai_tables_before_rollback.sql'
  echo '    注意: config_json 为原生 JSON，dump 中为 CAST(... AS JSON)，只能用 mysql < file 回灌，勿手工拼 SQL'
  echo ''
  echo '  [方案C] binlog PITR（兜底，默认不执行；爆炸半径大，务必先读注释）'
  echo '    基线位点: binlog.000028 @ 13805375（20:55:32 CST 前最后一次事务结束）'
  echo '    该 binlog 内最后一个基线前事务起点: 13727846（Anonymous_GTID, 19:48:18 CST）'
  echo '    取值来源: mysqlbinlog --stop-position=13805375 /var/lib/mysql/binlog.000028 \'
  echo '              | grep -E "^# at |Anonymous_GTID|BEGIN|Xid" | tail -24'
  echo ''
  echo '    !! 已刻意注释掉命令，不要直接执行。原因（scout-db 实测）：'
  echo '       - 省略 --start-position 会从文件开头 07:15:49 整段重放，波及 ai_agent_snapshot(65行)、'
  echo '         wallpaper、ai_device.last_connected_at，撞主键中断或静默改回旧值'
  echo '       - 只给 --start-position=13727846 只能重放最后 1 个事务（chat_audio/chat_history），'
  echo '         不具备"重建到基线"的能力'
  echo '       - 真正全量 PITR 需 --start-position=4 且必须先有"binlog 文件起点"的全量备份，本项目没有'
  echo '    如确需使用，先人工确认再执行（两选一）：'
  echo '      # 仅重放最后 1 个事务: mysqlbinlog --database=xiaozhi_esp32_server --start-position=13727846 --stop-position=13805375 /var/lib/mysql/binlog.000028 > /tmp/pitr.sql'
  echo '      # 自文件起点重建(危险,需先有起点全备): mysqlbinlog --database=xiaozhi_esp32_server --start-position=4 --stop-position=13805375 /var/lib/mysql/binlog.000028 > /tmp/pitr.sql'
  echo '      # 执行前必须先: mysqldump -uroot -p123456 --single-transaction --all-databases > /tmp/full_before_pitr.sql'
  echo '    时区: 应用写入列(update_date 等)为 UTC，比服务器 CST 早 8h；基线 max(update_date)=11:47:44 UTC'
  echo '    补充: ai_device 44:bd:8d:7b:3a:e4 于 21:03:01 CST 因设备重连被写 last_connected_at，属正常，勿当异常'
}

case "$TARGET" in
  check) check_all ;;
  jar) do_jar ;;
  py)  do_py ;;
  py-new) do_py_new ;;
  jar-new) do_jar_new ;;
  web-new) do_web_new ;;
  web) do_web ;;
  db)  do_db ;;
  all) do_jar; do_py; do_web; do_db ;;
  *) echo "用法: $0 [jar|py|py-new|jar-new|web|web-new|db|all|check]"; exit 2 ;;
esac

echo ''
echo '[ROLLBACK] 完成。请按上述校验命令逐项确认。'

#!/bin/bash
# ================= WORM ERADICATION (quarantine-based, reversible) =================
set -u
TS=$(date -u +%Y%m%dT%H%M%SZ)
Q="/root/ir_quarantine_${TS}"
mkdir -p "$Q/artifacts" "$Q/meta"
echo "[*] quarantine dir: $Q"

# ---------- 0. Evidence capture ----------
ps -eo pid,ppid,user,lstart,args > "$Q/meta/ps_before.txt" 2>&1
ss -tunap > "$Q/meta/ss_before.txt" 2>&1
copy(){ if [ -e "$1" ]; then cp -a "$1" "$2" 2>/dev/null && echo "  captured $1"; fi; }
copy /usr/local/bin/systemd-journald                 "$Q/artifacts/impl_systemd-journald.usrlocalbin"
copy /dev/shm/1269538733                             "$Q/artifacts/miner_1269538733.shm"
copy /etc/systemd/system/systemd-journald.service    "$Q/artifacts/rogue_systemd-journald.service"
copy /tmp/.ses                                       "$Q/artifacts/dot-ses.tmp"
copy /etc/ssh/sshd_config                            "$Q/meta/sshd_config.snapshot"
copy /etc/ssh/sshd_config.d/99-cloud-init.conf       "$Q/meta/99-cloud-init.conf.snapshot"
echo "[*] hashes:"; sha256sum "$Q/artifacts/"* 2>/dev/null
strings -n 8 /usr/local/bin/systemd-journald 2>/dev/null | grep -iE "stratum|pool|xmr|185\.|http|wallet|kdevtmpfsi|kinsing|/dev/shm" | head -20 > "$Q/meta/impl_strings.txt" 2>&1

echo; echo "===== STEP 1: neutralize systemd persistence ====="
systemctl stop systemd-journald.socket 2>&1 | sed 's/^/  /'
systemctl stop systemd-journald.service 2>&1 | sed 's/^/  /'
systemctl mask systemd-journald.service 2>&1 | sed 's/^/  /'

echo; echo "===== STEP 2: kill implant(1525) + miner(3337) ====="
kill -9 3337 1525 2>/dev/null
pkill -9 -f "/usr/local/bin/systemd-journald" 2>/dev/null
pkill -9 -f "/dev/shm/1269538733" 2>/dev/null
sleep 1
echo "  remaining (should be none):"; pgrep -af "1269538733|/usr/local/bin/systemd-journald" || echo "  (none)"

echo; echo "===== STEP 3: remove rogue unit override ====="
if mv -f /etc/systemd/system/systemd-journald.service "$Q/artifacts/rogue_systemd-journald.service.REMOVED" 2>/dev/null; then echo "  rogue unit moved out of /etc/systemd/system"; fi
systemctl daemon-reload 2>&1 | sed 's/^/  /'

echo; echo "===== STEP 4: remove payloads ====="
rm -f /dev/shm/1269538733 && echo "  removed /dev/shm/1269538733"
if mv -f /usr/local/bin/systemd-journald "$Q/artifacts/impl_systemd-journald.usrlocalbin.REMOVED" 2>/dev/null; then echo "  removed /usr/local/bin/systemd-journald"; fi
rm -f /tmp/.ses && echo "  removed /tmp/.ses"

echo; echo "===== STEP 5: restore REAL journald ====="
systemctl unmask systemd-journald.service 2>&1 | sed 's/^/  /'
systemctl daemon-reload 2>&1 | sed 's/^/  /'
systemctl start systemd-journald.socket 2>&1 | sed 's/^/  /'
systemctl start systemd-journald.service 2>&1 | sed 's/^/  /'

echo; echo "===== STEP 6: VERIFY ====="
echo "-- unit status --"; systemctl status systemd-journald.service --no-pager 2>&1 | head -10
echo "-- journald proc exe (must be /usr/lib/systemd/systemd-journald) --"
for p in $(pgrep -x systemd-journal 2>/dev/null; pgrep -f "systemd-journald" 2>/dev/null); do echo "  pid $p -> $(readlink /proc/$p/exe 2>/dev/null)"; done
echo "-- rogue broadcast --"; pkill -af "1269538733|/usr/local/bin/systemd-journald" || echo "  (none)"
echo "-- pool conn (should be empty) --"; ss -tnp 2>/dev/null | grep -E "185\.112\.146|1269538733" || echo "  (none)"
echo "-- /dev/shm --"; ls -la /dev/shm/
echo "-- /usr/local/bin --"; ls -la /usr/local/bin/
echo "-- root crontab --"; crontab -l 2>/dev/null || echo "  (empty)"
echo "-- journalctl smoke test --"; journalctl -n 3 --no-pager 2>&1 | tail -4
echo "-- load --"; uptime

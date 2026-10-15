#!/bin/bash
# ===== POST-CLEANUP VERIFICATION (wait & rescan for respawn) =====
echo "===== waiting 25s to catch any respawn ====="
sleep 25

echo; echo "===== 1. any rogue process? ====="
ps -eo pid,ppid,user,pcpu,lstart,args --sort=-pcpu 2>/dev/null | head -12
echo "-- pattern match --"; pgrep -af "1269538733|/usr/local/bin/systemd-journald" || echo "  (clean)"
echo "-- top cpu only --"; ps -eo pid,pcpu,comm --sort=-pcpu | head -6

echo; echo "===== 2. journald must be the REAL one ====="
systemctl show systemd-journald.service -p FragmentPath -p MainPID -p ActiveState 2>/dev/null
for p in $(pgrep -f systemd-journald); do echo "  pid $p -> $(readlink /proc/$p/exe)"; done

echo; echo "===== 3. no mask / stray symlink left ====="
ls -la /etc/systemd/system/ | grep -i journal || echo "  (no journald override left — good)"
ls -la /etc/systemd/system/systemd-journald.service 2>/dev/null || echo "  (no file — good)"

echo; echo "===== 4. persistence surfaces clean ====="
echo "-- crontabs dir --"; ls -la /var/spool/cron/crontabs/; 
echo "-- cron.d/hourly/daily --"; ls /etc/cron.d/ /etc/cron.hourly/ 2>/dev/null
echo "-- ld.so.preload --"; cat /etc/ld.so.preload 2>/dev/null || echo "  (none)"
echo "-- /dev/shm /tmp /var/tmp executables --"; ls -la /dev/shm/ /var/tmp/; find /tmp /dev/shm /var/tmp -type f -perm -u+x 2>/dev/null | head
echo "-- systemd system dirs for rogue units --"; find /etc/systemd/system -maxdepth 2 -type f -name "*.service" 2>/dev/null

echo; echo "===== 5. network: no miner pool, no odd listeners ====="
ss -tnp 2>/dev/null | grep -vE "127.0.0.1|::ffff:127" | head -20
echo "-- established to pool? --"; ss -tnp 2>/dev/null | grep -E "185\.112|:6280|:3333" || echo "  (none)"
echo "-- outbound listeners --"; ss -tlnp 2>/dev/null | grep -vE "0.0.0.0:80|0.0.0.0:22|:8101|:8102|:8104|:8105|:8144|:8002|:3306|:6379|:631|127.0.0" | head

echo; echo "===== 6. system integrity spot-checks ====="
echo "-- packages owning /usr/local/bin (should be empty) --"; ls -la /usr/local/bin/
echo "-- dpkg verify systemd (quiet if intact) --"; dpkg -V systemd openssh-server 2>/dev/null | head
echo "-- uid0 users --"; awk -F: '($3==0){print $1}' /etc/passwd
echo "-- authorized_keys --"; cat /root/.ssh/authorized_keys 2>/dev/null

echo; echo "===== 7. load now (should be decaying) ====="; uptime
echo; echo "===== 8. quarantine inventory ====="; ls -laR /root/ir_quarantine_* 2>/dev/null | head -40

#!/bin/bash
# ===== IR RECON PASS 1 =====
echo "===== 1. TOP CPU PROCESSES ====="
ps -eo pid,ppid,user,pcpu,pmem,etime,stat,comm,args --sort=-pcpu 2>/dev/null | head -40
echo
echo "===== 2. NETWORK LISTENERS ====="
ss -tulnp 2>/dev/null | head -60
echo
echo "===== 3. ESTABLISHED OUTBOUND ====="
ss -tnp state established 2>/dev/null | head -60
echo
echo "===== 4. CRON (system + user) ====="
echo "--- /etc/crontab ---"; cat /etc/crontab 2>/dev/null
echo "--- /etc/cron.d ---"; ls -la /etc/cron.d/ 2>/dev/null; for f in /etc/cron.d/*; do echo "== $f =="; cat "$f" 2>/dev/null; done
echo "--- /var/spool/cron/crontabs ---"; ls -la /var/spool/cron/crontabs/ 2>/dev/null; for f in /var/spool/cron/crontabs/*; do echo "== $f =="; cat "$f" 2>/dev/null; done
echo "--- /etc/cron.hourly|daily|weekly|monthly ---"; ls -la /etc/cron.hourly/ /etc/cron.daily/ /etc/cron.weekly/ /etc/cron.monthly/ 2>/dev/null
echo
echo "===== 5. SUSPICIOUS DIRS ====="
for d in /tmp /var/tmp /dev/shm /run/shm /var/run; do
  echo "--- $d ---"; ls -la "$d" 2>/dev/null | head -40
done
echo
echo "===== 6. SYSTEMD SERVICES (recent / rogue) ====="
systemctl list-units --type=service --state=running --no-pager 2>/dev/null
echo "--- enabled non-standard units ---"
systemctl list-unit-files --state=enabled --no-pager 2>/dev/null | head -80
echo
echo "===== 7. LD PRELOAD ROOTKIT ====="
cat /etc/ld.so.preload 2>/dev/null && echo "(ld.so.preload EXISTS ^^^)"
echo
echo "===== 8. AUTHORIZED KEYS ====="
for k in /root/.ssh/authorized_keys /home/*/.ssh/authorized_keys; do echo "== $k =="; cat "$k" 2>/dev/null; done
echo
echo "===== 9. RECENTLY MODIFIED IN /etc /usr/bin /usr/local/bin (last 3 days) ====="
find /etc /usr/bin /usr/local/bin /usr/sbin -xdev -mtime -3 -type f 2>/dev/null | head -60
echo
echo "===== 10. /etc/passwd UID0 / odd users ====="
awk -F: '($3==0){print}' /etc/passwd
echo "--- passwd tail ---"; tail -5 /etc/passwd
echo
echo "===== 11. HIDDEN EXECUTABLES ====="
find / -xdev -type f \( -name ".*" -o -path "*/.*/*" \) -executable -mtime -7 2>/dev/null | grep -vE "/proc|/sys" | head -40
echo
echo "===== 12. /proc FDs pointing to deleted/binaries ====="
ls -la /proc/*/exe 2>/dev/null | grep -vE "bash|python|nginx|java|systemd|sshd|ls|ps|grep|awk|cat|find|head" | head -40

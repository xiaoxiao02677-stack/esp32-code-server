#!/bin/bash
# ===== IR RECON PASS 5 : entry vector + config tamper + full proc exe sweep =====
echo "===== 1. ACCEPTED PASSWORD (any) & 16:14-16:20 window ====="
grep -aE "Accepted password" /var/log/auth.log 2>/dev/null | tail -10 || echo "(no password-based root logins)"
echo "--- auth.log 16:14:50 ~ 16:20 ---"
awk '$0 >= "2026-10-13T16:14:50" && $0 <= "2026-10-13T16:20:00"' /var/log/auth.log 2>/dev/null | head -60
echo
echo "===== 2. brute-force source summary ====="
grep -aE "Failed password|Invalid user" /var/log/auth.log* 2>/dev/null | grep -oE "from [0-9]+\.[0-9]+\.[0-9]+\.[0-9]+" | sort | uniq -c | sort -rn | head
echo "-- did 209.97.136.238 ever succeed? --"
grep -a "209.97.136.238" /var/log/auth.log 2>/dev/null | grep -aiE "Accepted|session opened" | head
echo
echo "===== 3. journald.conf tamper (attacker may disable logging) ====="
ls -la --time-style=full-iso /etc/systemd/journald.conf 2>/dev/null
grep -vE "^#|^$" /etc/systemd/journald.conf 2>/dev/null
find /etc/systemd -name "journald.conf*" 2>/dev/null
echo
echo "===== 4. xmrig config / wallet artifacts ====="
ls -la /root/.config/ 2>/dev/null
find /root /home /etc /var -name "*.xmrig*.json" -o -name "xmrig*.json" 2>/dev/null | head
find / -xdev -name "*.pid" -path "*shm*" 2>/dev/null | head
echo
echo "===== 5. systemctl resolved unit paths ====="
systemctl show systemd-journald.service -p FragmentPath -p ExecStart -p User -p Restart 2>/dev/null
echo
echo "===== 6. FULL /proc/*/exe sweep (deleted or shm or local) ====="
for p in /proc/[0-9]*; do
  pid=${p#/proc/}
  ex=$(readlink "$p/exe" 2>/dev/null)
  case "$ex" in
    *shm*|*local/bin*|*"/tmp/"*|*"/var/tmp/"*|*(deleted)*) echo "PID $pid -> $ex :: $(tr '\0' ' ' < $p/cmdline 2>/dev/null)" ;;
  esac
done
echo
echo "===== 7. syslog / kern around 16:15 ====="
awk '$0 >= "Oct 13 16:14" && $0 <= "Oct 13 16:20"' /var/log/syslog 2>/dev/null | head -40
echo
echo "===== 8. nginx access 16:1x (suspicious uploads) ====="
ls -la /var/log/nginx/ 2>/dev/null
grep -aE "13/Oct/2026:16:1" /var/log/nginx/access.log 2>/dev/null | grep -aiE "POST|PUT|\.php|\.sh|upload|passwd|shm|chmod" | head -20
echo
echo "===== 9. cron execution log around infection ====="
grep -aE "CRON|systemd" /var/log/syslog 2>/dev/null | awk '$0 >= "Oct 13 16:1" && $0 <= "Oct 13 16:2"' | head -30
echo
echo "===== 10. filesystem mount / persistence in /etc/fstab ====="
cat /etc/fstab 2>/dev/null | grep -vE "^#|^$"
echo
echo "===== 11. /etc/systemd/journald.conf.d & other overrides ====="
find /etc/systemd -name "*.conf" -newermt "2026-10-13 00:00" 2>/dev/null | head

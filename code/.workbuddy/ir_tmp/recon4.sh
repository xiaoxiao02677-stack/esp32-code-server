#!/bin/bash
# ===== IR RECON PASS 4 : close all gaps, find entry vector & any 2nd implant =====
echo "===== 1. rogue unit enablement / wants symlinks ====="
ls -la /etc/systemd/system/multi-user.target.wants/ 2>/dev/null
echo "-- is there enable symlink for systemd-journald? --"
find /etc/systemd -name "*journald*" 2>/dev/null
echo "-- vendor drop-in nice.conf --"; cat /usr/lib/systemd/system/systemd-journald.service.d/nice.conf 2>/dev/null
echo "-- socket state --"; systemctl is-enabled systemd-journald.socket systemd-journald.service 2>/dev/null
echo
echo "===== 2. accounts / sudo / pam integrity ====="
echo "-- uid0 --"; awk -F: '($3==0){print}' /etc/passwd
echo "-- last 6 passwd --"; tail -6 /etc/passwd
echo "-- newly added users (uid>=1000) --"; awk -F: '($3>=1000 && $3<65534){print $1":"$3":"$6":"$7}' /etc/passwd
echo "-- sudoers.d --"; ls -la /etc/sudoers.d/ 2>/dev/null; grep -rE "NOPASSWD|ALL" /etc/sudoers.d/ 2>/dev/null | head
echo "-- pam.d grep suspicious --"; grep -rnE "pam_exec|/tmp/|/dev/shm|/usr/local" /etc/pam.d/ 2>/dev/null | head
echo
echo "===== 3. autostart / user units ====="
ls -la /etc/xdg/autostart/ 2>/dev/null
find /root/.config /home/*/.config -path "*autostart*" -o -path "*systemd/user*" 2>/dev/null | head
systemctl --user list-unit-files 2>/dev/null | head -20
echo
echo "===== 4. FS sweep: ELF modified last 3 days outside vendor/known paths ====="
find / -xdev -type f -newermt "-3 days" 2>/dev/null \
 | grep -vE "^/(proc|sys|run|dev)|/yh/|/root/yh|essl|/var/lib|/var/cache|/usr/lib/python|site-packages|\.pyc|/home/demo/yuhe|yuhe-esp32|\.workbuddy" \
 | xargs -r file 2>/dev/null | grep -E "ELF|executable" | head -40
echo
echo "===== 5. any file matching implant size (3820020) or name systemd-journald ====="
find / -xdev -type f -size 3820020c 2>/dev/null | head
find / -xdev -name "systemd-journald" 2>/dev/null
echo
echo "===== 6. libprocesshider / preload hunting ====="
find / -xdev -name "*processhider*" -o -name "libhide*" 2>/dev/null | head
grep -rIn "ld.so.preload" /etc 2>/dev/null | head
echo
echo "===== 7. miner/watchdog sockets ====="
ss -tnp 2>/dev/null | grep -E "1525|3337" ; echo "(ss -p for 1525/3337 ^)"
ls -l /proc/3337/fd 2>/dev/null | head -20
echo
echo "===== 8. ENTRY VECTOR: auth log analysis ====="
echo "-- last 10 successful Accepted/opened sessions --"
grep -aE "Accepted|session opened for user root" /var/log/auth.log 2>/dev/null | tail -20
echo "-- top source IPs of failed logins --"
grep -aE "Failed password|Invalid user" /var/log/auth.log 2>/dev/null | grep -oE "from [0-9]+\.[0-9]+\.[0-9]+\.[0-9]+" | sort | uniq -c | sort -rn | head -15
echo "-- any wget/curl in logs / suspicious cmd --"
grep -aE "wget|curl|chmod \+x|/dev/shm|/var/tmp|1269538733|4035188231|systemd-journald" /var/log/auth.log 2>/dev/null | tail -20
echo
echo "===== 9. root bash_history FULL ====="
cat -n /root/.bash_history 2>/dev/null | tail -60
echo
echo "===== 10. sysupdate.d.5.gz ownership (exclude) ====="
dpkg -S /usr/share/man/man5/sysupdate.d.5.gz 2>/dev/null || echo "(not owned?)"
echo
echo "===== 11. /tmp/.ses origin: who has it open ====="
lsof /tmp/.ses 2>/dev/null || echo "(nobody holds /tmp/.ses)"
echo "--- /etc/cron.d & cron.hourly second look (hidden) ---"
ls -la /etc/cron.d/ /etc/cron.hourly/ /etc/cron.daily/ 2>/dev/null | grep -vE "^total|placeholder"

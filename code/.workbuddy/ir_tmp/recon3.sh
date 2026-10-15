#!/bin/bash
# ===== IR RECON PASS 3 : pinpoint stealth persistence & all implants =====
echo "===== 1. ROGUE systemd unit content ====="
echo "---- /etc/systemd/system/systemd-journald.service ----"
cat /etc/systemd/system/systemd-journald.service 2>/dev/null
echo
echo "---- all .service in /etc/systemd/system (non-symlink, real files) ----"
find /etc/systemd/system -maxdepth 3 -type f -name "*.service" -o -maxdepth 3 -type f -name "*.timer" 2>/dev/null | while read f; do echo "== $f =="; ls -la --time-style=full-iso "$f"; done
echo
echo "===== 2. journald binaries compare ====="
for j in /usr/local/bin/systemd-journald /usr/lib/systemd/systemd-journald /lib/systemd/systemd-journald; do
  echo "== $j =="; ls -la --time-style=full-iso "$j" 2>/dev/null; file "$j" 2>/dev/null; sha256sum "$j" 2>/dev/null
done
echo "-- journald processes --"
ps -eo pid,ppid,user,lstart,comm,args | grep -i journal
echo "-- systemctl status systemd-journald --"
systemctl status systemd-journald --no-pager 2>/dev/null | head -20
echo "-- rpm/dpkg integrity of systemd-journald --"
dpkg -S /usr/local/bin/systemd-journald 2>/dev/null || echo "(/usr/local/bin/systemd-journald NOT owned by any package ^^^)"
echo
echo "===== 3. /usr/local/bin & suspicious in it ====="
ls -la --time-style=full-iso /usr/local/bin/ 2>/dev/null
echo "-- /usr/local/lib --"; ls -la --time-style=full-iso /usr/local/lib/ 2>/dev/null
echo
echo "===== 4. crontab -l (root) & at jobs ====="
crontab -l 2>/dev/null; echo "rc=$?"
ls -la /var/spool/cron/crontabs/ 2>/dev/null
at -l 2>/dev/null || echo "(no atd)"
echo
echo "===== 5. /tmp/.ses and misc ====="
echo "--- /tmp/.ses ---"; ls -la /tmp/.ses 2>/dev/null; cat /tmp/.ses 2>/dev/null | head -5
ls -la /tmp/.X11-unix/ 2>/dev/null
echo
echo "===== 6. /etc/hosts / resolv / environment ====="
echo "--- /etc/hosts ---"; cat /etc/hosts
echo "--- /etc/resolv.conf ---"; cat /etc/resolv.conf 2>/dev/null
echo "--- /etc/environment ---"; cat /etc/environment 2>/dev/null
echo "--- /etc/ld.so.preload ---"; cat /etc/ld.so.preload 2>/dev/null || echo "(none)"
echo
echo "===== 7. ALL processes with full cmdline (find hidden/rogue) ====="
ps -eo pid,ppid,user,lstart,args --sort=pid 2>/dev/null | grep -viE "grep|kworker|ksoftirq|rcu_|migration|cpuhp|kthreadd|watchdog|kcompact|kswapd|kdevtemp|scsi_|kblockd|blkcg|writeback|kintegrity|kdmflush|kcryptd|kuncrypt|crypto|bioset|kpsmoused|iprt-VBox|ata_sff|khubd|kvm|irq|idle_inject|kstr|kworker" | head -70
echo
echo "===== 8. MINER open files / children / listening ====="
echo "-- children of 1525 --"; pgrep -P 1525 -a 2>/dev/null
echo "-- children of 3337 --"; pgrep -P 3337 -a 2>/dev/null
echo "-- ls -l /proc/1525/{exe,cwd} --"; ls -l /proc/1525/exe /proc/1525/cwd 2>/dev/null
echo "-- fd of 1525 --"; ls -l /proc/1525/fd 2>/dev/null | head -30
echo "-- maps (libs) of 1525 --"; cat /proc/1525/maps 2>/dev/null | awk '{print $6}' | grep -vE "^$" | sort -u | head -30
echo
echo "===== 9. modified /etc/systemd & lib last 24h (authoritative) ====="
find /etc/systemd /lib/systemd /usr/local /var/spool -type f -mtime -1 2>/dev/null | head -40
echo
echo "===== 10. cron/timer re-check with md5 dates ====="
stat /var/spool/cron/crontabs 2>/dev/null | head -6
journalctl --no-pager -q -b 2>/dev/null | grep -iE "journald|shm|1269538733|4035188231|failed" | tail -25

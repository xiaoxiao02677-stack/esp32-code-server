#!/bin/bash
# ===== IR RECON PASS 2 : persistence & artifact deep-dive =====
echo "===== A. PROCESS TREE (ancestors of miner 3337) ====="
for p in 3337 1525; do
  echo "-- proc $p --"
  ps -o pid,ppid,user,lstart,stat,args -p $p 2>/dev/null
  echo "cmdline: $(tr '\0' ' ' < /proc/$p/cmdline 2>/dev/null)"
  echo "cwd: $(readlink /proc/$p/cwd 2>/dev/null)   exe: $(readlink /proc/$p/exe 2>/dev/null)"
  echo "parent chain:"
  ppp=$p; for i in 1 2 3 4 5 6; do
    ppid=$(awk '{print $4}' /proc/$ppp/stat 2>/dev/null)
    [ -z "$ppid" ] && break
    echo "    $(awk '{print $2}' /proc/$ppid/comm 2>/dev/null) (pid=$ppid)"
    ppp=$ppid; [ "$ppp" = "1" ] && break
  done
done
echo
echo "===== B. MINER BINARY ARTIFACT ====="
ls -la /dev/shm/ 2>/dev/null
file /dev/shm/1269538733 2>/dev/null
sha256sum /dev/shm/1269538733 2>/dev/null
echo "-- strings preview (URLs/pools) --"
strings -n 6 /dev/shm/1269538733 2>/dev/null | grep -iE "stratum|pool|mine|xmr|http|\.onion|185\.|wallet|44|donate" | head -30
echo
echo "===== C. SYSTEMD PERSISTENCE ====="
echo "-- /etc/systemd/system/*.service recently added --"
ls -la --time-style=full-iso /etc/systemd/system/ 2>/dev/null | head -60
echo "-- timers --"
systemctl list-timers --all --no-pager 2>/dev/null | head -40
echo
echo "===== D. INIT / PROFILE PERSISTENCE ====="
echo "-- /etc/rc.local --"; cat /etc/rc.local 2>/dev/null
echo "-- /etc/init.d --"; ls -la /etc/init.d/ 2>/dev/null
echo "-- /etc/profile.d --"; ls -la /etc/profile.d/ 2>/dev/null
echo "-- /root/.bashrc tail --"; tail -15 /root/.bashrc 2>/dev/null
echo "-- /root/.profile tail --"; tail -15 /root/.profile 2>/dev/null
echo "-- /etc/bash.bashrc tail --"; tail -15 /etc/bash.bashrc 2>/dev/null
echo
echo "===== E. LD PRELOAD / ROOTKIT ====="
echo "ld.so.preload: $(cat /etc/ld.so.preload 2>/dev/null || echo '(none)')"
echo "ld.so.conf.d:"; ls -la /etc/ld.so.conf.d/ 2>/dev/null
echo
echo "===== F. SSH KEYS & HISTORY ====="
echo "-- authorized_keys --"; for k in /root/.ssh/authorized_keys /home/*/.ssh/authorized_keys; do echo "== $k =="; ls -la "$k" 2>/dev/null; cat "$k" 2>/dev/null; done
echo "-- bash_history (root) tail --"; tail -40 /root/.bash_history 2>/dev/null
echo
echo "===== G. FILES MODIFIED LAST 24h IN KEY PATHS ====="
find /etc /usr/bin /usr/sbin /usr/local /root /var/spool/cron /lib/systemd -xdev -mtime -1 -type f 2>/dev/null | grep -vE "\.log$|/yh/|idf|\.pyc$" | head -70
echo
echo "===== H. OTHER SUSPECT BINARIES ====="
ls -la /tmp/ /var/tmp/ /dev/shm/ 2>/dev/null | grep -vE "^total|^d"
find / -xdev -type f \( -name "kinsing" -o -name "kdevtmpfsi" -o -name "kworkerd" -o -name "sysupdate*" -o -name "networkservice" \) 2>/dev/null | head
echo
echo "===== I. FULL LISTENER/ESTABLISHED (compact) ====="
ss -tunap 2>/dev/null | grep -vE "127.0.0.1|\[::1\]|::ffff:127" | head -40

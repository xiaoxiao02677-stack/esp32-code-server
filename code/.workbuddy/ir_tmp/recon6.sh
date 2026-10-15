#!/bin/bash
# ===== IR RECON PASS 6 : final pre-cleanup verification =====
echo "===== 1. processes with deleted/shm/local exe ====="
for p in /proc/[0-9]*; do
  pid=${p#/proc/}
  ex=$(readlink "$p/exe" 2>/dev/null) || continue
  case "$ex" in
    *shm*|*local/bin*|*tmp*) echo "PID $pid -> $ex :: $(tr '\0' ' ' < $p/cmdline 2>/dev/null | cut -c1-80)" ;;
  esac
done
echo "-- deleted-exe procs --"
ls -l /proc/[0-9]*/exe 2>/dev/null | grep -i deleted | head
echo
echo "===== 2. authorized_keys fingerprint vs login fingerprint ====="
ssh-keygen -lf /root/.ssh/authorized_keys 2>/dev/null
echo "(login used SHA256:7RQGhX2BEFdg8igm47FeHrST21jr4zpE2mvQ1YuVjL8)"
echo
echo "===== 3. sshd config effective ====="
sshd -T 2>/dev/null | grep -iE "permitrootlogin|passwordauthentication|pubkeyauthentication|port " | head
echo "-- /etc/ssh/sshd_config.d/ --"; ls -la /etc/ssh/sshd_config.d/ 2>/dev/null; cat /etc/ssh/sshd_config.d/*.conf 2>/dev/null
echo "-- root last login --"; lastlog -u root 2>/dev/null; last -a 2>/dev/null | head -12
echo
echo "===== 4. firewall state ====="
ufw status verbose 2>/dev/null || echo "(no ufw)"
iptables -S 2>/dev/null | head -20
echo
echo "===== 5. confirm exact malicious PIDs & cgroup ====="
pgrep -af "1269538733|/usr/local/bin/systemd-journald" 2>/dev/null
systemctl show systemd-journald.service -p MainPID -p ActiveState -p SubState 2>/dev/null
echo
echo "===== 6. /tmp/.ses content & /dev/shm listing ====="
cat /tmp/.ses 2>/dev/null; ls -la /dev/shm/ 2>/dev/null
echo
echo "===== 7. any *.sh dropper in /root /tmp /var/tmp /dev/shm ====="
find /root /tmp /var/tmp /dev/shm -maxdepth 2 -type f \( -name "*.sh" -o -name "*.py" -o -perm -u+x \) 2>/dev/null | grep -vE "/root/yh|\.venv|\.cache" | head -30

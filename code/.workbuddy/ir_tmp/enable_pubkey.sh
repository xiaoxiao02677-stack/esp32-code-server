#!/bin/bash
# ===== Enable SSH public-key auth (fix tampered config) + ensure key authorized =====
set -u
TS=$(date -u +%Y%m%dT%H%M%SZ)
Q="/root/ir_quarantine_20261013T093320Z/artifacts"
mkdir -p "$Q"

echo "===== 0. current effective config ====="
sshd -T 2>/dev/null | grep -iE "^pubkeyauthentication|^passwordauthentication|^permitrootlogin|^authorizedkeysfile"

echo; echo "===== 1. backup sshd_config ====="
cp -a /etc/ssh/sshd_config /root/sshd_config.bak-$TS && echo "  backed up -> /root/sshd_config.bak-$TS"

echo; echo "===== 2. neutralize tampered drop-in (PubkeyAuthentication no) ====="
if [ -f /etc/ssh/sshd_config.d/99-cloud-init.conf ]; then
  mv -f /etc/ssh/sshd_config.d/99-cloud-init.conf "$Q/99-cloud-init.conf.REMOVED" && echo "  moved 99-cloud-init.conf out (was: $(cat "$Q/99-cloud-init.conf.REMOVED"))"
else
  echo "  (no drop-in)"
fi
echo "  remaining drop-ins:"; ls -la /etc/ssh/sshd_config.d/ 2>/dev/null

echo; echo "===== 3. set PubkeyAuthentication yes in main config ====="
sed -i 's/^[[:space:]]*PubkeyAuthentication[[:space:]]\+no[[:space:]]*$/PubkeyAuthentication yes/' /etc/ssh/sshd_config
grep -qE '^[[:space:]]*PubkeyAuthentication[[:space:]]+yes' /etc/ssh/sshd_config || echo 'PubkeyAuthentication yes' >> /etc/ssh/sshd_config
grep -nE '^[[:space:]]*PubkeyAuthentication' /etc/ssh/sshd_config

echo; echo "===== 4. ensure the ed25519 key is authorized ====="
mkdir -p /root/.ssh && chmod 700 /root/.ssh
touch /root/.ssh/authorized_keys && chmod 600 /root/.ssh/authorized_keys
KEY='ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIHj83eRqshGNz3/a4I9gTNV7OiIHOUVMmZay2bylD1oS gitee SSH key'
grep -qF "AAAAC3NzaC1lZDI1NTE5AAAAIHj83eRqshGNz3/a4I9gTNV7OiIHOUVMmZay2bylD1oS" /root/.ssh/authorized_keys || echo "$KEY" >> /root/.ssh/authorized_keys
echo "  authorized_keys now:"; cat /root/.ssh/authorized_keys

echo; echo "===== 5. validate & reload sshd ====="
if sshd -t 2>&1; then echo "  config test: OK"; systemctl reload ssh 2>&1 | sed 's/^/  /'; echo "  reloaded"; else echo "  config test FAILED"; fi

echo; echo "===== 6. effective AFTER ====="
sshd -T 2>/dev/null | grep -iE "^pubkeyauthentication|^passwordauthentication|^permitrootlogin|^authorizedkeysfile"

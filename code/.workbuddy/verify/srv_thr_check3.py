# -*- coding: utf-8 -*-
# 查 _push_device_config 的 on_sent 钩子用法 + 唤醒词阈值的既有服务端同步（可参照）
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
import paramiko
ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect("sandyun.top", port=22222, username="root", timeout=30)
try:
    def run(cmd, label, t=60):
        print(f"\n===== {label} =====")
        _, out, err = ssh.exec_command(cmd, timeout=t)
        o = out.read().decode('utf-8', errors='replace')
        e = err.read().decode('utf-8', errors='replace')
        print(o[:6000] if o.strip() else "(无输出)")
        if e.strip(): print("[stderr]", e[:300])
    run("sed -n '350,420p' /root/xiaozhi-server/main/yuhe-server/core/services/wake_word_service.py", "_push_device_config 剩余部分（on_sent 机制）")
    run("grep -n -B3 -A8 'on_sent' /root/xiaozhi-server/main/yuhe-server/core/services/wake_word_service.py | head -50", "on_sent 现有用法")
finally:
    ssh.close()
    print("\n[done]")

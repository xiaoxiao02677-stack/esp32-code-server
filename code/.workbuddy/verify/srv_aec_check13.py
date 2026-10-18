# -*- coding: utf-8 -*-
# 查 handleAbortMessage 下行内容（打断后设备如何恢复）
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
        print(o[:5000] if o.strip() else "(无输出)")
        if e.strip(): print("[stderr]", e[:300])
    run("cat /root/xiaozhi-server/main/yuhe-server/core/handle/abortHandle.py", "abortHandle.py 全文")
finally:
    ssh.close()
    print("\n[done]")

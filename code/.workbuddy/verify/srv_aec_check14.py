# -*- coding: utf-8 -*-
# 查服务端 Silero VAD 的参数（灵敏度/阈值可调性）
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
        print(o[:4500] if o.strip() else "(无输出)")
        if e.strip(): print("[stderr]", e[:300])
    run("cat /root/xiaozhi-server/main/yuhe-server/core/providers/vad/silero.py", "silero.py 全文")
    run("grep -n -B2 -A8 'VAD' /root/xiaozhi-server/main/yuhe-server/config.yaml | head -20", "config.yaml VAD 段")
finally:
    ssh.close()
    print("\n[done]")

# -*- coding: utf-8 -*-
# 深挖 receiveAudioHandle.py 的完整逻辑（服务端如何判断"用户说话打断 TTS"）
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
        print(o[:7000] if o.strip() else "(无输出)")
        if e.strip(): print("[stderr]", e[:300])
    run("cat /root/xiaozhi-server/main/yuhe-server/core/handle/receiveAudioHandle.py", "receiveAudioHandle.py 全文")
finally:
    ssh.close()
    print("\n[done]")

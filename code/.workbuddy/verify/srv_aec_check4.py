# -*- coding: utf-8 -*-
# 查 receiveAudioHandle（服务端接收设备音频的处理器）+ abortHandle + listen 模式
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
    run("grep -n 'listen' /root/xiaozhi-server/main/yuhe-server/core/handle/receiveAudioHandle.py | head -20", "receiveAudioHandle listen 处理")
    run("grep -rn 'startListen' /root/xiaozhi-server/main/yuhe-server/core/handle/*.py | head -10", "startListen 分布")
    run("grep -n -A15 'def.*abort\\|stopSpeaking' /root/xiaozhi-server/main/yuhe-server/core/handle/abortHandle.py | head -50", "abortHandle 内容")
    run("grep -rn 'mode.*realtime\\|realtime.*mode' /root/xiaozhi-server/main/yuhe-server/core/ --include='*.py' | grep -v venv | head -10", "realtime 模式处理")
finally:
    ssh.close()
    print("\n[done]")

# -*- coding: utf-8 -*-
# 查服务端 AEC 时间戳对齐逻辑 + VAD 提供商
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
        print(o[:5500] if o.strip() else "(无输出)")
        if e.strip(): print("[stderr]", e[:300])
    run("sed -n '410,450p' /root/xiaozhi-server/main/yuhe-server/core/connection.py", "connection.py 410-450（时间戳消费）")
    run("sed -n '80,115p' /root/xiaozhi-server/main/yuhe-server/core/handle/sendAudioHandle.py", "sendAudioHandle 80-115")
    run("grep -n -A5 'vad' /root/xiaozhi-server/main/yuhe-server/config.yaml | head -25", "config.yaml VAD 配置")
    run("ls /root/xiaozhi-server/main/yuhe-server/core/providers/vad/ 2>/dev/null", "VAD 提供商列表")
finally:
    ssh.close()
    print("\n[done]")

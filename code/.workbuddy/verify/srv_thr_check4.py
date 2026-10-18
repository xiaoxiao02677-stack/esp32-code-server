# -*- coding: utf-8 -*-
# 找 client_is_speaking 置位点 + 拉取三个待改文件的精确代码段
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
    run("grep -rn 'client_is_speaking = ' /root/xiaozhi-server/main/yuhe-server/core/ --include='*.py' | grep -v __pycache__ | head", "client_is_speaking 置位点")
    run("sed -n '110,135p' /root/xiaozhi-server/main/yuhe-server/core/connection.py", "connection.py __init__ aec 段（110-135）")
    run("sed -n '157,205p' /root/xiaozhi-server/main/yuhe-server/core/services/wake_word_service.py", "wake_word_service.py push_device_config 通用体（157-205）")
finally:
    ssh.close()
    print("\n[done]")

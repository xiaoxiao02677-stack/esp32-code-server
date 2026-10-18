# -*- coding: utf-8 -*-
# 查 client_aec 赋值来源（hello 握手）+ websocket aec 特性声明
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
    run("grep -rn 'client_aec' /root/xiaozhi-server/main/yuhe-server/core/ --include='*.py' | head -15", "client_aec 赋值/使用点")
    run("grep -n -B5 -A10 'client_aec' /root/xiaozhi-server/main/yuhe-server/core/handle/helloHandle.py | head -50", "helloHandle 里 aec 声明")
    run("grep -n -B3 -A8 'features' /root/xiaozhi-server/main/yuhe-server/core/handle/helloHandle.py | head -40", "helloHandle features 处理")
finally:
    ssh.close()
    print("\n[done]")

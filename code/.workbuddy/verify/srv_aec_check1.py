# -*- coding: utf-8 -*-
# 查服务端是否支持 realtime 模式的服务端打断（server-side interrupt）
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
        print(o[:4000] if o.strip() else "(无输出)")
        if e.strip(): print("[stderr]", e[:300])
    # 1) 服务端 WS 协议里 listening mode / realtime 处理
    run("grep -rn 'realtime' /root/xiaozhi-server/main/core/ --include='*.py' -l | head", "realtime 关键词分布")
    # 2) 兜底：全 server 目录搜
    run("grep -rln 'realtime' /root/xiaozhi-server/main/ --include='*.py' | head -10", "全服务端 realtime 文件")
    # 3) 打断/interrupt 相关处理
    run("grep -rln 'interrupt' /root/xiaozhi-server/main/ --include='*.py' | head -10", "interrupt 文件")
finally:
    ssh.close()
    print("\n[done]")

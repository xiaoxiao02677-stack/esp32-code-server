# -*- coding: utf-8 -*-
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
import paramiko
ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect("sandyun.top", port=22222, username="root", timeout=30)
try:
    def run(cmd, label, t=50):
        print(f"\n===== {label} =====")
        _, out, err = ssh.exec_command(cmd, timeout=t)
        o = out.read().decode('utf-8', errors='replace')
        e = err.read().decode('utf-8', errors='replace')
        print(o[:3000] if o.strip() else "(无输出)")
        if e.strip(): print("[stderr]", e[:200])
    # 1) 找配置文件真实路径与含 password 的行（打码显示）
    run("ls /opt/xiaozhi/ && grep -rn 'password' /opt/xiaozhi/*.yml 2>/dev/null | sed 's/password:.*/password: ***/' | head -5", "找 yml")
    # 2) Python 侧配置（yuhe-server 的 .env / config）
    run("ls /root/xiaozhi-server/main/yuhe-server/.env 2>/dev/null && grep -c 'MYSQL\|DB_' /root/xiaozhi-server/main/yuhe-server/.env 2>/dev/null", "python .env")
    # 3) 直接看 python 服务进程的配置来源
    run("grep -rn 'password' /root/xiaozhi-server/main/yuhe-server/config*.yaml /root/xiaozhi-server/main/yuhe-server/data/.config.yaml 2>/dev/null | sed 's/password:.*/password: ***/' | head -5; find /root/xiaozhi-server -maxdepth 3 -name '*.yaml' -o -maxdepth 3 -name '.env' 2>/dev/null | head -8", "python 配置文件")
finally:
    ssh.close()
    print("\n[done]")

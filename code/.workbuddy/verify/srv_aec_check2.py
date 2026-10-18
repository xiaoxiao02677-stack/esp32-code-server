# -*- coding: utf-8 -*-
# 找服务端业务代码位置 + 查 realtime/interrupt 处理
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
    run("ls /root/xiaozhi-server/main/yuhe-server/ | head -20", "服务端根目录")
    run("find /root/xiaozhi-server -maxdepth 4 -name '*.py' -path '*core*' ! -path '*venv*' 2>/dev/null | head -15", "core py 文件（排除 venv）")
    run("grep -rn --include='*.py' --exclude-dir=.venv -l 'realtime' /root/xiaozhi-server/main/yuhe-server/ 2>/dev/null | head", "业务代码 realtime 文件")
    run("grep -rn --include='*.py' --exclude-dir=.venv -l 'interrupt' /root/xiaozhi-server/main/yuhe-server/ 2>/dev/null | head", "业务代码 interrupt 文件")
finally:
    ssh.close()
    print("\n[done]")

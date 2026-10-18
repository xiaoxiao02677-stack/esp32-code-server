# -*- coding: utf-8 -*-
# 重启 yuhe-server 并验证：进程起来 + 无启动报错 + 服务监听正常
import sys, io, time
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
        print(o[:3000] if o.strip() else "(no output)")
        if e.strip(): print("[stderr]", e[:400])
    run("systemctl restart yuhe-server && sleep 3 && systemctl is-active yuhe-server", "restart and status")
    run("journalctl -u yuhe-server --since '30 seconds ago' --no-pager | tail -25", "启动日志（错误排查）")
    run("ss -tlnp | grep -E ':8000|:8003|:12399' | head -5", "端口监听")
finally:
    ssh.close()
    print("\n[done]")

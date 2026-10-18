# -*- coding: utf-8 -*-
# 二次验证：等待启动完成后查端口/日志/WS 就绪
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
        print(o[:3500] if o.strip() else "(no output)")
        if e.strip(): print("[stderr]", e[:400])
    time.sleep(25)
    run("systemctl is-active yuhe-server && ss -tlnp | grep -E ':8000|:8003|:12399'", "status + ports")
    run("tail -20 /root/xiaozhi-server/main/yuhe-server/data/app.log", "app.log 尾部")
    run("journalctl -u yuhe-server --since '2 minutes ago' --no-pager | grep -iE 'error|traceback|exception' | head -10", "启动错误扫描")
finally:
    ssh.close()
    print("\n[done]")

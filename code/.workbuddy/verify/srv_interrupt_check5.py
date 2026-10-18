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
        print(o[:3500] if o.strip() else "(无输出)")
        if e.strip(): print("[stderr]", e[:200])
    # manager-api.log 是 Java 的应用日志！查 interrupt 相关
    run("grep -n '打断\|interrupt' /opt/xiaozhi/manager-api.log 2>/dev/null | tail -20", "Java manager-api.log 打断记录(尾部20)", 5000)
    # 21:50 后 Java 日志的 device config 保存动作
    run("grep -n '21:5[0-9]' /opt/xiaozhi/manager-api.log 2>/dev/null | grep -iE 'config|device|agent' | tail -20", "Java 21:50后 config/device/agent 动作", 5000)
finally:
    ssh.close()
    print("\n[done]")

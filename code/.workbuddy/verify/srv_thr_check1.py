# -*- coding: utf-8 -*-
# 查 interrupt_threshold 在 Python 服务端的处理路径（Java 推送 → 设备 WS）
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
    run("grep -rn 'interrupt_threshold' /root/xiaozhi-server/main/yuhe-server/core/ /root/xiaozhi-server/main/yuhe-server/*.py --include='*.py' 2>/dev/null | grep -v __pycache__ | head -20", "interrupt_threshold 全部分布")
    run("grep -rn 'device_config' /root/xiaozhi-server/main/yuhe-server/core/ --include='*.py' 2>/dev/null | grep -v __pycache__ | head -15", "device_config 下发路径")
finally:
    ssh.close()
    print("\n[done]")

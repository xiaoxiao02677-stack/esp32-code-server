# -*- coding: utf-8 -*-
# 查 push_device_config 实现 + conn 生命周期 + device_config 初始内容
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
        print(o[:6500] if o.strip() else "(无输出)")
        if e.strip(): print("[stderr]", e[:300])
    run("sed -n '280,350p' /root/xiaozhi-server/main/yuhe-server/core/services/wake_word_service.py", "push_device_config / push_interrupt_threshold 实现")
    run("sed -n '975,1000p' /root/xiaozhi-server/main/yuhe-server/core/connection.py", "connection.py device_config 初始下发段")
    run("grep -n 'client_is_speaking\\|client_voice_start\\|client_have_voice' /root/xiaozhi-server/main/yuhe-server/core/connection.py | head", "conn 音频状态字段")
finally:
    ssh.close()
    print("\n[done]")

# -*- coding: utf-8 -*-
# 查 config.yaml 完整 VAD 配置段（当前 threshold 值）
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
        print(o[:3500] if o.strip() else "(无输出)")
        if e.strip(): print("[stderr]", e[:300])
    run("grep -n -A8 '^VAD:' /root/xiaozhi-server/main/yuhe-server/config.yaml", "config.yaml VAD 段完整内容")
    run("grep -c 'feature.aec' /root/xiaozhi-server/main/yuhe-server/data/app.log 2>/dev/null; grep '客户端启用了服务端AEC' /root/xiaozhi-server/main/yuhe-server/data/app.log 2>/dev/null | tail -3", "历史日志：设备声明 AEC 记录（应为空=从未声明）")
finally:
    ssh.close()
    print("\n[done]")

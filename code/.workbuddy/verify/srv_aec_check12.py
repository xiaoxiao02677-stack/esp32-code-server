# -*- coding: utf-8 -*-
# connection.py 400-435 上下文（两处 queue.put 的来源）
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
    run("sed -n '380,435p' /root/xiaozhi-server/main/yuhe-server/core/connection.py", "connection.py 380-435")
    run("grep -rn 'async def handle_audio_message\\|def receive_ws\\|async def.*binary' /root/xiaozhi-server/main/yuhe-server/core/websocket_server.py | head", "websocket_server 二进制入口")
    run("grep -n -B3 -A15 'decode_opus\\|opus_decoder' /root/xiaozhi-server/main/yuhe-server/core/websocket_server.py | head -40", "websocket_server opus 解码")
finally:
    ssh.close()
    print("\n[done]")

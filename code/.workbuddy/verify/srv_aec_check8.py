# -*- coding: utf-8 -*-
# 查 websocket 收包路径：opus 解码 → 是否带时间戳/AEC → handleAudioMessage
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
    run("grep -n 'handleAudioMessage\\|_decode_opus\\|timestamp\\|header' /root/xiaozhi-server/main/yuhe-server/core/websocket_server.py | head -20", "websocket_server 关键点")
    run("grep -n -B5 -A20 'def _decode_opus_packet\\|handleAudioMessage' /root/xiaozhi-server/main/yuhe-server/core/connection.py | head -60", "connection.py 解码/音频入口")
finally:
    ssh.close()
    print("\n[done]")

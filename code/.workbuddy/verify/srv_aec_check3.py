# -*- coding: utf-8 -*-
# 查 dialogue.py 的 interrupt 逻辑 + websocket 的 listening mode 处理
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
        print(o[:5000] if o.strip() else "(无输出)")
        if e.strip(): print("[stderr]", e[:300])
    run("grep -n -B3 -A10 'interrupt' /root/xiaozhi-server/main/yuhe-server/core/utils/dialogue.py | head -60", "dialogue.py interrupt 逻辑")
    run("grep -n 'listen\|mode' /root/xiaozhi-server/main/yuhe-server/core/websocket_server.py | head -30", "websocket_server listen/mode 处理点")
    run("grep -n 'start_conversation\|tts stop\|sentence_start\|abort' /root/xiaozhi-server/main/yuhe-server/core/handle/audio_message_handle.py 2>/dev/null | head -20", "audio_message_handle 关键点")
    run("ls /root/xiaozhi-server/main/yuhe-server/core/handle/ 2>/dev/null", "handle 目录")
finally:
    ssh.close()
    print("\n[done]")

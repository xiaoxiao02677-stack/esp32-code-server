# -*- coding: utf-8 -*-
# 最后一环：WS 直连时设备 opus 包在哪解码？connection.py 的 message_handler
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
    run("grep -n 'asr_audio_queue.put\\|async def message_handler' /root/xiaozhi-server/main/yuhe-server/core/connection.py", "queue.put 与 message_handler 位置")
    run("grep -n -A30 'async def message_handler' /root/xiaozhi-server/main/yuhe-server/core/connection.py | head -45", "message_handler 全文（含 opus→pcm 与 timestamp 分支）")
finally:
    ssh.close()
    print("\n[done]")

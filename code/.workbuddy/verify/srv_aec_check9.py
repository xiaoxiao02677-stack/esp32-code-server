# -*- coding: utf-8 -*-
# 查 handleAudioMessage 的调用方（谁传 pcm_frame 进去）——websocket 直连时收的是裸 opus 还是有头部的包
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
    run("grep -rn 'handleAudioMessage' /root/xiaozhi-server/main/yuhe-server/core/ --include='*.py' | head", "handleAudioMessage 调用方")
    run("grep -n -B8 -A25 'audio_message\\|opcode.*BINARY\\|receive()' /root/xiaozhi-server/main/yuhe-server/core/connection.py | grep -A25 -B8 'async def message_handler\\|async def audio' | head -60", "connection.py 音频消息入口")
finally:
    ssh.close()
    print("\n[done]")

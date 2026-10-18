# -*- coding: utf-8 -*-
# 比对本地与生产三个文件是否一致（改前必查：避免版本漂移覆盖生产热修）
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
import paramiko
ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect("sandyun.top", port=22222, username="root", timeout=30)
try:
    files = [
        "core/handle/receiveAudioHandle.py",
        "core/connection.py",
        "core/services/wake_word_service.py",
    ]
    for f in files:
        cmd = f"md5sum /root/xiaozhi-server/main/yuhe-server/{f}"
        _, out, _ = ssh.exec_command(cmd, timeout=30)
        print(f.strip(), out.read().decode().split()[0][:12])
finally:
    ssh.close()

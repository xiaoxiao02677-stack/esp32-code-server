#!/usr/bin/env python3
"""SSH 启动 yuhe-server（setsid 后台，不挂 SSH 会话）"""
import sys
sys.path.insert(0, r"G:\demo\21_xiaozhi\code\.workbuddy")
from ssh_run import get_client

client = get_client()
# setsid + nohup + 输出重定向 + 关闭 stdin，get_pty=False，命令立即返回
cmd = (
    "cd /root/xiaozhi-server/main/yuhe-server && "
    "setsid nohup .venv/bin/python app.py > /tmp/yuhe-server.log 2>&1 < /dev/null & "
    "echo STARTED"
)
stdin, stdout, stderr = client.exec_command(cmd, timeout=20, get_pty=False)
print(stdout.read().decode())
client.close()

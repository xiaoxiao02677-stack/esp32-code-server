#!/usr/bin/env python3
"""SSH 后台启动 yuhe-server（完全剥离会话，避免 paramiko 读 stdout 阻塞）。"""
import sys
import time

sys.path.insert(0, r"G:\demo\21_xiaozhi\code\.workbuddy")
from ssh_run import get_client  # noqa: E402

START = (
    "cd /root/xiaozhi-server/main/yuhe-server && "
    "setsid nohup .venv/bin/python app.py > /tmp/yuhe-server.log "
    "2>&1 < /dev/null & disown; exit 0"
)

client = get_client()
try:
    client.exec_command(START, timeout=10)  # 不读 stdout，避免 channel 挂住
finally:
    time.sleep(2)
    client.close()

print("启动命令已下发，等待 15s 让服务初始化...")
time.sleep(15)

c2 = get_client()
try:
    _, out, _ = c2.exec_command(
        "ps -eo pid,etime,cmd | grep '[a]pp.py'; echo '--- 端口 ---'; "
        "ss -lntp 2>/dev/null | grep -E ':8000|:8003' | cut -c1-90; "
        "echo '--- 日志尾 ---'; tail -n 20 /tmp/yuhe-server.log",
        timeout=60,
    )
    print(out.read().decode("utf-8", "replace"))
finally:
    c2.close()

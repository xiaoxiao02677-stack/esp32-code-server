#!/usr/bin/env python3
"""重启线上 xiaozhi-server（Python）并验活。

用法：python restart_py_server.py
"""
import sys
import time

sys.path.insert(0, r"G:\demo\21_xiaozhi\code\.workbuddy")
from ssh_run import get_client  # noqa: E402


def sh(client, cmd, timeout=120):
    _, out, err = client.exec_command(cmd, timeout=timeout)
    o = out.read().decode("utf-8", "replace").strip()
    e = err.read().decode("utf-8", "replace").strip()
    return out.channel.recv_exit_status(), o, e


def main():
    client = get_client()
    try:
        print("[1/5] 当前进程")
        rc, o, e = sh(client, "ps -eo pid,etime,cmd | grep '[a]pp.py'")
        print(o or "(无)")

        print("\n[2/5] 停止")
        sh(client, "pkill -f 'xiaozhi-server/main/xiaozhi-server'; "
                   "pkill -f 'venv/bin/python app.py'; sleep 3; true")
        rc, o, e = sh(client, "ps -eo pid,cmd | grep '[a]pp.py' | wc -l")
        print("剩余 app.py 进程数:", o)

        print("\n[3/5] 启动")
        sh(client, "cd /root/xiaozhi-server/main/xiaozhi-server && "
                   "setsid nohup .venv/bin/python app.py > /tmp/xiaozhi-server.log "
                   "2>&1 < /dev/null & echo STARTED", timeout=20)
        time.sleep(12)

        print("\n[4/5] 进程与端口")
        rc, o, e = sh(client, "ps -eo pid,etime,cmd | grep '[a]pp.py'")
        print(o or "(无进程!)")
        rc, o, e = sh(client, "ss -lntp 2>/dev/null | grep -E ':8000|:8003' || "
                              "netstat -lntp 2>/dev/null | grep -E ':8000|:8003'")
        print("监听:", o or "(未监听!)")

        print("\n[5/5] 日志尾部")
        rc, o, e = sh(client, "tail -n 40 /tmp/xiaozhi-server.log")
        print(o)
        rc, o, e = sh(client, "grep -iE 'traceback|error|exception' "
                              "/tmp/xiaozhi-server.log | tail -15")
        print("--- 错误行 ---")
        print(o or "(无错误)")
    finally:
        client.close()


if __name__ == "__main__":
    main()

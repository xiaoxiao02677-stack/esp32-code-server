#!/usr/bin/env python3
"""恢复被部署脚本超时打断的 Python 服务启动 + 全量验活。"""
import sys
import time

sys.path.insert(0, r"G:\demo\21_xiaozhi\code\.workbuddy")
from ssh_run import get_client  # noqa: E402


def sh(client, cmd, timeout=60, read=True):
    _, out, err = client.exec_command(cmd, timeout=timeout)
    if read:
        o = out.read().decode("utf-8", "replace").strip()
        e = err.read().decode("utf-8", "replace").strip()
        rc = out.channel.recv_exit_status()
        if o:
            print(o[-500:])
        if e and rc != 0:
            print("[stderr]", e[-300:])
        return rc, o
    # 后台命令：不读 stdout，直接关 channel（防挂起，历史踩坑记录）
    time.sleep(2)
    out.channel.close()
    return 0, ""


def main():
    client = get_client()
    try:
        print("[1] app.py 进程状态")
        rc, o = sh(client, "ps -eo pid,etime,cmd | grep '[a]pp.py' | head -3")
        if not o:
            print("!! 无进程，需要启动")

        print("\n[2] 启动（后台不读 stdout）")
        sh(client, "cd /root/xiaozhi-server/main/yuhe-server && "
                   "setsid nohup .venv/bin/python app.py > /tmp/yuhe-server.log 2>&1 < /dev/null &",
            read=False)
        time.sleep(15)

        print("\n[3] 验活")
        sh(client, "ps -eo pid,etime,cmd | grep '[a]pp.py' | head -3")
        sh(client, "ss -lnt | grep -E ':(8000|8003|12399)'")
        sh(client, "curl -s -o /dev/null -w 'manager-api 8002: %{http_code}\\n' http://127.0.0.1:8002/yuhe/user/pub-config")
        sh(client, "tail -5 /tmp/yuhe-server.log")
    finally:
        client.close()


if __name__ == "__main__":
    main()

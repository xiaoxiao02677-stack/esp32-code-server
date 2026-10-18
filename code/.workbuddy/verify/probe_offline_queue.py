#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""只读探针：确认「双键 payload 已进入 python 离线队列」及 python 未重启。

只执行 grep / ps / ss / stat，不写任何文件、不重启任何服务。
"""
import paramiko

HOST, PORT, USER, PASSWORD = "sandyun.top", 22222, "root", "Ymm6088."

c = paramiko.SSHClient()
c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect(HOST, port=PORT, username=USER, password=PASSWORD, timeout=25,
          look_for_keys=False, allow_agent=False)


def sh(cmd, t=120):
    _, o, e = c.exec_command(cmd, timeout=t)
    return o.read().decode("utf-8", "replace").strip(), e.read().decode("utf-8", "replace").strip()


print("=== 1) python 进程与启动时刻（确认未重启）===")
print(sh("systemctl show yuhe-server -p MainPID -p NRestarts -p ActiveEnterTimestamp")[0])
print(sh("ps -o pid,lstart,etime,cmd -p $(systemctl show -p MainPID --value yuhe-server) 2>/dev/null")[0])

print("\n=== 2) 离线队列入队日志（唤醒词已缓存至 N 个离线设备）===")
out, _ = sh("grep -n '已缓存至' /opt/xiaozhi/yuhe-server/data/app.log | tail -10")
print(out or "(无)")

print("\n=== 3) 最近 3 次唤醒词推送的返回（含 offline 计数）===")
out, _ = sh("grep -nE '唤醒词已缓存|向设备 .* 推送唤醒词|已下发云端设备配置' "
            "/opt/xiaozhi/yuhe-server/data/app.log | tail -12")
print(out or "(无)")

print("\n=== 4) 设备 44bd 最近 WS/心跳痕迹 ===")
out, _ = sh("grep -nE '44bd8d7b3ae4' /opt/xiaozhi/yuhe-server/data/app.log | tail -12")
print(out or "(无)")

print("\n=== 5) 8000/8003 监听与 PID 归属 ===")
print(sh("ss -lntp 2>/dev/null | grep -E ':8000|:8003|:12399' | sed -E 's/users:.*//'")[0])

c.close()

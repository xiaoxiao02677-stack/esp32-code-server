#!/usr/bin/env python3
"""部署 PROXY protocol：打通设备真实 IP 到 Python 日志。

步骤：
  1. 备份 nginx.conf 与站点配置
  2. 新增 127.0.0.1:9002 / 9444 的 proxy_protocol 上游 server
  3. 改写 stream 块：proxy_protocol on + 上游改指 9002/9444 + 加 stream 访问日志
  4. nginx -t 通过才 reload（失败则中止，不碰线上）
  5. 从外网分别用 ws:// 和 wss:// 连 8001，验证日志出现真实公网 IP
"""
import re
import socket
import ssl
import time

import paramiko

HOST, PORT, USER, PASSWORD = "sandyun.top", 22222, "root", "Ymm6088."
PUB_HOST = "sandyun.top"
PUB_PORT = 8001
STAMP = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())

NEW_STREAM = """stream {
    # 设备接入层访问日志：记录真实设备 IP（按 IP 定位问题用）
    log_format device '$remote_addr [$time_local] -> $upstream_addr';
    access_log /var/log/nginx/stream-8001.log device buffer=32k flush=5s;

    map $ssl_preread_protocol $upstream_8001 {
        ""        127.0.0.1:9002;
        default   127.0.0.1:9444;
    }
    server {
        listen 8001;
        ssl_preread on;
        # 2026-10-09 真实 IP 修复：向下游发送 PROXY protocol 头。
        # 下游 127.0.0.1:9002(明文)/9444(TLS) 以 listen ... proxy_protocol 接收，
        # 再由 realip 模块把 $remote_addr 还原成设备真实公网 IP。
        # 回滚：把上面 map 改回 127.0.0.1:9001 / 9443 并去掉本行即可。
        proxy_protocol on;
        proxy_pass $upstream_8001;
        proxy_timeout 3600s;
    }
}"""


def ws_probe(tls, devid):
    """从本机（外网）连 8001 做 WS 握手探针。"""
    req = (
        f"GET /xiaozhi/v1/?device-id={devid} HTTP/1.1\r\n"
        f"Host: {PUB_HOST}:{PUB_PORT}\r\n"
        "Upgrade: websocket\r\n"
        "Connection: Upgrade\r\n"
        "Sec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==\r\n"
        "Sec-WebSocket-Version: 13\r\n"
        f"User-Agent: ip-probe-{devid}\r\n\r\n"
    )
    s = socket.create_connection((PUB_HOST, PUB_PORT), timeout=15)
    if tls:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        s = ctx.wrap_socket(s, server_hostname=PUB_HOST)
    s.sendall(req.encode())
    try:
        data = s.recv(2048)
    except Exception as e:
        data = f"<recv err {e}>".encode()
    s.close()
    tag = "wss" if tls else "ws "
    print(f"  [{tag}] {devid}: {data[:100]!r}")


def main():
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect(HOST, port=PORT, username=USER, password=PASSWORD,
              timeout=20, look_for_keys=False, allow_agent=False)
    sftp = c.open_sftp()

    def sh(cmd, t=180):
        _, o, e = c.exec_command(cmd, timeout=t)
        return (o.read().decode("utf-8", "replace").strip(),
                e.read().decode("utf-8", "replace").strip())

    print("=" * 64)
    print("步骤 1: 备份")
    print("=" * 64)
    sh(f"cp -a /etc/nginx/nginx.conf /etc/nginx/nginx.conf.bak-{STAMP}")
    sh(f"cp -a /etc/nginx/sites-available/xiaozhi-manager "
       f"/etc/nginx/sites-available/xiaozhi-manager.bak-{STAMP}")
    print(sh(f"ls -l /etc/nginx/nginx.conf.bak-{STAMP}")[0])

    print()
    print("=" * 64)
    print("步骤 2: 新增 9002/9444 proxy_protocol 上游")
    print("=" * 64)
    sftp.put(r"G:\demo\21_xiaozhi\code\.workbuddy\nginx-device-proxy-protocol.conf",
             "/etc/nginx/sites-available/xiaozhi-device-pp")
    sh("ln -sf /etc/nginx/sites-available/xiaozhi-device-pp "
       "/etc/nginx/sites-enabled/xiaozhi-device-pp")
    print(sh("ls -l /etc/nginx/sites-enabled/")[0])

    print()
    print("=" * 64)
    print("步骤 3: 改写 stream 块")
    print("=" * 64)
    with sftp.open("/etc/nginx/nginx.conf", "r") as f:
        content = f.read().decode("utf-8")
    new_content, n = re.subn(r"stream\s*\{.*?\n\}", NEW_STREAM, content,
                             flags=re.DOTALL)
    print(f"替换 stream 块数量: {n}")
    assert n == 1, "未找到或找到多个 stream 块，中止"
    with sftp.open("/etc/nginx/nginx.conf", "w") as f:
        f.write(new_content.encode("utf-8"))
    print(sh("sed -n '/^stream {/,/^}/p' /etc/nginx/nginx.conf")[0])

    print()
    print("=" * 64)
    print("步骤 4: nginx -t（不通就中止，不 reload）")
    print("=" * 64)
    o, e = sh("nginx -t 2>&1")
    print(o, e)
    if "test is successful" not in o:
        print("!!! nginx -t 失败，已中止，线上未受影响")
        sftp.close(); c.close()
        return

    print()
    print("=" * 64)
    print("步骤 5: reload 并确认新端口监听")
    print("=" * 64)
    print(sh("systemctl reload nginx")[0] or "(reload ok)")
    print(sh("ss -lntp | grep -E ':9002|:9444|:8001'")[0])

    print()
    print("=" * 64)
    print("步骤 6: 外网探针（ws:// 与 wss:// 各一次）")
    print("=" * 64)
    ws_probe(False, "ppprobe-plain")
    ws_probe(True, "ppprobe-tls")
    time.sleep(6)

    print("\n本机（SSH 会话）公网 IP 参照:")
    print("  " + sh("who | awk '{print $5}' | tr -d '()' | sort -u | head -3")[0])

    print("\nstream 层日志（应出现真实公网 IP）:")
    print("  " + (sh("tail -5 /var/log/nginx/stream-8001.log")[0] or "(空)"))

    print("\nPython 日志里的连接 IP（关键）:")
    print("  " + (sh(r"grep -E 'conn - Headers' "
                     r"/root/xiaozhi-server/main/xiaozhi-server/data/app.log "
                     r"| tail -5")[0] or "(无)"))

    sftp.close(); c.close()
    print("\n完成。")


if __name__ == "__main__":
    main()

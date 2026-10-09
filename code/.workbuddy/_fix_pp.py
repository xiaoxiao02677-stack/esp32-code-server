#!/usr/bin/env python3
"""重新上传完整版 9002/9444 server 块并验证：网页 + WS 真实 IP 都不能坏。"""
import socket, ssl, time, paramiko
HOST, PORT, USER, PASSWORD = "sandyun.top", 22222, "root", "Ymm6088."
c = paramiko.SSHClient(); c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect(HOST, port=PORT, username=USER, password=PASSWORD, timeout=20, look_for_keys=False, allow_agent=False)
sftp = c.open_sftp()
def sh(cmd, t=180):
    _, o, e = c.exec_command(cmd, timeout=t)
    return o.read().decode("utf-8","replace").strip(), e.read().decode("utf-8","replace").strip()

sftp.put(r"G:\demo\21_xiaozhi\code\.workbuddy\nginx-device-proxy-protocol.conf",
         "/etc/nginx/sites-available/xiaozhi-device-pp")
o, e = sh("nginx -t 2>&1")
print("nginx -t:", o)
assert "successful" in o, "配置不合法，中止"
sh("systemctl reload nginx"); time.sleep(2)

print("\n=== 网页回归（必须与旧 9443 一致）===")
for p in ["/", "/admincc/", "/cc/"]:
    a = sh(f"curl -sk -o /dev/null -w '%{{http_code}}' https://127.0.0.1:8001{p}")[0]
    b = sh(f"curl -sk -o /dev/null -w '%{{http_code}}' https://127.0.0.1:9443{p}")[0]
    print(f"  {p:12s} 8001(stream->9444)={a}   9443(旧)={b}   {'OK' if a==b else '不一致!'}")
print("  / 的标题:", sh("curl -sk https://127.0.0.1:8001/ | grep -o '<title>[^<]*</title>'")[0])
print("  旧块标题:", sh("curl -sk https://127.0.0.1:9443/ | grep -o '<title>[^<]*</title>'")[0])

def ws_probe(tls, devid):
    req = (f"GET /xiaozhi/v1/?device-id={devid} HTTP/1.1\r\nHost: sandyun.top:8001\r\n"
           "Upgrade: websocket\r\nConnection: Upgrade\r\n"
           "Sec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==\r\nSec-WebSocket-Version: 13\r\n"
           f"User-Agent: ip-probe-{devid}\r\n\r\n")
    s = socket.create_connection(("sandyun.top", 8001), timeout=15)
    if tls:
        ctx = ssl.create_default_context(); ctx.check_hostname=False; ctx.verify_mode=ssl.CERT_NONE
        s = ctx.wrap_socket(s, server_hostname="sandyun.top")
    s.sendall(req.encode())
    d = s.recv(2048); s.close()
    print(f"  [{'wss' if tls else 'ws '}] {devid}: {d[:60]!r}")

print("\n=== 真实 IP 回归 ===")
ws_probe(False, "ppfix-plain"); ws_probe(True, "ppfix-tls")
time.sleep(6)
print("  stream 层:", sh("tail -3 /var/log/nginx/stream-8001.log")[0])
print("  Python 日志:")
print("   " + sh(r"grep -E 'conn - Headers' /root/xiaozhi-server/main/xiaozhi-server/data/app.log | tail -3")[0])
sftp.close(); c.close()

#!/usr/bin/env python3
"""收敛端口 + 公共 location 抽 snippet：备份 → 上传 → -t → reload → 全面回归。"""
import socket
import ssl
import time

import paramiko

HOST, PORT, USER, PASSWORD = "sandyun.top", 22222, "root", "Ymm6088."
STAMP = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
LOCAL = r"G:\demo\21_xiaozhi\code\.workbuddy"


def ws_probe(tls, devid, host="sandyun.top", port=8001):
    req = (f"GET /xiaozhi/v1/?device-id={devid} HTTP/1.1\r\n"
           f"Host: {host}:{port}\r\n"
           "Upgrade: websocket\r\nConnection: Upgrade\r\n"
           "Sec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==\r\n"
           "Sec-WebSocket-Version: 13\r\n"
           f"User-Agent: ip-probe-{devid}\r\n\r\n")
    try:
        s = socket.create_connection((host, port), timeout=10)
        if tls:
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
            s = ctx.wrap_socket(s, server_hostname=host)
        s.sendall(req.encode())
        d = s.recv(2048)
        s.close()
        return d[:40].decode("utf-8", "replace").strip()
    except Exception as e:
        return f"失败: {type(e).__name__} {e}"


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

    print("=" * 62)
    print("步骤 1: 备份现有站点配置")
    print("=" * 62)
    for f in ("xiaozhi-manager", "xiaozhi-device-pp"):
        sh(f"cp -a /etc/nginx/sites-available/{f} "
           f"/etc/nginx/sites-available/{f}.bak-{STAMP} 2>/dev/null || true")
    print(sh(f"ls -l /etc/nginx/sites-available/*.bak-{STAMP}")[0])

    print()
    print("=" * 62)
    print("步骤 2: 上传 snippet 与两个 server 块")
    print("=" * 62)
    sftp.put(rf"{LOCAL}\nginx-snippet-xiaozhi-common.conf",
             "/etc/nginx/snippets/xiaozhi-common.conf")
    sftp.put(rf"{LOCAL}\nginx-site-xiaozhi-manager.conf",
             "/etc/nginx/sites-available/xiaozhi-manager")
    sftp.put(rf"{LOCAL}\nginx-device-proxy-protocol.conf",
             "/etc/nginx/sites-available/xiaozhi-device-pp")
    sh("chmod 644 /etc/nginx/snippets/xiaozhi-common.conf "
       "/etc/nginx/sites-available/xiaozhi-manager "
       "/etc/nginx/sites-available/xiaozhi-device-pp")
    print("已上传：snippets/xiaozhi-common.conf、xiaozhi-manager、xiaozhi-device-pp")

    print()
    print("=" * 62)
    print("步骤 3: nginx -t（不通就中止）")
    print("=" * 62)
    o, e = sh("nginx -t 2>&1")
    print(o)
    if "successful" not in o:
        print("!!! 配置不合法，已中止，线上未受影响")
        sftp.close(); c.close(); return

    sh("systemctl reload nginx"); time.sleep(2)
    print("\nreload 完成，监听情况:")
    print(sh("ss -lntp | grep -E ':9001|:9002|:9443|:9444|:8443|:8001' "
             "| sed -E 's/users:.*//' | sort -u")[0])

    print()
    print("=" * 62)
    print("步骤 4: 回归 —— 网页（8001 与 8443 都必须正常）")
    print("=" * 62)
    for p in ["/", "/admincc/", "/cc/"]:
        a = sh(f"curl -sk -o /dev/null -w '%{{http_code}}' https://127.0.0.1:8001{p}")[0]
        b = sh(f"curl -sk -o /dev/null -w '%{{http_code}}' https://127.0.0.1:8443{p}")[0]
        print(f"  {p:12s} 8001={a}  8443={b}  {'OK' if a == b == '200' else '不一致!'}")
    print("  / 标题:", sh("curl -sk https://127.0.0.1:8001/ | grep -o '<title>[^<]*</title>'")[0])
    print("  /xiaozhi/ API:", sh("curl -sk -o /dev/null -w '%{http_code}' "
                                "https://127.0.0.1:8001/xiaozhi/")[0])

    print()
    print("=" * 62)
    print("步骤 5: 回归 —— 真实 IP（ws:// 与 wss://）")
    print("=" * 62)
    print("  ws :", ws_probe(False, "refactor-plain"))
    print("  wss:", ws_probe(True, "refactor-tls"))
    time.sleep(6)
    print("  stream 层:", sh("tail -2 /var/log/nginx/stream-8001.log")[0])
    print("  Python 日志:")
    print("   " + sh(r"grep -E 'conn - Headers' "
                     r"/root/xiaozhi-server/main/xiaozhi-server/data/app.log "
                     r"| tail -2 | cut -c1-190")[0])

    print()
    print("=" * 62)
    print("步骤 6: 回归 —— 外部已无法直连 9001/9443")
    print("=" * 62)
    for p in (9001, 9443, 8443):
        s = socket.socket(); s.settimeout(6)
        try:
            s.connect(("sandyun.top", p))
            print(f"  :{p} 仍可从外网连通")
        except Exception as ex:
            print(f"  :{p} 外网不可达 ({type(ex).__name__})  <-- 预期：9001/9443 应不可达")
        finally:
            s.close()

    sftp.close(); c.close()
    print("\n完成。")


if __name__ == "__main__":
    main()

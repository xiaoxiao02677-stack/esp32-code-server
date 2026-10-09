import paramiko, time, socket, ssl
HOST, PORT, USER, PASSWORD = "sandyun.top", 22222, "root", "Ymm6088."
c = paramiko.SSHClient(); c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect(HOST, port=PORT, username=USER, password=PASSWORD, timeout=20, look_for_keys=False, allow_agent=False)
def sh(cmd, t=180):
    _, o, e = c.exec_command(cmd, timeout=t)
    return o.read().decode("utf-8","replace").strip(), e.read().decode("utf-8","replace").strip()

print("重启前监听:", sh("ss -lnt | grep -E ':9001|:9443' | awk '{print $4}' | tr '\n' ' '")[0])
print("\n执行 systemctl restart nginx ...")
print(sh("systemctl restart nginx; sleep 3; systemctl is-active nginx")[0])
print("\n重启后监听:")
print(sh("ss -lnt | grep -E ':9001|:9443|:9002|:9444|:8443|:8001' | awk '{print $4}' | sort | uniq -c")[0])
print("\nerror.log 是否还有 bind 失败:", sh("grep -c 'still could not bind' /var/log/nginx/error.log")[0])

IP="192.168.50.4"
print(f"\n=== 非回环地址 {IP}（9001/9443 应拒绝，8443 应通）===")
for p, sch in ((9001,"http"),(9443,"https"),(8443,"https")):
    k = "-k" if sch=="https" else ""
    code = sh(f"curl -sk -m 5 -o /dev/null -w '%{{http_code}}' {sch}://{IP}:{p}/ 2>/dev/null || echo REFUSED")[0]
    print(f"  {sch}://{IP}:{p} -> {code}")
print("\n=== 回环（9001/9443 应保持可用，作为回滚兜底）===")
print("  127.0.0.1:9001 ->", sh("curl -s -m 5 -o /dev/null -w '%{http_code}' http://127.0.0.1:9001/")[0])
print("  127.0.0.1:9443 ->", sh("curl -sk -m 5 -o /dev/null -w '%{http_code}' https://127.0.0.1:9443/")[0])

def ws_probe(tls, devid):
    req=(f"GET /xiaozhi/v1/?device-id={devid} HTTP/1.1\r\nHost: sandyun.top:8001\r\n"
         "Upgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==\r\n"
         f"Sec-WebSocket-Version: 13\r\nUser-Agent: ip-probe-{devid}\r\n\r\n")
    s=socket.create_connection(("sandyun.top",8001),timeout=10)
    if tls:
        ctx=ssl.create_default_context(); ctx.check_hostname=False; ctx.verify_mode=ssl.CERT_NONE
        s=ctx.wrap_socket(s,server_hostname="sandyun.top")
    s.sendall(req.encode()); d=s.recv(2048); s.close()
    return d[:38].decode("utf-8","replace").strip()

print("\n=== 重启后回归：网页 + 真实 IP ===")
for p in ["/","/admincc/","/cc/"]:
    print(f"  8001 {p:11s} ->", sh(f"curl -sk -o /dev/null -w '%{{http_code}}' https://127.0.0.1:8001{p}")[0])
print("  标题:", sh("curl -sk https://127.0.0.1:8001/ | grep -o '<title>[^<]*</title>'")[0])
print("  ws :", ws_probe(False,"postrestart-plain"))
print("  wss:", ws_probe(True,"postrestart-tls"))
time.sleep(6)
print("  stream:", sh("tail -2 /var/log/nginx/stream-8001.log")[0])
print("  Python:", sh(r"grep -E 'conn - Headers' /root/xiaozhi-server/main/xiaozhi-server/data/app.log | tail -2 | cut -c1-150")[0])
c.close()

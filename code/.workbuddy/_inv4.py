import paramiko
HOST, PORT, USER, PASSWORD = "sandyun.top", 22222, "root", "Ymm6088."
c = paramiko.SSHClient(); c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect(HOST, port=PORT, username=USER, password=PASSWORD, timeout=20, look_for_keys=False, allow_agent=False)
def sh(cmd, t=120):
    _, o, e = c.exec_command(cmd, timeout=t)
    return o.read().decode("utf-8","replace").strip(), e.read().decode("utf-8","replace").strip()
print("=== nginx 版本 ===")
print(sh("nginx -v 2>&1")[0])
print("\n=== 谁在监听 9001 / 9443 / 8000 ===")
print(sh("ss -lntp | grep -E ':9001|:9443|:8000|:8001'")[0])
print("\n=== 9001 server 块 ===")
print(sh("nginx -T 2>/dev/null | grep -n -B3 -A25 'listen.*9001' | head -60")[0])
print("\n=== 9443 server 块 ===")
print(sh("nginx -T 2>/dev/null | grep -n -B3 -A20 'listen.*9443' | head -50")[0])
print("\n=== app.log 是否有重启前历史 ===")
print(sh("head -2 /root/xiaozhi-server/main/xiaozhi-server/data/app.log; echo ...; tail -2 /root/xiaozhi-server/main/xiaozhi-server/data/app.log")[0])
c.close()

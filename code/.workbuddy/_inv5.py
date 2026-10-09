import paramiko
HOST, PORT, USER, PASSWORD = "sandyun.top", 22222, "root", "Ymm6088."
c = paramiko.SSHClient(); c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect(HOST, port=PORT, username=USER, password=PASSWORD, timeout=20, look_for_keys=False, allow_agent=False)
def sh(cmd, t=120):
    _, o, e = c.exec_command(cmd, timeout=t)
    return o.read().decode("utf-8","replace").strip(), e.read().decode("utf-8","replace").strip()
print("=== ufw / 防火墙 ===")
print(sh("ufw status 2>&1 | head -20")[0])
print("\n=== 9001/9443/8443 访问日志（是否有人直连） ===")
print(sh("nginx -T 2>/dev/null | grep -n 'access_log' | head")[0])
print(sh("ls -la /var/log/nginx/ | head -20")[0])
print("\n=== 最近 access.log 里 9001/9443 的记录 ===")
print(sh("tail -3000 /var/log/nginx/access.log 2>/dev/null | awk '{print $NF}' | sort | uniq -c | head")[0] or "(access.log 无或空)")
print("\n=== stream 层有没有 access_log ===")
print(sh("nginx -T 2>/dev/null | grep -n -A8 'stream {' | head -20")[0])
c.close()

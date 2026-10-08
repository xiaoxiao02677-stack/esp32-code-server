import paramiko
HOST, PORT, USER, PASSWORD = "sandyun.top", 22222, "root", "Ymm6088."
c = paramiko.SSHClient(); c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect(HOST, port=PORT, username=USER, password=PASSWORD, timeout=20, look_for_keys=False, allow_agent=False)
def sh(cmd, t=60):
    _, o, e = c.exec_command(cmd, timeout=t)
    return o.read().decode("utf-8","replace").strip()
print(sh("ls /root/xiaozhi-server/main/xiaozhi-server | head -30"))
print("--- yml ---")
print(sh("find /root/xiaozhi-server -maxdepth 5 -name 'application*.yml' 2>/dev/null | head"))
print("--- dscfg ---")
print(sh("grep -rn -A8 'datasource:' $(find /root/xiaozhi-server -maxdepth 6 -name 'application.yml' 2>/dev/null | head -1) 2>/dev/null | head -20"))
c.close()

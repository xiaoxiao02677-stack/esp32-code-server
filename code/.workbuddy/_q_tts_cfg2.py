import paramiko
HOST, PORT, USER, PASSWORD = "sandyun.top", 22222, "root", "Ymm6088."
c = paramiko.SSHClient(); c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect(HOST, port=PORT, username=USER, password=PASSWORD, timeout=20, look_for_keys=False, allow_agent=False)
def sh(cmd, t=60):
    _, o, e = c.exec_command(cmd, timeout=t)
    return o.read().decode("utf-8","replace").strip()
print("=== datasource ===")
print(sh("grep -rn -A6 'datasource' /root/xiaozhi-server/main/xiaozhi-server/manager-api/src/main/resources/application.yml 2>/dev/null | head -20 || find / -name application.yml -path '*manager-api*' 2>/dev/null | head"))
c.close()

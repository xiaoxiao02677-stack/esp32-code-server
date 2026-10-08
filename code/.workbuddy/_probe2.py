import paramiko
HOST, PORT, USER, PASSWORD = "sandyun.top", 22222, "root", "Ymm6088."
c = paramiko.SSHClient(); c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect(HOST, port=PORT, username=USER, password=PASSWORD, timeout=20, look_for_keys=False, allow_agent=False)
def sh(cmd, t=200):
    _, o, e = c.exec_command(cmd, timeout=t)
    return o.read().decode("utf-8","replace").strip(), e.read().decode("utf-8","replace").strip()
print(sh("cat /etc/systemd/system/xiaozhi-server.service | grep -E 'ExecStart|WorkingDirectory|User' | head"))
print(sh("ls /root/xiaozhi-server/main/xiaozhi-server/.venv/bin/python* 2>/dev/null | head"))
c.close()

import paramiko
HOST, PORT, USER, PASSWORD = "sandyun.top", 22222, "root", "Ymm6088."
c = paramiko.SSHClient(); c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect(HOST, port=PORT, username=USER, password=PASSWORD, timeout=20, look_for_keys=False, allow_agent=False)
sftp = c.open_sftp()
sftp.put(r"G:\demo\21_xiaozhi\code\.workbuddy\server_tts_probe.py", "/tmp/server_tts_probe.py")
def sh(cmd, t=240):
    _, o, e = c.exec_command(cmd, timeout=t)
    return o.read().decode("utf-8","replace").strip(), e.read().decode("utf-8","replace").strip()
o,e = sh("cd /root/xiaozhi-server/main/yuhe-server && .venv/bin/python /tmp/server_tts_probe.py")
print(o); print("[ERR]", e)
c.close()

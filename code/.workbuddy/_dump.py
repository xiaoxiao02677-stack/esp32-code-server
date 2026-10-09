import paramiko
HOST, PORT, USER, PASSWORD = "sandyun.top", 22222, "root", "Ymm6088."
c = paramiko.SSHClient(); c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect(HOST, port=PORT, username=USER, password=PASSWORD, timeout=20, look_for_keys=False, allow_agent=False)
def sh(cmd, t=120):
    _, o, e = c.exec_command(cmd, timeout=t)
    return o.read().decode("utf-8","replace").strip(), e.read().decode("utf-8","replace").strip()
print("=== nginx.conf 全文（80行后） ===")
print(sh("sed -n '55,120p' /etc/nginx/nginx.conf")[0])
print("\n=== sites-enabled 列表 ===")
print(sh("ls -l /etc/nginx/sites-enabled/")[0])
print("\n=== xiaozhi-manager 全文 ===")
o,_ = sh("cat /etc/nginx/sites-enabled/xiaozhi-manager")
print(o)
c.close()

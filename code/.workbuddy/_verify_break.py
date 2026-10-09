import paramiko, ssl, socket
HOST, PORT, USER, PASSWORD = "sandyun.top", 22222, "root", "Ymm6088."
c = paramiko.SSHClient(); c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect(HOST, port=PORT, username=USER, password=PASSWORD, timeout=20, look_for_keys=False, allow_agent=False)
def sh(cmd, t=120):
    _, o, e = c.exec_command(cmd, timeout=t)
    return o.read().decode("utf-8","replace").strip(), e.read().decode("utf-8","replace").strip()
print("从服务器本机 curl https://127.0.0.1:8001/ （模拟浏览器走 stream）:")
print(sh("curl -sk -o /dev/null -w 'HTTP %{http_code}\n' https://127.0.0.1:8001/")[0])
print("\n直连 9443（旧路径）:")
print(sh("curl -sk -o /dev/null -w 'HTTP %{http_code}\n' https://127.0.0.1:9443/")[0])
c.close()

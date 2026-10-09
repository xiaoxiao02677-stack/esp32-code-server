import paramiko
HOST, PORT, USER, PASSWORD = "sandyun.top", 22222, "root", "Ymm6088."
c = paramiko.SSHClient(); c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect(HOST, port=PORT, username=USER, password=PASSWORD, timeout=20, look_for_keys=False, allow_agent=False)
def sh(cmd, t=120):
    _, o, e = c.exec_command(cmd, timeout=t)
    return o.read().decode("utf-8","replace").strip(), e.read().decode("utf-8","replace").strip()
print("=== 经 8001 (stream->9444 新块) 的 / 内容前 300 字符 ===")
print(sh("curl -sk https://127.0.0.1:8001/ | head -c 300")[0])
print("\n=== 直连 9443 (旧块) 的 / 内容前 300 字符 ===")
print(sh("curl -sk https://127.0.0.1:9443/ | head -c 300")[0])
print("\n=== /admincc/ 对比 ===")
print("8001:", sh("curl -sk -o /dev/null -w '%{http_code}' https://127.0.0.1:8001/admincc/")[0])
print("9443:", sh("curl -sk -o /dev/null -w '%{http_code}' https://127.0.0.1:9443/admincc/")[0])
c.close()

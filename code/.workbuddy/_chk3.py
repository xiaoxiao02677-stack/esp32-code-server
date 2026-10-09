import paramiko
HOST, PORT, USER, PASSWORD = "sandyun.top", 22222, "root", "Ymm6088."
c = paramiko.SSHClient(); c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect(HOST, port=PORT, username=USER, password=PASSWORD, timeout=20, look_for_keys=False, allow_agent=False)
def sh(cmd, t=120):
    _, o, e = c.exec_command(cmd, timeout=t)
    return o.read().decode("utf-8","replace").strip(), e.read().decode("utf-8","replace").strip()
print("=== error.log 最近 bind 相关 ===")
print(sh("grep -iE 'bind|emerg|alert' /var/log/nginx/error.log | tail -10")[0] or "(无)")
print("\n=== 服务器网卡 IP ===")
print(sh("hostname -I")[0])
print("\n=== 完整监听（ss -lntp 不截断）===")
print(sh("ss -lntp 2>/dev/null | grep -E ':9001|:9443' | sed -E 's/users:.*//' ")[0])
IP = sh("hostname -I")[0].split()[0]
print(f"\n=== 从本机访问非回环地址 {IP}:9001 / :9443（应拒绝）===")
print("9001:", sh(f"curl -s -m 5 -o /dev/null -w '%{{http_code}}' http://{IP}:9001/ ; echo ' (curl退出码' $? ')'")[0])
print("9443:", sh(f"curl -sk -m 5 -o /dev/null -w '%{{http_code}}' https://{IP}:9443/")[0])
print("8443:", sh(f"curl -sk -m 5 -o /dev/null -w '%{{http_code}}' https://{IP}:8443/")[0])
print("\n=== 回环地址（应正常）===")
print("127.0.0.1:9001:", sh("curl -s -m 5 -o /dev/null -w '%{http_code}' http://127.0.0.1:9001/")[0])
print("127.0.0.1:9443:", sh("curl -sk -m 5 -o /dev/null -w '%{http_code}' https://127.0.0.1:9443/")[0])
c.close()

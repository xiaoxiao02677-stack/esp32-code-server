import paramiko
HOST, PORT, USER, PASSWORD = "sandyun.top", 22222, "root", "Ymm6088."
c = paramiko.SSHClient(); c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect(HOST, port=PORT, username=USER, password=PASSWORD, timeout=20, look_for_keys=False, allow_agent=False)
def sh(cmd, t=120):
    _, o, e = c.exec_command(cmd, timeout=t)
    return o.read().decode("utf-8","replace").strip(), e.read().decode("utf-8","replace").strip()
print("=== bash history 里的 > ===")
print(sh("grep -nE '>' ~/.bash_history 2>/dev/null | grep -iE 'log|nohup' | head -20")[0] or "(无)")
print("\n=== /opt/xiaozhi ===")
print(sh("ls -la /opt/xiaozhi/ | head -20")[0])
print(sh("grep -rnE '[^>]>[^>]' /opt/xiaozhi/*.sh 2>/dev/null | head -10")[0] or "(无 sh)")
print("\n=== nginx stream 配置 ===")
print(sh("nginx -T 2>/dev/null | sed -n '/stream {/,/^}/p' | head -60")[0])
print("\n=== nginx 主配置 include ===")
print(sh("grep -nE 'include|stream' /etc/nginx/nginx.conf")[0])
c.close()

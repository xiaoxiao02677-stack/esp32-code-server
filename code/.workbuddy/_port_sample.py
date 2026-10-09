import re, time, paramiko
HOST, PORT, USER, PASSWORD = "sandyun.top", 22222, "root", "Ymm6088."
c = paramiko.SSHClient(); c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect(HOST, port=PORT, username=USER, password=PASSWORD, timeout=20, look_for_keys=False, allow_agent=False)
sftp = c.open_sftp()
def sh(cmd, t=120):
    _, o, e = c.exec_command(cmd, timeout=t)
    return o.read().decode("utf-8","replace").strip(), e.read().decode("utf-8","replace").strip()

print("=== 当前 http 块 log_format / access_log ===")
print(sh("grep -n -E 'log_format|access_log' /etc/nginx/nginx.conf")[0])

with sftp.open("/etc/nginx/nginx.conf","r") as f: txt = f.read().decode()
# 新增带端口的日志格式
if "main_port" not in txt:
    txt = txt.replace(
        'access_log /var/log/nginx/access.log;',
        "log_format main_port '$remote_addr [$time_local] port=$server_port "
        '\"$request\" $status $body_bytes_sent "$http_user_agent"\';\n'
        "\taccess_log /var/log/nginx/access.log main_port;")
    with sftp.open("/etc/nginx/nginx.conf","w") as f: f.write(txt.encode())
o,e = sh("nginx -t 2>&1"); print("\nnginx -t:", o)
assert "successful" in o, "配置不合法，中止"
sh("systemctl reload nginx")
print("已切换为带端口的日志格式，采样 150 秒...")
time.sleep(150)

print("\n=== 各端口请求数（按 port= 分组） ===")
print(sh(r"grep -oE 'port=[0-9]+' /var/log/nginx/access.log | sort | uniq -c | sort -rn")[0])

print("\n=== 9001 / 9443 上的请求（若有，判断是不是扫描器） ===")
print(sh(r"grep -E 'port=(9001|9443)' /var/log/nginx/access.log | tail -15")[0] or "(采样期内 9001/9443 无任何请求)")

print("\n=== 8001 之外其他端口最近请求 ===")
print(sh(r"grep -vE 'port=(9001|9443)' /var/log/nginx/access.log | tail -8")[0] or "(无)")
sftp.close(); c.close()

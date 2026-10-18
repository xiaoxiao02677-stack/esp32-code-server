import paramiko, time
HOST, PORT, USER, PASSWORD = "sandyun.top", 22222, "root", "Ymm6088."
c = paramiko.SSHClient(); c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect(HOST, port=PORT, username=USER, password=PASSWORD, timeout=20, look_for_keys=False, allow_agent=False)
def sh(cmd, t=120):
    _, o, e = c.exec_command(cmd, timeout=t)
    return o.read().decode("utf-8","replace").strip(), e.read().decode("utf-8","replace").strip()
print("=== stream-8001.log 是否被 nginx 的 logrotate 覆盖 ===")
print(sh("grep -n 'log' /etc/logrotate.d/nginx | head")[0])
print("\n=== 等待真实设备重连（30s）后看 IP ===")
time.sleep(30)
print(sh(r"grep -E 'conn - Headers' /root/xiaozhi-server/main/yuhe-server/data/app.log | tail -4 | sed -E 's/(device-id[^}]*)/\1/' | cut -c1-200")[0])
print("\n=== 最近 3 分钟内 device-id 非探针的连接 IP 统计 ===")
print(sh(r"grep -E 'conn - Headers' /root/xiaozhi-server/main/yuhe-server/data/app.log | grep -v ip-probe | awk '{print $2}' | grep -oE '^[0-9.]+' | sort | uniq -c | sort -rn | head")[0])
print("\n=== nginx error.log 最近异常 ===")
print(sh("tail -5 /var/log/nginx/error.log")[0] or "(空)") 
print("\n=== stream 日志大小 ===")
print(sh("ls -la /var/log/nginx/stream-8001.log")[0])
c.close()

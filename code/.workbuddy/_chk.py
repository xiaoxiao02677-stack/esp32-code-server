import paramiko, time
HOST, PORT, USER, PASSWORD = "sandyun.top", 22222, "root", "Ymm6088."
c = paramiko.SSHClient(); c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect(HOST, port=PORT, username=USER, password=PASSWORD, timeout=20, look_for_keys=False, allow_agent=False)
def sh(cmd, t=120):
    _, o, e = c.exec_command(cmd, timeout=t)
    return o.read().decode("utf-8","replace").strip(), e.read().decode("utf-8","replace").strip()
L="/root/xiaozhi-server/main/xiaozhi-server/data/app.log"
print("第1次:", sh(f"stat -c '%s' {L}")[0])
time.sleep(15)
print("15s后:", sh(f"stat -c '%s' {L}")[0])
print("尾部2行:", sh(f"tail -2 {L}")[0] or "(空)")
print("\nmanager-api.log:")
print(sh("stat -c '%s' /opt/xiaozhi/manager-api.log; tail -1 /opt/xiaozhi/manager-api.log")[0] or "(空)")
print("\n留档文件:")
print(sh("ls -la /root/xiaozhi-server/main/xiaozhi-server/data/app.log-* /opt/xiaozhi/manager-api.log-*")[0])
print("\nlogrotate 状态:")
print(sh("grep -A2 -E 'app.log|manager-api.log' /var/lib/logrotate/status 2>/dev/null | head")[0])
c.close()

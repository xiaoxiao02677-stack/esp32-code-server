import paramiko
HOST, PORT, USER, PASSWORD = "sandyun.top", 22222, "root", "Ymm6088."
c = paramiko.SSHClient(); c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect(HOST, port=PORT, username=USER, password=PASSWORD, timeout=20, look_for_keys=False, allow_agent=False)
def sh(cmd, t=120):
    _, o, e = c.exec_command(cmd, timeout=t)
    return o.read().decode("utf-8","replace").strip(), e.read().decode("utf-8","replace").strip()
print("=== systemd unit ===")
print(sh("cat /etc/systemd/system/yuhe-server.service")[0])
print("\n=== 所有 > 重定向（启动脚本） ===")
print(sh("grep -rn '>' /root/xiaozhi-server/*.sh /root/xiaozhi-server/main/*.sh 2>/dev/null | grep -vE 'grep|echo|->|>>' | head -20")[0] or "(无)")
print("\n=== nohup/启动命令历史 ===")
print(sh("ls -la /root/xiaozhi-server/ | head -20")[0])
print("\n=== 日志文件 ===")
print(sh("ls -la /root/xiaozhi-server/main/yuhe-server/*.log /root/xiaozhi-server/main/yuhe-server/tmp/*.log 2>/dev/null | head -20")[0] or "(无)")
print(sh("find /root/xiaozhi-server -maxdepth 3 -name '*.log' -printf '%s %p\n' 2>/dev/null | sort -rn | head -15")[0])
c.close()

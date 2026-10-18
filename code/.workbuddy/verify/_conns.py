import paramiko
LOG="/root/xiaozhi-server/main/yuhe-server/data/app.log"
c = paramiko.SSHClient(); c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect("sandyun.top", port=22222, username="root", password="Ymm6088.", timeout=25, look_for_keys=False, allow_agent=False)
def sh(cmd, t=60):
    _, o, e = c.exec_command(cmd, timeout=t)
    return o.read().decode("utf-8","replace").strip()
print("=== 全部 WS 连接时刻（conn - Headers）===")
print(sh("grep -n 'conn - Headers' " + LOG + " | awk -F'[' '{print $1 substr($2,1,15)}' | cut -c1-30"))
print("\n=== 全部 已下发云端设备配置 时刻 + 内容截断 ===")
print(sh("grep -n '已下发云端设备配置' " + LOG + " | sed 's/\[0.9.7[^]]*\]//' | cut -c1-120 | tail -6"))
print("\n=== 全部 客户端断开连接 时刻 ===")
print(sh("grep -n '客户端断开连接' " + LOG + " | cut -c1-40 | tail -8"))
c.close()

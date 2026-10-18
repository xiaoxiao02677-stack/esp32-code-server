import paramiko
BASE="/root/xiaozhi-server/main/yuhe-server"; LOG=f"{BASE}/data/app.log"
c = paramiko.SSHClient(); c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect("sandyun.top", port=22222, username="root", password="Ymm6088.", timeout=25, look_for_keys=False, allow_agent=False)
def sh(cmd, t=60):
    _, o, e = c.exec_command(cmd, timeout=t)
    return o.read().decode("utf-8","replace").strip()
print("时间:", sh("date '+%F %T %Z'"))
print("PID:", sh("systemctl show yuhe-server -p MainPID --value"), "NRestarts:", sh("systemctl show yuhe-server -p NRestarts --value"))
print("最后一条心跳:", sh(f"grep '心跳' {LOG} | tail -1"))
print("已下发云端设备配置 总条数:", sh(f"grep -c '已下发云端设备配置' {LOG}"))
print("其中含 ASCII 拼音的条数:", sh(f"grep -cE '已下发云端设备配置: .*[a-z]{{2,}} [a-z]{{2,}}' {LOG}"))
print("最后一条:", sh(f"grep '已下发云端设备配置' {LOG} | tail -1"))
print("WS 会话(conn - Headers) 21:03 后新增:", sh(f"awk '/21:02:47/{{f=1}} f&&/conn - Headers/' {LOG} | wc -l"))
c.close()

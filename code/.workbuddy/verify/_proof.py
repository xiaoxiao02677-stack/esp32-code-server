import paramiko
BASE="/root/xiaozhi-server/main/yuhe-server"; LOG=f"{BASE}/data/app.log"
c = paramiko.SSHClient(); c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect("sandyun.top", port=22222, username="root", password="Ymm6088.", timeout=25, look_for_keys=False, allow_agent=False)
def sh(cmd, t=60):
    _, o, e = c.exec_command(cmd, timeout=t)
    return o.read().decode("utf-8","replace").strip()
print("=== 1) 21:26:05 那条前后 25 行 ===")
print(sh(f"grep -n '已下发云端设备配置' {LOG} | tail -3"))
N = sh(f"grep -n '已下发云端设备配置' {LOG} | tail -1 | cut -d: -f1")
print(f"--- 行号 {N} 附近 ---")
print(sh(f"sed -n '{int(N)-22},{int(N)+6}p' {LOG}"))
c.close()

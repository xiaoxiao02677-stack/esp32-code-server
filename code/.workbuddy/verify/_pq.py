import paramiko
LOG = "/root/xiaozhi-server/main/yuhe-server/data/app.log"
c = paramiko.SSHClient(); c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect("sandyun.top", port=22222, username="root", password="Ymm6088.", timeout=25, look_for_keys=False, allow_agent=False)
def sh(cmd, t=120):
    _, o, e = c.exec_command(cmd, timeout=t)
    return o.read().decode("utf-8","replace").strip(), e.read().decode("utf-8","replace").strip()
print("=== A) 离线入队日志（最近 10 条）===")
print(sh(f"grep -n '已缓存至' {LOG} | tail -10")[0] or "(无)")
print("\n=== B) 推送唤醒词成功日志（最近 10 条）===")
print(sh(f"grep -n '推送唤醒词' {LOG} | tail -10")[0] or "(无)")
print("\n=== C) 云端设备配置下发（最近 6 条）===")
print(sh(f"grep -n '已下发云端设备配置' {LOG} | tail -6")[0] or "(无)")
print("\n=== D) 44bd 痕迹（最近 12 条）===")
print(sh(f"grep -n '44bd8d7b3ae4' {LOG} | tail -12")[0] or "(无)")
print("\n=== E) 日志尾部 15 行 ===")
print(sh(f"tail -15 {LOG}")[0])
c.close()

import paramiko
LOG="/root/xiaozhi-server/main/yuhe-server/data/app.log"
c = paramiko.SSHClient(); c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect("sandyun.top", port=22222, username="root", password="Ymm6088.", timeout=25, look_for_keys=False, allow_agent=False)
def sh(cmd, t=60):
    _, o, e = c.exec_command(cmd, timeout=t)
    return o.read().decode("utf-8","replace").strip()
for n in (3045, 3094):
    print(f"--- line {n} ---")
    print(sh(f"sed -n '{n}p' {LOG} | sed 's/.*收到listen消息：//'"))
print("\n--- 这两条 detect 后 2 行内是否有 唤醒回复(3045~3048 / 3094~3097) ---")
print(sh(f"sed -n '3045,3048p' {LOG} | cut -c1-120"))
print(sh(f"sed -n '3094,3097p' {LOG} | cut -c1-120"))
c.close()

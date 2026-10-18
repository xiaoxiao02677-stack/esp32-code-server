import paramiko
BASE="/root/xiaozhi-server/main/yuhe-server"; LOG=f"{BASE}/data/app.log"
c = paramiko.SSHClient(); c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect("sandyun.top", port=22222, username="root", password="Ymm6088.", timeout=25, look_for_keys=False, allow_agent=False)
def sh(cmd, t=60):
    _, o, e = c.exec_command(cmd, timeout=t)
    return o.read().decode("utf-8","replace").strip()
print("=== WS 连接痕迹（21:20 之后）===")
print(sh(f"awk '/21:2[0-9]:/{{f=1}} f' {LOG} | grep -cE 'conn - Headers|配置输出音频采样率|websocket'"))
print(sh(f"grep -nE 'conn - Headers' {LOG} | tail -4") or "(无 conn - Headers)")
print("\n=== 21:20 之后所有 core.connection 行 ===")
print(sh(f"awk '/21:2[0-9]:/' {LOG} | grep 'core.connection' | head -25") or "(无)")
print("\n=== 设备注册/hello ===")
print(sh(f"grep -nE '注册|hello|Hello' {LOG} | tail -8") or "(无)")
c.close()

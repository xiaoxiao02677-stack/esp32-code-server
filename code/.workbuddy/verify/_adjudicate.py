import paramiko
BASE="/root/xiaozhi-server/main/yuhe-server"; LOG=f"{BASE}/data/app.log"
c = paramiko.SSHClient(); c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect("sandyun.top", port=22222, username="root", password="Ymm6088.", timeout=25, look_for_keys=False, allow_agent=False)
def sh(cmd, t=60):
    _, o, e = c.exec_command(cmd, timeout=t)
    return o.read().decode("utf-8","replace").strip()
print("=== A) 21:28:08 ~ 21:29:10 全部关键行（按行号）===")
print(sh(f"sed -n '3020,3130p' {LOG} | grep -nE 'conn - Headers|异步获取差异化配置成功|已下发云端设备配置|收到listen|播放唤醒词回复|识别文本|大模型收到用户消息|客户端断开' | sed 's/异步获取差异化配置成功.*device_config/异步获取差异化配置成功: {device_config/'"))
print("\n=== B) 所有 detect 行 + 其后 3 行内是否有唤醒回复 ===")
print(sh(f"grep -nE 'state\":\"detect\"' {LOG} | tail -6"))
print("\n=== C) 所有 播放唤醒词回复 行 ===")
print(sh(f"grep -n '播放唤醒词回复' {LOG} | tail -6"))
print("\n=== D) 21:28:22 前后逐行原文（含非匹配行）===")
print(sh(f"sed -n '3090,3112p' {LOG}"))
c.close()

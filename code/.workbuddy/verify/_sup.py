import paramiko
BASE="/root/xiaozhi-server/main/yuhe-server"; LOG=f"{BASE}/data/app.log"
c = paramiko.SSHClient(); c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect("sandyun.top", port=22222, username="root", password="Ymm6088.", timeout=25, look_for_keys=False, allow_agent=False)
def sh(cmd, t=60):
    _, o, e = c.exec_command(cmd, timeout=t)
    return o.read().decode("utf-8","replace").strip()
print("1) 'WakeWordService 初始化完成' 出现次数:", sh(f"grep -c 'WakeWordService 初始化完成' {LOG}"))
print("2) 'wallpaper' INFO 样本:", sh(f"grep -m2 'INFO:core.services.wallpaper_service' {LOG}") or "(无)")
print("3) 全仓 setLevel 位置:")
print(sh(f"grep -rn 'setLevel\|basicConfig' {BASE}/core {BASE}/config {BASE}/app.py 2>/dev/null | head -12") or "(无)")
print("4) push_scheduler 的 logger 获取方式:")
print(sh(f"grep -n 'getLogger\|setLevel' {BASE}/core/services/push_scheduler.py | head -6") or "(无)")
print("5) wake_word_service 的 logger 获取方式:")
print(sh(f"grep -n 'getLogger\|setLevel' {BASE}/core/services/wake_word_service.py | head -6") or "(无)")
c.close()

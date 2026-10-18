import paramiko
LOG = "/root/xiaozhi-server/main/yuhe-server/data/app.log"
c = paramiko.SSHClient(); c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect("sandyun.top", port=22222, username="root", password="Ymm6088.", timeout=25, look_for_keys=False, allow_agent=False)
def sh(cmd, t=120):
    _, o, e = c.exec_command(cmd, timeout=t)
    return o.read().decode("utf-8","replace").strip(), e.read().decode("utf-8","replace").strip()
print("=== 1) wake_word_service 该 logger 有任何输出吗 ===")
print(sh(f"grep -c 'wake_word_service' {LOG}")[0], "行")
print(sh(f"grep -n 'wake_word_service' {LOG} | tail -5")[0] or "(无)")
print("\n=== 2) 本项目 formatter 格式的行数 vs 默认 logging 格式的行数 ===")
print("本项目格式(261017 HH:MM:SS[):", sh(f"grep -cE '^[0-9]{{6}} [0-9]{{2}}:[0-9]{{2}}:[0-9]{{2}}\[' {LOG}")[0])
print("默认格式(LEVEL:name:):", sh(f"grep -cE '^(INFO|WARNING|ERROR|DEBUG):' {LOG}")[0])
print("\n=== 3) 默认格式里出现的 logger 名字清单 ===")
print(sh(f"grep -oE '^(INFO|WARNING|ERROR|DEBUG):[a-zA-Z0-9_.]+' {LOG} | sort | uniq -c | sort -rn | head -15")[0])
print("\n=== 4) 19:48 之后有无 已下发云端设备配置 ===")
print(sh(f"awk '/19:48:14/{{f=1}} f&&/已下发云端设备配置/' {LOG} | tail -5")[0] or "(19:48 之后没有再下发)")
c.close()

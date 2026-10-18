import paramiko
BASE="/root/xiaozhi-server/main/yuhe-server"; LOG=f"{BASE}/data/app.log"
c = paramiko.SSHClient(); c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect("sandyun.top", port=22222, username="root", password="Ymm6088.", timeout=25, look_for_keys=False, allow_agent=False)
def sh(cmd, t=60):
    _, o, e = c.exec_command(cmd, timeout=t)
    return o.read().decode("utf-8","replace").strip()
print("1) 谁打印 '尝试下发'：")
print(sh(f"grep -rn '尝试下发' {BASE}/core 2>/dev/null | grep -v '\.bak' | head -8") or "(无)")
print("\n2) 该文件的 logger 获取/级别：")
print(sh(f"grep -n 'getLogger\|setLevel\|intercept\|InterceptHandler' {BASE}/core/connection.py | head -8") or "(无)")
print("\n3) stdlib_log_bridge 注册了哪些模块：")
print(sh(f"grep -rn 'stdlib_log_bridge\|install_stdlib_bridge\|bridge' {BASE}/app.py {BASE}/core/utils/stdlib_log_bridge.py 2>/dev/null | grep -v '^.*#' | head -12") or "(无)")
print("\n4) 日志里 '尝试下发' 出现次数：", sh(f"grep -c '尝试下发' {LOG}"))
print("5) 日志里 '异步获取差异化配置成功' 出现次数：", sh(f"grep -c '异步获取差异化配置成功' {LOG}"))
c.close()

import paramiko
HOST, PORT, USER, PASSWORD = "sandyun.top", 22222, "root", "Ymm6088."
c = paramiko.SSHClient(); c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect(HOST, port=PORT, username=USER, password=PASSWORD, timeout=20, look_for_keys=False, allow_agent=False)
def sh(cmd, t=120):
    _, o, e = c.exec_command(cmd, timeout=t)
    return o.read().decode("utf-8","replace").strip(), e.read().decode("utf-8","replace").strip()
print("=== 配置里的 listen（权威） ===")
print(sh("nginx -T 2>/dev/null | grep -nE '^\s+listen' ")[0])
print("\n=== 监听地址（含新旧 worker）===")
print(sh("ss -lnt | grep -E ':9001|:9443|:9002|:9444|:8443|:8001' | awk '{print $4}' | sort | uniq -c")[0])
print("\n=== nginx worker 进程与启动时间 ===")
print(sh("ps -eo pid,lstart,cmd | grep 'nginx: worker' | grep -v grep | head -8")[0])
print("\n=== 新格式日志里扫描器走的是哪个端口 ===")
print(sh(r"grep -oE 'port=[0-9]+' /var/log/nginx/access.log | sort | uniq -c | sort -rn")[0])
print(sh(r"grep -E 'port=' /var/log/nginx/access.log | grep -iE 'censys|infrawat|modat|Go-http|python|curl' | tail -5")[0] or "(采样期内无扫描器)")
c.close()

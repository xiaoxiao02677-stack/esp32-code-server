import paramiko
BASE="/root/xiaozhi-server/main/yuhe-server"
c = paramiko.SSHClient(); c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect("sandyun.top", port=22222, username="root", password="Ymm6088.", timeout=25, look_for_keys=False, allow_agent=False)
def sh(cmd, t=120):
    _, o, e = c.exec_command(cmd, timeout=t)
    return o.read().decode("utf-8","replace").strip(), e.read().decode("utf-8","replace").strip()
print("=== 1) config.yaml 里的日志级别设置 ===")
print(sh(f"grep -nE 'log_level|level:|logger' {BASE}/config.yaml | head -20")[0] or "(无)")
print("\n=== 2) 项目内 setup_logging / getLogger 级别干预 ===")
print(sh(f"grep -rn 'setLevel' {BASE}/config/*.py {BASE}/app.py 2>/dev/null | head -15")[0] or "(无)")
print("\n=== 3) tmp/server.log 里有无 wake_word_service 的 INFO ===")
print(sh(f"grep -c 'wake_word_service' {BASE}/tmp/server.log 2>/dev/null")[0])
print(sh(f"grep -n '已缓存至' {BASE}/tmp/server.log 2>/dev/null | tail -5")[0] or "(无)")
print("\n=== 4) 全 data 目录搜索 已缓存至 / 推送唤醒词 ===")
print(sh(f"grep -rn '已缓存至' {BASE}/data/app.log {BASE}/tmp/server.log 2>/dev/null | tail -5")[0] or "(无)")
print("\n=== 5) 21:19~21:23 默认格式行原文（我的探针痕迹）===")
print(sh(f"grep -nE '^(INFO|WARNING|ERROR):' {BASE}/data/app.log | tail -8")[0])
c.close()

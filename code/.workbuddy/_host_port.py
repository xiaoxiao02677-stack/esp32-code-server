import paramiko
HOST, PORT, USER, PASSWORD = "sandyun.top", 22222, "root", "Ymm6088."
c = paramiko.SSHClient(); c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect(HOST, port=PORT, username=USER, password=PASSWORD, timeout=20, look_for_keys=False, allow_agent=False)
def sh(cmd, t=180):
    _, o, e = c.exec_command(cmd, timeout=t)
    return o.read().decode("utf-8","replace").strip(), e.read().decode("utf-8","replace").strip()
# access.log 是 combined 格式，最后一个字段是 referer，Host 不在里面。
# 但 request 里的绝对 URL 与 $http_referer 会带端口。用 referer + 全量文本匹配端口。
print("=== 历史日志（含已轮转）中出现 9001/9443/8443/8001 的次数 ===")
print(sh(r"zcat -f /var/log/nginx/access.log*.gz 2>/dev/null | cat - /var/log/nginx/access.log /var/log/nginx/access.log.1 2>/dev/null | grep -oE 'sandyun\.top:[0-9]{4}' | sort | uniq -c | sort -rn")[0] or "(无 host:port 记录)")
print("\n=== 最近出现 :9443 的样本 ===")
print(sh(r"zcat -f /var/log/nginx/access.log*.gz 2>/dev/null | cat - /var/log/nginx/access.log /var/log/nginx/access.log.1 2>/dev/null | grep -E 'sandyun\.top:9443' | tail -5")[0] or "(无)")
print("\n=== 最近出现 :9001 的样本 ===")
print(sh(r"zcat -f /var/log/nginx/access.log*.gz 2>/dev/null | cat - /var/log/nginx/access.log /var/log/nginx/access.log.1 2>/dev/null | grep -E 'sandyun\.top:9001' | tail -5")[0] or "(无)")
print("\n=== 最近出现 :8443 的样本 ===")
print(sh(r"zcat -f /var/log/nginx/access.log*.gz 2>/dev/null | cat - /var/log/nginx/access.log /var/log/nginx/access.log.1 2>/dev/null | grep -E 'sandyun\.top:8443' | tail -5")[0] or "(无)")
c.close()

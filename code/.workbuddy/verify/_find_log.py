import paramiko
c = paramiko.SSHClient(); c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect("sandyun.top", port=22222, username="root", password="Ymm6088.", timeout=25, look_for_keys=False, allow_agent=False)
def sh(cmd, t=120):
    _, o, e = c.exec_command(cmd, timeout=t)
    return o.read().decode("utf-8","replace").strip(), e.read().decode("utf-8","replace").strip()
o,_ = sh("ls -la /root/xiaozhi-server/main/yuhe-server/ 2>/dev/null | head -25; echo '--- data ---'; ls -la /root/xiaozhi-server/main/yuhe-server/data 2>/dev/null | head -15")
print(o)
print("=== working dir from proc ===")
print(sh("readlink /proc/674256/cwd")[0])
print("=== open log files ===")
print(sh("ls -l /proc/674256/fd 2>/dev/null | grep -E 'log|app' | head")[0])
c.close()

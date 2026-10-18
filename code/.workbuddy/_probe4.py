import paramiko
HOST, PORT, USER, PASSWORD = "sandyun.top", 22222, "root", "Ymm6088."
c = paramiko.SSHClient(); c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect(HOST, port=PORT, username=USER, password=PASSWORD, timeout=20, look_for_keys=False, allow_agent=False)
def sh(cmd, t=120):
    _, o, e = c.exec_command(cmd, timeout=t)
    return o.read().decode("utf-8","replace").strip(), e.read().decode("utf-8","replace").strip()
print("--- 进程启动时间 vs 文件时间 ---")
print(sh("stat -c '%y %n' /root/xiaozhi-server/main/yuhe-server/core/providers/tts/doubao_v3.py; systemctl show yuhe-server -p ExecMainStartTimestamp")[0])
print("--- 服务状态 ---")
print(sh("systemctl is-active yuhe-server")[0])
print("--- 最近日志(含TTS/emotion/doubao) ---")
print(sh("journalctl -u yuhe-server -n 200 --no-pager | grep -iE 'error|traceback|doubao|tts|emotion' | tail -20")[0] or "(无匹配错误)")
print("--- 8000/8003 监听 ---")
print(sh("ss -lntp | grep -E ':8000|:8003' | head")[0])
c.close()

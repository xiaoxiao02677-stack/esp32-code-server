# -*- coding: utf-8 -*-
# 推送 5 个服务端文件到生产 + 备份原文件 + py_compile 验证（不重启，等用户确认）
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
import paramiko, time

LOCAL_ROOT = r"G:\demo\21_xiaozhi\yh\yuhe-server"
REMOTE_ROOT = "/root/xiaozhi-server/main/yuhe-server"
FILES = [
    "core/handle/receiveAudioHandle.py",
    "core/connection.py",
    "core/services/wake_word_service.py",
    "core/handle/sendAudioHandle.py",
    "core/handle/textHandler/listenMessageHandler.py",
]
STAMP = time.strftime("%Y%m%dT%H%M%S")

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect("sandyun.top", port=22222, username="root", timeout=30)
try:
    sftp = ssh.open_sftp()
    for f in FILES:
        # 1) 远端备份
        _, out, _ = ssh.exec_command(f"cp -p {REMOTE_ROOT}/{f} {REMOTE_ROOT}/{f}.bak-{STAMP}", timeout=30)
        out.channel.recv_exit_status()
        # 2) 上传
        sftp.put(f"{LOCAL_ROOT}\\{f.replace('/', chr(92))}", f"{REMOTE_ROOT}/{f}")
        print(f"[uploaded] {f}")
    sftp.close()
    # 3) 远端 py_compile 验证（用服务端自己的 python）
    _, out, err = ssh.exec_command(
        f"cd {REMOTE_ROOT} && .venv/bin/python -m py_compile " + " ".join(FILES), timeout=60)
    rc = out.channel.recv_exit_status()
    print("远端 py_compile:", "OK" if rc == 0 else f"FAIL rc={rc}")
    e = err.read().decode('utf-8', errors='replace')
    if e.strip(): print("[stderr]", e[:500])
    # 4) md5 对账
    for f in FILES:
        cmd = f"md5sum {REMOTE_ROOT}/{f}"
        _, out, _ = ssh.exec_command(cmd, timeout=30)
        print(out.read().decode().split()[0][:12], f)
finally:
    ssh.close()
    print("\n[done] 未重启服务——待用户确认后重启")

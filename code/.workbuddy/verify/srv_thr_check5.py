# -*- coding: utf-8 -*-
# 拉取待改文件的完整相关段落：connection.py 1850-1880（clearSpeakStatus）、push_interrupt_threshold 全文、handleAudioMessage 精确行
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
import paramiko
ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect("sandyun.top", port=22222, username="root", timeout=30)
try:
    def run(cmd, label, t=60):
        print(f"\n===== {label} =====")
        _, out, err = ssh.exec_command(cmd, timeout=t)
        o = out.read().decode('utf-8', errors='replace')
        e = err.read().decode('utf-8', errors='replace')
        print(o[:6000] if o.strip() else "(无输出)")
        if e.strip(): print("[stderr]", e[:300])
    run("sed -n '1850,1880p' /root/xiaozhi-server/main/yuhe-server/core/connection.py", "clearSpeakStatus（1850-1880）")
    run("sed -n '345,356p' /root/xiaozhi-server/main/yuhe-server/core/handle/sendAudioHandle.py", "sendAudioHandle client_is_speaking=True 置位处（345-356）")
    run("grep -n 'handleAbortMessage\\|client_aec' /root/xiaozhi-server/main/yuhe-server/core/handle/receiveAudioHandle.py", "receiveAudioHandle 相关行号")
finally:
    ssh.close()
    print("\n[done]")

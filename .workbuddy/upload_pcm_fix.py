#!/usr/bin/env python3
"""Upload fixed asr_recognize_handler.py (pcm_bytes fix) and restart."""
import paramiko

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect("sandyun.top", port=22222, username="root", password="Ymm6088.",
               timeout=15, look_for_keys=False, allow_agent=False)
try:
    sftp = client.open_sftp()
    sftp.put(r"G:/demo/21_xiaozhi/code-server-mirror/xiaozhi-server/core/api/asr_recognize_handler.py",
             "/root/xiaozhi-server/main/xiaozhi-server/core/api/asr_recognize_handler.py")
    sftp.close()
    print("upload done")
    cmd = ("cd /root/xiaozhi-server/main/xiaozhi-server && "
           "python3 -c 'import ast; ast.parse(open(\"core/api/asr_recognize_handler.py\", encoding=\"utf-8\").read()); print(\"AST OK\")' && "
           "systemctl restart xiaozhi-server && sleep 6 && systemctl is-active xiaozhi-server")
    stdin, stdout, stderr = client.exec_command(cmd, timeout=60)
    print(stdout.read().decode("utf-8", "replace"))
    err = stderr.read().decode("utf-8", "replace")
    if err:
        print("[stderr]", err[:300])
finally:
    client.close()

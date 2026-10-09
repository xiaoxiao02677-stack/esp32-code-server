# -*- coding: utf-8 -*-
"""Stage 1: upload connection.py (with backup) + py_compile check."""
import sys
import time

import paramiko

HOST = "sandyun.top"
PORT = 22222
USER = "root"
PASSWORD = "Ymm6088."
LOCAL_FILE = "G:/demo/21_xiaozhi/code-server-mirror/xiaozhi-server/core/connection.py"
REMOTE_FILE = "/root/xiaozhi-server/main/xiaozhi-server/core/connection.py"

TS = time.strftime("%Y%m%d-%H%M%S")
BACKUP = REMOTE_FILE + ".bak-" + TS


def main():
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(HOST, port=PORT, username=USER, password=PASSWORD, timeout=20)

    # 0) pre-deploy state
    _, out, err = ssh.exec_command(
        "ps -ef | grep 'app.py' | grep -v grep; echo '---'; ss -lnt | grep -E ':(8000|8003|12399)' || true"
    )
    print("== PRE-STATE ==")
    print(out.read().decode("utf-8", "replace"))

    # 1) backup existing file
    _, out, err = ssh.exec_command(
        f"test -f {REMOTE_FILE} && cp -p {REMOTE_FILE} {BACKUP} && echo BACKUP_OK {BACKUP} || echo BACKUP_FAIL"
    )
    print(out.read().decode("utf-8", "replace").strip())

    # 2) upload
    sftp = ssh.open_sftp()
    sftp.put(LOCAL_FILE, REMOTE_FILE)
    attrs = sftp.stat(REMOTE_FILE)
    print(f"UPLOAD_OK size={attrs.st_size}")
    sftp.close()

    # 3) md5 compare
    _, out, _ = ssh.exec_command(f"md5sum {REMOTE_FILE} {REMOTE_FILE}.bak-{TS}" if False else f"md5sum {REMOTE_FILE}")
    print("REMOTE_MD5:", out.read().decode().strip())

    # 4) syntax check with venv python
    _, out, err = ssh.exec_command(
        "cd /root/xiaozhi-server/main/xiaozhi-server && .venv/bin/python -m py_compile core/connection.py && echo COMPILE_OK || echo COMPILE_FAIL"
    )
    o = out.read().decode("utf-8", "replace")
    e = err.read().decode("utf-8", "replace")
    print("COMPILE stdout:", o.strip())
    print("COMPILE stderr:", e.strip())

    ssh.close()


if __name__ == "__main__":
    main()

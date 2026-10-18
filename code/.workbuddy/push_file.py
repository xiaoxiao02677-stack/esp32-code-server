#!/usr/bin/env python3
"""Push a local file to remote via base64 over exec_command (sftp is disabled on this host)."""
import base64
import sys
sys.path.insert(0, r"G:\demo\21_xiaozhi\code\.workbuddy")
from ssh_run import get_client

local, remote = sys.argv[1], sys.argv[2]
mode = sys.argv[3] if len(sys.argv) > 3 else "644"
with open(local, "rb") as f:
    data = base64.b64encode(f.read()).decode()

client = get_client()
try:
    cmd = (
        f"printf '%s' '{data}' | base64 -d > {remote} "
        f"&& chmod {mode} {remote} && ls -l {remote}"
    )
    stdin, stdout, stderr = client.exec_command(cmd, timeout=120)
    out = stdout.read().decode("utf-8", "replace")
    err = stderr.read().decode("utf-8", "replace")
    rc = stdout.channel.recv_exit_status()
    print(out.strip())
    if err.strip():
        print("[stderr]", err.strip())
    print("[rc=%d]" % rc)
finally:
    client.close()

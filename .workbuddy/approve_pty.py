#!/usr/bin/env python3
"""Approve an AOCI managed-scope change via a real winpty PTY."""
import sys
import time

from winpty import PtyProcess

phrase = sys.argv[1]
cmd = sys.argv[2:]

proc = PtyProcess.spawn(cmd, dimensions=(24, 200))
# wait for the prompt to appear
buf = ""
deadline = time.time() + 20
while time.time() < deadline:
    if proc.isalive():
        time.sleep(0.3)
        try:
            buf += proc.read(4096)
        except Exception:
            break
        if "APPLY MANAGED SCOPE" in buf or "请精确输入" in buf:
            break
    else:
        break

if "APPLY MANAGED SCOPE" in buf or proc.isalive():
    proc.write(phrase + "\r")
    # drain output until exit
    deadline = time.time() + 90
    while proc.isalive() and time.time() < deadline:
        time.sleep(0.4)
        try:
            buf += proc.read(4096)
        except Exception:
            break

print(buf[-3000:])
sys.exit(proc.exitstatus if hasattr(proc, "exitstatus") else 0)

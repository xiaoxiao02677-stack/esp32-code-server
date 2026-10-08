#!/usr/bin/env python3
"""rsync cc-console dist → /var/www/cc-console（经 sftp 递归）"""
import os
import stat
import sys
sys.path.insert(0, r"G:\demo\21_xiaozhi\code\.workbuddy")
from ssh_run import get_client

SRC = r"G:\demo\21_xiaozhi\cc-console\dist"
DST = "/var/www/cc-console"

client = get_client()
sftp = client.open_sftp()

def ensure_dir(path):
    try:
        sftp.stat(path)
    except FileNotFoundError:
        sftp.mkdir(path)

count = 0
for root, dirs, files in os.walk(SRC):
    rel = os.path.relpath(root, SRC).replace("\\", "/")
    rdir = DST if rel == "." else f"{DST}/{rel}"
    ensure_dir(rdir)
    for f in files:
        sftp.put(os.path.join(root, f), f"{rdir}/{f}")
        count += 1
print(f"UPLOADED {count} files -> {DST}")
sftp.close()
client.close()

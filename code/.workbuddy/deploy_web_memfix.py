#!/usr/bin/env python3
"""Upload manager-web dist -> /var/www/xiaozhi-manager (index.html last)."""
import os
import sys

sys.path.insert(0, r"G:\demo\21_xiaozhi\code\.workbuddy")
from ssh_run import get_client  # noqa: E402

SRC = r"G:\demo\21_xiaozhi\code-server-mirror\manager-web\dist"
DST = "/var/www/xiaozhi-manager"

client = get_client()
sftp = client.open_sftp()


def ensure_dir(path):
    try:
        sftp.stat(path)
    except FileNotFoundError:
        sftp.mkdir(path)


count = 0
index_local = None
for root, dirs, files in os.walk(SRC):
    rel = os.path.relpath(root, SRC).replace("\\", "/")
    rdir = DST if rel == "." else f"{DST}/{rel}"
    ensure_dir(rdir)
    for f in files:
        if rel == "." and f == "index.html":
            index_local = os.path.join(root, f)
            continue
        sftp.put(os.path.join(root, f), f"{rdir}/{f}")
        count += 1
print(f"pass1 uploaded {count} files")

if index_local:
    sftp.put(index_local, f"{DST}/index.html")
    print("index.html uploaded")

sftp.close()
client.close()
print("WEB_DEPLOY_DONE")

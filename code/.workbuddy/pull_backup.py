#!/usr/bin/env python3
"""Download the deploy backup snapshot from sandyun.top for off-host copy.

Usage: python pull_backup.py
"""
import hashlib
import os
import posixpath
import sys

sys.path.insert(0, r"G:\demo\21_xiaozhi\code\.workbuddy")
from ssh_run import get_client

REMOTE_ROOT = "/root/deploy-backup/20261017T125532Z"
LOCAL_ROOT = r"G:/demo/21_xiaozhi/code/.workbuddy/deploy-backup-local/20261017T125532Z"

FILES = [
    "jar/xiaozhi-esp32-api.jar",    "py/core/services/wake_word_service.py",
    "py/core/http_server.py",
    "py/core/api/wake_word_handler.py",
    "db/ai_tables_full.sql",
    "db/ai_tables_4tables.sql",
    "db/ai_tables.sql",
    "web-admin.tar.gz",
    "MANIFEST.txt",
    "ROLLBACK.sh",
]

# 可选：只拉指定相对路径，例如: python pull_backup.py ROLLBACK.sh MANIFEST.txt
if len(sys.argv) > 1:
    FILES = sys.argv[1:]


def md5_local(path):
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def main():
    client = get_client()
    try:
        client.get_transport().set_keepalive(30)
        sftp = client.open_sftp()

        # remote md5 in one shot
        cmd = "md5sum " + " ".join(posixpath.join(REMOTE_ROOT, f) for f in FILES)
        stdin, stdout, stderr = client.exec_command(cmd, timeout=300)
        remote_md5 = {}
        for line in stdout.read().decode().splitlines():
            parts = line.split()
            if len(parts) >= 2:
                remote_md5[parts[1]] = parts[0]
        err = stderr.read().decode().strip()
        if err:
            print("[remote stderr]", err)

        results = []
        for rel in FILES:
            remote = posixpath.join(REMOTE_ROOT, rel)
            local = os.path.join(LOCAL_ROOT, rel.replace("/", os.sep))
            os.makedirs(os.path.dirname(local), exist_ok=True)
            size = sftp.stat(remote).st_size
            sftp.get(remote, local)
            lmd5 = md5_local(local)
            rmd5 = remote_md5.get(remote, "MISSING")
            ok = (lmd5 == rmd5)
            results.append((rel, size, lmd5, rmd5, ok))
            print(f"{'OK  ' if ok else 'FAIL'} {rel}  {size} B  local={lmd5}  remote={rmd5}", flush=True)

        sftp.close()

        total = sum(r[1] for r in results)
        bad = [r for r in results if not r[4]]
        print("")
        print(f"files={len(results)} total_bytes={total} ({total/1024/1024:.1f} MB) failed={len(bad)}")
        for r in bad:
            print("MISMATCH:", r[0])
        print("RESULT=" + ("PASS" if not bad else "FAIL"))
    finally:
        client.close()


if __name__ == "__main__":
    main()

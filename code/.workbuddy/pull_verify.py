#!/usr/bin/env python3
"""Pull the post-save EVIDENCE snapshot (not a rollback asset) to local disk.

Remote : /root/deploy-verify/20261017T2135Z/
Local  : G:/demo/21_xiaozhi/code/.workbuddy/verify/snapshots/20261017T2135Z/

Every file is md5-checked locally against a same-run remote md5sum.
"""
import hashlib
import os
import posixpath
import sys

sys.path.insert(0, r"G:\demo\21_xiaozhi\code\.workbuddy")
from ssh_run import get_client

REMOTE_ROOT = "/root/deploy-verify/20261017T2135Z"
LOCAL_ROOT = r"G:/demo/21_xiaozhi/code/.workbuddy/verify/snapshots/20261017T2135Z"

FILES = [
    "postsave_device_config.sql",
    "postsave_md5.txt",
]


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

        cmd = "md5sum " + " ".join(posixpath.join(REMOTE_ROOT, f) for f in FILES)
        _, stdout, stderr = client.exec_command(cmd, timeout=120)
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
            ok = lmd5 == rmd5
            results.append((rel, size, lmd5, rmd5, ok))
            print(f"{'OK  ' if ok else 'FAIL'} {rel}  {size} B  local={lmd5}  remote={rmd5}", flush=True)

        sftp.close()

        total = sum(r[1] for r in results)
        bad = [r for r in results if not r[4]]
        print("")
        print(f"files={len(results)} total_bytes={total} failed={len(bad)}")
        for r in bad:
            print("MISMATCH:", r[0])
        print("RESULT=" + ("PASS" if not bad else "FAIL"))
    finally:
        client.close()


if __name__ == "__main__":
    main()

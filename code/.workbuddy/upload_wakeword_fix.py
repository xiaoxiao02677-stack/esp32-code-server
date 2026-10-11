#!/usr/bin/env python3
"""Upload modified manager-api files to server with .bak-devsync backup."""
import paramiko

HOST, PORT, USER, PASSWORD = "sandyun.top", 22222, "root", "Ymm6088."

LOCAL_BASE = "G:/demo/21_xiaozhi/code-server-mirror"
REMOTE_BASE = "/root/xiaozhi-server/main"

FILES = [
    "manager-api/src/main/java/xiaozhi/modules/agent/controller/WakeWordController.java",
    "manager-api/src/main/java/xiaozhi/modules/device/service/DeviceService.java",
    "manager-api/src/main/java/xiaozhi/modules/device/service/impl/DeviceServiceImpl.java",
]


def main():
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(HOST, port=PORT, username=USER, password=PASSWORD,
                   timeout=15, banner_timeout=15, auth_timeout=15,
                   look_for_keys=False, allow_agent=False)
    try:
        sftp = client.open_sftp()
        for rel in FILES:
            local = f"{LOCAL_BASE}/{rel}"
            remote = f"{REMOTE_BASE}/{rel}"
            backup = remote + ".bak-devsync"
            try:
                sftp.stat(backup)
                print(f"backup exists, keep old: {backup}")
            except FileNotFoundError:
                sftp.rename(remote, backup)
                print(f"backed up: {remote} -> {backup}")
            with open(local, "rb") as f, sftp.open(remote, "wb") as rf:
                rf.set_pipelined(True)
                while True:
                    chunk = f.read(65536)
                    if not chunk:
                        break
                    rf.write(chunk)
            print(f"uploaded: {remote}")
        sftp.close()
        # verify checksums
        for rel in FILES:
            remote = f"{REMOTE_BASE}/{rel}"
            _, stdout, _ = client.exec_command(f"md5sum '{remote}'")
            rmd5 = stdout.read().decode().split()[0]
            import hashlib
            with open(f"{LOCAL_BASE}/{rel}", "rb") as f:
                lmd5 = hashlib.md5(f.read()).hexdigest()
            status = "OK" if rmd5 == lmd5 else "MISMATCH"
            print(f"{status}: {rel} local={lmd5} remote={rmd5}")
    finally:
        client.close()


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""SSH helper for remote server operations (sandyun.top:22222)."""
import sys
import stat
import warnings

import paramiko

warnings.filterwarnings("ignore")

HOST = "sandyun.top"
PORT = 22222
USER = "root"
PASSWORD = "Ymm6088."


def connect() -> paramiko.SSHClient:
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(HOST, port=PORT, username=USER, password=PASSWORD, timeout=20)
    return client


def run(cmd: str, timeout: int = 1800) -> int:
    client = connect()
    try:
        stdin, stdout, stderr = client.exec_command(cmd, timeout=timeout)
        out = stdout.read().decode("utf-8", "replace")
        err = stderr.read().decode("utf-8", "replace")
        code = stdout.channel.recv_exit_status()
        if out:
            print(out, end="" if out.endswith("\n") else "\n")
        if err:
            print("[STDERR]", err, file=sys.stderr, end="" if err.endswith("\n") else "\n")
        return code
    finally:
        client.close()


def upload(local_path: str, remote_path: str) -> int:
    local_path = local_path.replace("\\", "/")
    client = connect()
    try:
        sftp = client.open_sftp()
        try:
            sftp.put(local_path, remote_path)
            print(f"OK {local_path} -> {remote_path}")
            return 0
        finally:
            sftp.close()
    finally:
        client.close()


def upload_dir(local_dir: str, remote_dir: str, excludes=None) -> int:
    import os

    excludes = excludes or set()
    local_dir = local_dir.replace("\\", "/").rstrip("/")
    remote_dir = remote_dir.rstrip("/")
    client = connect()
    try:
        sftp = client.open_sftp()
        try:
            count = 0
            for root, dirs, files in os.walk(local_dir):
                rel = os.path.relpath(root, local_dir).replace("\\", "/")
                rel_parts = set(rel.split("/")) if rel != "." else set()
                if rel_parts & excludes:
                    dirs[:] = []
                    continue
                rpath = remote_dir if rel == "." else f"{remote_dir}/{rel}"
                try:
                    sftp.stat(rpath)
                except FileNotFoundError:
                    sftp.mkdir(rpath)
                for name in files:
                    if name in excludes:
                        continue
                    lfile = os.path.join(root, name)
                    try:
                        sftp.put(lfile, f"{rpath}/{name}")
                        count += 1
                    except PermissionError:
                        print(f"SKIP (no read perm) {lfile}")
            print(f"UPLOADED {count} files -> {remote_dir}")
            return 0
        finally:
            sftp.close()
    finally:
        client.close()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: run <cmd> [timeout_sec] | put <local> <remote> | putdir <local_dir> <remote_dir> [excludes]")
        sys.exit(1)
    action = sys.argv[1]
    if action == "run":
        timeout = int(sys.argv[3]) if len(sys.argv) > 3 else 1800
        sys.exit(run(sys.argv[2], timeout=timeout))
    elif action == "put":
        sys.exit(upload(sys.argv[2], sys.argv[3]))
    elif action == "putdir":
        excl = set(sys.argv[4].split(",")) if len(sys.argv) > 4 else set()
        sys.exit(upload_dir(sys.argv[2], sys.argv[3], excl))
    else:
        print(f"Unknown action: {action}")
        sys.exit(1)

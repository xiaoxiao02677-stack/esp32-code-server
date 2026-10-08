#!/usr/bin/env python3
"""SFTP push helper for sandyun.top deployment (symmetric to sftp_pull.py).

Usage: python sftp_push.py <local_file> <remote_file>
"""
import sys
import paramiko

HOST, PORT, USER, PASSWORD = "sandyun.top", 22222, "root", "Ymm6088."

def main():
    if len(sys.argv) != 3:
        print("usage: sftp_push.py LOCAL REMOTE", file=sys.stderr)
        sys.exit(2)
    local, remote = sys.argv[1], sys.argv[2]
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(HOST, port=PORT, username=USER, password=PASSWORD,
                   timeout=15, look_for_keys=False, allow_agent=False)
    sftp = client.open_sftp()
    print(f"pushing {local} -> {remote}")
    sftp.put(local, remote)
    sftp.close()
    client.close()
    print("done")

if __name__ == "__main__":
    main()

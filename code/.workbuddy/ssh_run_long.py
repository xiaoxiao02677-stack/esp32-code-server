#!/usr/bin/env python3
"""SSH helper with long timeout for deployment commands (mvn/rsync/mysqldump).

Usage: python ssh_run_long.py "command1" ["command2" ...]
Identical to ssh_run.py but channel timeout is 900s instead of 60s.
"""
import sys
import paramiko

HOST = "sandyun.top"
PORT = 22222
USER = "root"

def get_client():
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(HOST, port=PORT, username=USER, password="Ymm6088.",
                   timeout=15, banner_timeout=15, auth_timeout=15,
                   look_for_keys=False, allow_agent=False)
    return client

def main():
    if len(sys.argv) < 2:
        print("usage: ssh_run_long.py CMD [CMD...]", file=sys.stderr)
        sys.exit(2)
    client = get_client()
    try:
        for cmd in sys.argv[1:]:
            print(f"\n$ {cmd}")
            stdin, stdout, stderr = client.exec_command(cmd, timeout=900)
            out = stdout.read().decode("utf-8", "replace")
            err = stderr.read().decode("utf-8", "replace")
            rc = stdout.channel.recv_exit_status()
            if out:
                print(out.rstrip())
            if err:
                print("[stderr]", err.rstrip())
            print(f"[rc={rc}]")
    finally:
        client.close()

if __name__ == "__main__":
    main()

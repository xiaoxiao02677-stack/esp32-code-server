#!/usr/bin/env python3
# Remote SSH helper: run a command (or read a here-doc script) on the target host.
# Usage:
#   python rsh.py "remote command"
#   python rsh.py -f local_script.sh          # uploads & runs the script with bash -s
# Env: HOST, PORT, USER, PASS override defaults.
import sys, os, paramiko

HOST = os.environ.get("RHOST", "sandyun.top")
PORT = int(os.environ.get("RPORT", "22223"))
USER = os.environ.get("RUSER", "root")
PASS = os.environ.get("RPASS", "Ymm6088.")

def make_client():
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect(HOST, port=PORT, username=USER, password=PASS,
              timeout=20, banner_timeout=20, auth_timeout=20,
              look_for_keys=False, allow_agent=False)
    return c

def run(cmd, timeout=120):
    c = make_client()
    stdin, stdout, stderr = c.exec_command(cmd, timeout=timeout, get_pty=False)
    out = stdout.read().decode("utf-8", "replace")
    err = stderr.read().decode("utf-8", "replace")
    rc = stdout.channel.recv_exit_status()
    c.close()
    return out, err, rc

def main():
    args = sys.argv[1:]
    if not args:
        print("no command", file=sys.stderr); sys.exit(2)
    if args[0] == "-f":
        with open(args[1], "rb") as f:
            script = f.read().decode("utf-8")
        cmd = "bash -s"
        c = make_client()
        stdin, stdout, stderr = c.exec_command(cmd, timeout=300)
        stdin.write(script); stdin.channel.shutdown_write()
        out = stdout.read().decode("utf-8", "replace")
        err = stderr.read().decode("utf-8", "replace")
        rc = stdout.channel.recv_exit_status()
        c.close()
        sys.stdout.write(out)
        if err.strip():
            sys.stdout.write("\n--- STDERR ---\n" + err)
        sys.exit(rc)
    else:
        out, err, rc = run(" ".join(args))
        sys.stdout.write(out)
        if err.strip():
            sys.stdout.write("\n--- STDERR ---\n" + err)
        sys.exit(rc)

if __name__ == "__main__":
    main()

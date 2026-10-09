# -*- coding: utf-8 -*-
"""Stage 2: restart app.py (kill-all, start one), verify process/ports/log.

paramiko note: for the background start command, do NOT read stdout
(would hang until timeout). Sleep 2 then close the channel directly.
"""
import time

import paramiko

HOST = "sandyun.top"
PORT = 22222
USER = "root"
PASSWORD = "Ymm6088."

APP_DIR = "/root/xiaozhi-server/main/xiaozhi-server"

# bracket trick in patterns prevents the pkill shell from matching itself
KILL_CMD = (
    "pkill -f 'xiaozhi-server/main/xiaozhi[-]server'; "
    "pkill -f 'venv/bin/python app[.]py'; "
    "sleep 3; echo KILL_DONE"
)

START_CMD = (
    f"cd {APP_DIR} && setsid nohup .venv/bin/python app.py "
    "> /tmp/xiaozhi-server.log 2>&1 < /dev/null &"
)

VERIFY_CMD = r"""
echo '== RAW PS =='
ps -ef | grep '[a]pp.py' | grep -v grep
echo '== PY PROCS =='
PIDS=""
for p in $(pgrep -f 'app[.]py'); do
  c=$(ps -o comm= -p "$p" 2>/dev/null)
  if [ "$c" = "python" ]; then
    PIDS="$PIDS $p"
    ps -o pid,ppid,etime,args= -p "$p" | tail -1
  fi
done
echo "PY_PIDS:$PIDS"
echo '== PORTS =='
ss -lnt | grep -E ':(8000|8003|12399)' || echo NO_PORTS
echo '== LOG tail =='
tail -5 /tmp/xiaozhi-server.log
"""


def count_python_app(ssh):
    """Return list of pids that are real python processes running app.py."""
    _, out, _ = ssh.exec_command(
        "for p in $(pgrep -f 'app[.]py'); do "
        "c=$(ps -o comm= -p $p 2>/dev/null); "
        "[ \"$c\" = \"python\" ] && echo $p; done"
    )
    pids = [line.strip() for line in out.read().decode().split() if line.strip()]
    return pids


def main():
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(HOST, port=PORT, username=USER, password=PASSWORD, timeout=20)

    # 1) kill everything
    _, out, err = ssh.exec_command(KILL_CMD)
    print("KILL:", out.read().decode().strip(), err.read().decode().strip())

    remaining = count_python_app(ssh)
    print("AFTER_KILL_PY_PIDS:", remaining)

    # 2) start (background command: DO NOT read stdout)
    print("START:", START_CMD)
    _, stdout, _ = ssh.exec_command(START_CMD)
    time.sleep(2)
    stdout.channel.close()

    # 3) wait 12s for boot
    time.sleep(12)

    pids = count_python_app(ssh)
    print("PY_PIDS_AFTER_START:", pids)

    # 4) if more than one, kill -9 extras (keep oldest = lowest pid)
    if len(pids) > 1:
        keep = pids[0]
        extras = pids[1:]
        print(f"MULTIPLE detected, keeping {keep}, killing {extras}")
        _, out, _ = ssh.exec_command("kill -9 " + " ".join(extras) + "; sleep 2; echo KILLED_EXTRAS")
        print(out.read().decode().strip())
        time.sleep(2)
        pids = count_python_app(ssh)
        print("PY_PIDS_AFTER_CLEANUP:", pids)

    # 5) full verification dump
    _, out, err = ssh.exec_command(VERIFY_CMD)
    print(out.read().decode("utf-8", "replace"))
    e = err.read().decode("utf-8", "replace").strip()
    if e:
        print("VERIFY stderr:", e)

    ssh.close()


if __name__ == "__main__":
    main()

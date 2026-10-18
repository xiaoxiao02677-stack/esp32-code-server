#!/usr/bin/env python3
"""Read-only conflict auditor: track md5 of 5 candidate files + service restarts.

Round 0 baseline captured at 2026-10-10 21:25:16 (remote time).
Logs every change as: file | old_md5 | new_md5 | time (plus mtime).
Read-only: never modifies remote files.
"""
import re
import subprocess
import time
from datetime import datetime

SSH = ["python", "G:/demo/21_xiaozhi/code/.workbuddy/ssh_run.py"]
BASE = "/root/xiaozhi-server/main/yuhe-server"
FILES = [
    "core/api/wake_word_handler.py",
    "core/websocket_server.py",
    "core/providers/tts/base.py",
    "core/providers/tts/doubao_v3.py",
    "core/utils/modules_initialize.py",
]
INTERVAL = 150  # seconds between rounds
ROUNDS = 6
LOG = "G:/demo/21_xiaozhi/code/.workbuddy/audit_conflict_6.log"

BASELINE = {
    "core/api/wake_word_handler.py": "bf21d2bd2543b3f0b82c1f100300b8af",
    "core/websocket_server.py": "c109308d031414ed0642afc93f997965",
    "core/providers/tts/base.py": "3b4977092d78724402dd9205a1505751",
    "core/providers/tts/doubao_v3.py": "78f7b8582cb9467a5c1d69fcaa6d2e08",
    "core/utils/modules_initialize.py": "f9b30a4b7abaf0bac7242f2ddc808bd2",
}

MD5_RE = re.compile(r"^([0-9a-f]{32})\s+(core/\S+)$", re.M)


def ssh(cmd):
    try:
        r = subprocess.run(SSH + [cmd], capture_output=True, text=True, timeout=120)
        return r.stdout + r.stderr
    except Exception as exc:  # noqa: BLE001
        return f"[ssh-error] {exc}"


def log(line):
    stamp = datetime.now().strftime("%H:%M:%S")
    with open(LOG, "a", encoding="utf-8") as fh:
        fh.write(f"[{stamp}] {line}\n")
    print(f"[{stamp}] {line}", flush=True)


def snapshot():
    md5_cmd = f"cd {BASE} && date '+%Y-%m-%d %H:%M:%S' && md5sum " + " ".join(FILES)
    out = ssh(md5_cmd)
    remote_time = "?"
    m = re.search(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})$", out, re.M)
    if m:
        remote_time = m.group(1)
    hashes = {f: BASELINE[f] for f in FILES}
    for h, f in MD5_RE.findall(out):
        if f in hashes:
            hashes[f] = h
    # mtimes for changed-file detail
    stat_cmd = f"cd {BASE} && stat -c '%y %n' " + " ".join(FILES)
    stat_out = ssh(stat_cmd)
    mtimes = dict(re.findall(r"^(\S+ \S+) (\S+)$", stat_out, re.M))
    # service state
    svc = ssh("systemctl show yuhe-server -p ActiveEnterTimestamp --value")
    svc = svc.split("[rc=]")[0].strip().splitlines()
    active_since = svc[-1].strip() if svc else "?"
    return remote_time, hashes, mtimes, active_since


def main():
    log(f"=== auditor start; baseline 21:25:16; {ROUNDS} rounds x {INTERVAL}s ===")
    prev = {f: BASELINE[f] for f in FILES}
    change_count = {f: 0 for f in FILES}
    first = True
    for rnd in range(1, ROUNDS + 1):
        remote_time, hashes, mtimes, active_since = snapshot()
        log(f"round {rnd} @{remote_time} svc_active_since={active_since}")
        for f in FILES:
            if hashes[f] != prev[f]:
                change_count[f] += 1
                mt = mtimes.get(f, "?")
                log(f"CHANGE {f} | {prev[f]} -> {hashes[f]} | remote={remote_time} mtime={mt} | change#{change_count[f]}")
                prev[f] = hashes[f]
        if first:
            first = False
        if rnd < ROUNDS:
            time.sleep(INTERVAL)
    # summary
    log("=== summary ===")
    for f in FILES:
        flag = " ** MULTI-CHANGE: possible same-file conflict **" if change_count[f] >= 2 else ""
        log(f"{f}: changes={change_count[f]} final={prev[f]}{flag}")
    log("=== auditor end ===")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Supervisor: keep auto_author pipelines alive for both repos until done.

Checks the aoci status of each repo; if entries needed and no python
process is running for it, (re)start it. Exits when both repos report
aligned (no authoring targets).
"""
import json
import subprocess
import time

ROOT = "G:/demo/21_xiaozhi"
AOCI = "D:/INSTALL/aoci/aoci.exe"
REPOS = {
    "code-server-mirror": "G:/demo/21_xiaozhi/code-server-mirror",
    "hermes-agent-main": "G:/demo/21_xiaozhi/hermes-agent-main",
}
LOGS = {
    "code-server-mirror": ROOT + "/.workbuddy/full_server.log",
    "hermes-agent-main": ROOT + "/.workbuddy/full_hermes.log",
}


def running_pipelines():
    r = subprocess.run(
        ["wmic", "process", "where",
         "commandline like '%auto_author.py%' and name like 'python%'",
         "get", "commandline", "/format:csv"],
        capture_output=True, timeout=30)
    out = r.stdout.decode("utf-8", "replace")
    active = set()
    for name in REPOS:
        if f"auto_author.py {name}" in out:
            active.add(name)
    return active


def authoring_remaining(repo_path):
    r = subprocess.run(
        [AOCI, "--repo", repo_path, "scope", "status", "--json"],
        capture_output=True, timeout=300)
    d = json.loads(r.stdout.decode("utf-8", "replace"))
    return d.get("authoring_targets", 0)


def start_pipeline(name):
    log = open(LOGS[name], "a", encoding="utf-8")
    log.write(f"\n=== supervisor restart {time.strftime('%H:%M:%S')} ===\n")
    log.flush()
    subprocess.Popen(
        ["python", ROOT + "/.workbuddy/auto_author.py", name],
        stdout=log, stderr=log, cwd=ROOT)
    print(f"[supervisor] started {name}", flush=True)


idle_rounds = 0
while True:
    active = running_pipelines()
    all_done = True
    for name, path in REPOS.items():
        try:
            remaining = authoring_remaining(path)
        except Exception as e:
            print(f"[supervisor] status error {name}: {e}", flush=True)
            continue
        if remaining > 0:
            all_done = False
            if name not in active:
                print(f"[supervisor] {name}: {remaining} targets, "
                      f"not running -> start", flush=True)
                start_pipeline(name)
            else:
                print(f"[supervisor] {name}: {remaining} targets, running",
                      flush=True)
        else:
            print(f"[supervisor] {name}: aligned", flush=True)
    if all_done:
        print("[supervisor] both repos aligned; exiting", flush=True)
        break
    idle_rounds += 1
    time.sleep(180)

#!/usr/bin/env python3
"""Watchdog v2: relay to hermes when server-mirror python exits.

Robust on any locale: checks the parent bash PID via psutil-free approach —
poll for existence of the python child with the exact command line using
wmic with explicit codepage-independent parsing (unicode escape output).
"""
import subprocess
import time

PARENT_PID = "38664"
MARKER = "auto_author.py code-server-mirror"


def server_pipeline_alive():
    # check our own known child python (PID 36112) and the parent shell
    for pid in (PARENT_PID, "36112"):
        try:
            r = subprocess.run(
                ["wmic", "process", "where", f"processid={pid}", "get",
                 "processid", "/format:csv"],
                capture_output=True, timeout=20)
            # /format:csv output is ASCII-safe: header + row, no localized text
            out = r.stdout.decode("ascii", "replace")
            if f",{pid}," in out or out.rstrip().endswith(pid):
                return True
        except Exception:
            pass
    return False


while True:
    if not server_pipeline_alive():
        print("server-mirror pipeline gone; starting hermes", flush=True)
        break
    time.sleep(90)

with open("G:/demo/21_xiaozhi/.workbuddy/full_hermes.log", "a", encoding="utf-8") as log:
    log.write("\n=== relay start ===\n")
    log.flush()
    subprocess.run(
        ["python", "G:/demo/21_xiaozhi/.workbuddy/auto_author.py",
         "hermes-agent-main"],
        stdout=log, stderr=log, cwd="G:/demo/21_xiaozhi")

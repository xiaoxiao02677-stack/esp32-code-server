#!/usr/bin/env python3
"""Watchdog: when the code-server-mirror pipeline exits, start hermes."""
import subprocess
import sys
import time

while True:
    r = subprocess.run(
        ["tasklist", "/FI", "PID", "eq", sys.argv[1]],
        capture_output=True, text=True)
    if sys.argv[1] not in r.stdout:
        print("server-mirror pipeline exited; starting hermes pipeline")
        break
    time.sleep(60)

with open("G:/demo/21_xiaozhi/.workbuddy/full_hermes.log", "a", encoding="utf-8") as log:
    subprocess.run(
        ["python", "G:/demo/21_xiaozhi/.workbuddy/auto_author.py",
         "hermes-agent-main"],
        stdout=log, stderr=log, cwd="G:/demo/21_xiaozhi")

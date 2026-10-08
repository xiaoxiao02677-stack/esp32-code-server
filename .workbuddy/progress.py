#!/usr/bin/env python3
"""Progress snapshot for both repos."""
import json
import re
import subprocess

AOCI = "D:/INSTALL/aoci/aoci.exe"
REPOS = {
    "code-server-mirror": "G:/demo/21_xiaozhi/code-server-mirror",
    "hermes-agent-main": "G:/demo/21_xiaozhi/hermes-agent-main",
}
for name, path in REPOS.items():
    r = subprocess.run([AOCI, "--repo", path, "status"],
                       capture_output=True, timeout=120)
    out = r.stdout.decode("utf-8", "replace")
    m = re.search(r"索引条目 (\d+)", out)
    entries = m.group(1) if m else "?"
    log = (f"G:/demo/21_xiaozhi/.workbuddy/full_server.log"
           if "server" in name else
           f"G:/demo/21_xiaozhi/.workbuddy/full_hermes.log")
    try:
        with open(log, encoding="utf-8", errors="replace") as f:
            logtxt = f.read()
        applied = logtxt.count("submit -> applied")
    except OSError:
        applied = 0
    print(f"{name}: entries={entries} applied_batches={applied}")
import os
for k, d in (("server", "code-server-mirror"),
             ("hermes", "hermes-agent-main")):
    cdir = f"G:/demo/21_xiaozhi/.workbuddy/aoci/cache/{d}"
    n = len(os.listdir(cdir)) if os.path.isdir(cdir) else 0
    print(f"cache[{k}]={n}")

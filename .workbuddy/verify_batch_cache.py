#!/usr/bin/env python3
"""Verify cached entries against the current machine-issued batch.

Stages a maintain response, then for every candidate whose cache key exists,
checks that the cached entry's leading filename equals the candidate's
basename. Purges mismatches.
"""
import hashlib
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from auto_author import REPOS, McpSession

repo_name = sys.argv[1]
repo = REPOS[repo_name]
cache_dir = f"G:/demo/21_xiaozhi/.workbuddy/aoci/cache/{repo_name}"

session = McpSession(repo)
data = session.tool("aoci_maintain", {})
session.close()
cands = data.get("candidates", [])
print(f"staged {len(cands)} candidates")

purged = kept = absent = 0
for c in cands:
    key = hashlib.sha256(
        (repo + "|" + c["path"] + "|" + c["source_sha256"]).encode()
    ).hexdigest()
    fp = os.path.join(cache_dir, key + ".txt")
    if not os.path.exists(fp):
        absent += 1
        continue
    with open(fp, encoding="utf-8") as fh:
        entry = fh.read().strip()
    base = os.path.basename(c["path"])
    if not entry.startswith(base + "["):
        os.remove(fp)
        purged += 1
        print(f"purged mismatch: {c['path']} -> entry starts "
              f"'{entry.split('[')[0]}'")
    else:
        kept += 1
print(f"purged={purged} kept={kept} absent={absent}")

#!/usr/bin/env python3
"""Purge cache entries whose leading filename matches no candidate basename."""
import os
import sys

cache_dir = sys.argv[1]
repo = sys.argv[2]
# collect all valid basenames from the repo's managed files (git ls-files +
# untracked non-ignored is close enough; use directory walk on top dirs)
valid_names = set()
for root, dirs, files in os.walk(repo):
    dirs[:] = [d for d in dirs if d not in
               (".git", "node_modules", ".aoci", "__pycache__")]
    for f in files:
        valid_names.add(f)

removed = kept = 0
for fn in os.listdir(cache_dir):
    if not fn.endswith(".txt"):
        continue
    fp = os.path.join(cache_dir, fn)
    with open(fp, encoding="utf-8") as fh:
        c = fh.read().strip()
    if not c:
        os.remove(fp)
        removed += 1
        continue
    name = c.split("[")[0]
    if name not in valid_names:
        os.remove(fp)
        removed += 1
        print("purged:", name[:70])
    else:
        kept += 1
print(f"purged {removed}, kept {kept}")

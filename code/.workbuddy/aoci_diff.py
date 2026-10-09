import json, os, hashlib, fnmatch

REPO = r"G:/demo/21_xiaozhi/code/xiaozhi-esp32"
cfg = json.load(open(os.path.join(REPO, ".aoci", "config.json")))
base = json.load(open(os.path.join(REPO, ".aoci", "baseline.json")))
files = base["files"]

exclude_dirs = set(cfg.get("exclude_dirs") or []) | {".git", ".aoci", ".workbuddy"}
exclude_files = cfg.get("exclude_files") or []

def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()

# Walk disk, respecting excludes
disk = {}
for root, dirs, fnames in os.walk(REPO):
    # prune excluded dirs in-place
    rel_root = os.path.relpath(root, REPO)
    parts = [] if rel_root == "." else rel_root.split(os.sep)
    dirs[:] = [d for d in dirs if d not in exclude_dirs and d not in (".git",".aoci",".workbuddy")]
    for fn in fnames:
        if any(fnmatch.fnmatch(fn, pat) for pat in exclude_files):
            continue
        full = os.path.join(root, fn)
        rel = os.path.relpath(full, REPO).replace(os.sep, "/")
        try:
            disk[rel] = sha256(full)
        except Exception as e:
            print("HASHERR", rel, e)

base_set = set(files.keys())
disk_set = set(disk.keys())

new = sorted(disk_set - base_set)
deleted = sorted(base_set - disk_set)
common = disk_set & base_set
changed = sorted([p for p in common if files[p].get("sha256") != disk[p]])
unchanged = len(common) - len(changed)

print("=== DISK vs BASELINE DIFF ===")
print("disk (after exclude):", len(disk_set))
print("baseline:", len(base_set))
print("unchanged:", unchanged)
print("CHANGED:", len(changed))
print("NEW (disk only):", len(new))
print("DELETED (baseline only):", len(deleted))
print()
print("--- sample CHANGED (first 25) ---")
for p in changed[:25]:
    print("  C", p)
print("--- sample NEW (first 40) ---")
for p in new[:40]:
    print("  +", p)
print("--- sample DELETED (first 40) ---")
for p in deleted[:40]:
    print("  -", p)
# role breakdown of NEW (so we know default observe vs index)
from collections import Counter
# any new that would be expected index? none in baseline so default observe
print()
print("NEW role plan: all default 'observe' (", len(new), "files )")
# changed index-role files (preserve index)
chg_index = [p for p in changed if files[p].get("role") == "index"]
print("CHANGED that are role=index (preserve index):", len(chg_index))
for p in chg_index[:25]:
    print("  CI", p)

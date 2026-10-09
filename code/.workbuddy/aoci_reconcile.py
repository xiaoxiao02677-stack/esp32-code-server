import json, os, hashlib, fnmatch, datetime

REPO = r"G:/demo/21_xiaozhi/code/xiaozhi-esp32"
ACI = os.path.join(REPO, ".aoci")
cfg = json.load(open(os.path.join(ACI, "config.json")))
base = json.load(open(os.path.join(ACI, "baseline.json")))

exclude_dirs = set(cfg.get("exclude_dirs") or []) | {".git", ".aoci", ".workbuddy"}
exclude_files = cfg.get("exclude_files") or []

def raw_sha(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for c in iter(lambda: f.read(1 << 20), b""):
            h.update(c)
    return h.hexdigest()

def norm_sha(p):
    # line-ending normalized (CRLF->LF) sha, matching tool's normalized fingerprint
    h = hashlib.sha256()
    with open(p, "rb") as f:
        data = f.read()
    data = data.replace(b"\r\n", b"\n").replace(b"\r", b"\n")
    h.update(data)
    return h.hexdigest()

files = base["files"]
before = dict(files)  # snapshot roles

# Walk disk (exclude .workbuddy so we don't pull agent internals; preserved separately)
disk = {}
for root, dirs, fnames in os.walk(REPO):
    dirs[:] = [d for d in dirs if d not in exclude_dirs]
    for fn in fnames:
        if any(fnmatch.fnmatch(fn, pat) for pat in exclude_files):
            continue
        full = os.path.join(root, fn)
        rel = os.path.relpath(full, REPO).replace(os.sep, "/")
        try:
            disk[rel] = (raw_sha(full), norm_sha(full), os.path.getsize(full))
        except Exception as e:
            print("HASHERR", rel, e)

changed, added, dropped, preserved_wb = [], [], [], []
# Update existing + detect changes
for p in list(files.keys()):
    if p.startswith(".workbuddy/"):
        preserved_wb.append(p)  # scan-excluded; keep exactly as-is
        continue
    if p in disk:
        r, n, sz = disk[p]
        meta = files[p]
        if meta.get("sha256") != r or meta.get("normalized_sha256") != n or meta.get("size") != sz:
            changed.append(p)
        meta["sha256"] = r
        meta["normalized_sha256"] = n
        meta["size"] = sz
    else:
        # genuine deletion (not .workbuddy)
        dropped.append(p)
        del files[p]

# Add new files (default observe)
for p, (r, n, sz) in disk.items():
    if p not in files:
        added.append(p)
        files[p] = {"role": "observe", "sha256": r, "size": sz, "normalized_sha256": n}

base["updated_at"] = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
base["files"] = files

json.dump(base, open(os.path.join(ACI, "baseline.json"), "w"), ensure_ascii=False, indent=1)

from collections import Counter
print("CHANGED (refreshed):", len(changed))
for p in changed: print("  C", p, "role=", before[p].get("role"))
print("ADDED (observe):", len(added))
for p in added[:40]: print("  +", p)
print("DROPPED (genuine del):", len(dropped))
for p in dropped[:40]: print("  -", p)
print("PRESERVED .workbuddy entries:", len(preserved_wb))
print("TOTAL baseline files:", len(files))
print("role counts:", dict(Counter(m.get("role") for m in files.values())))

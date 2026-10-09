import json, os, hashlib, fnmatch, datetime

REPO = r"G:/demo/21_xiaozhi/code/xiaozhi-esp32"
ACI = os.path.join(REPO, ".aoci")
cfg = json.load(open(os.path.join(ACI, "config.json")))
base = json.load(open(os.path.join(ACI, "baseline.json")))
files = base["files"]

exclude_dirs = set(cfg.get("exclude_dirs") or []) | {".git", ".aoci", ".workbuddy"}
exclude_files = cfg.get("exclude_files") or []

def raw_sha(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for c in iter(lambda: f.read(1 << 20), b""):
            h.update(c)
    return h.hexdigest()

def norm_sha(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        data = f.read().replace(b"\r\n", b"\n").replace(b"\r", b"\n")
    h.update(data)
    return h.hexdigest()

# disk raw+size map (exclude .workbuddy so agent internals aren't pulled in; preserved separately)
disk = {}
for root, dirs, fnames in os.walk(REPO):
    dirs[:] = [d for d in dirs if d not in exclude_dirs]
    for fn in fnames:
        if any(fnmatch.fnmatch(fn, pat) for pat in exclude_files):
            continue
        full = os.path.join(root, fn)
        rel = os.path.relpath(full, REPO).replace(os.sep, "/")
        try:
            disk[rel] = (raw_sha(full), os.path.getsize(full))
        except Exception as e:
            print("HASHERR", rel, e)

updated, preserved_wb, dropped, added = [], [], [], []
for p in list(files.keys()):
    if p.startswith(".workbuddy/"):
        preserved_wb.append(p)  # scan-excluded; keep exactly as-is
        continue
    if p in disk:
        r, sz = disk[p]
        meta = files[p]
        if meta.get("sha256") != r:  # RAW content genuinely changed -> refresh all 3 fields
            updated.append(p)
            meta["sha256"] = r
            meta["size"] = sz
            meta["normalized_sha256"] = norm_sha(os.path.join(REPO, p.replace("/", os.sep)))
        # else: leave untouched (preserve original normalized_sha256 + size exactly)
    else:
        dropped.append(p)
        del files[p]

for p, (r, sz) in disk.items():
    if p not in files:
        added.append(p)
        files[p] = {"role": "observe", "sha256": r, "size": sz,
                    "normalized_sha256": norm_sha(os.path.join(REPO, p.replace("/", os.sep)))}

base["updated_at"] = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
base["files"] = files
json.dump(base, open(os.path.join(ACI, "baseline.json"), "w"), ensure_ascii=False, indent=1)

from collections import Counter
print("UPDATED (raw content changed, refreshed):", len(updated))
for p in updated: print("  U", p, "role=", files[p]["role"])
print("ADDED:", len(added), "| DROPPED (genuine):", len(dropped), "| PRESERVED .workbuddy:", len(preserved_wb))
print("TOTAL:", len(files), "| roles:", dict(Counter(m["role"] for m in files.values())))

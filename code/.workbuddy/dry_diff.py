import json, os, hashlib, fnmatch, sys

REPOS = {
    "BIG": r"G:/demo/21_xiaozhi/code/big_secreen/xiaozhi-esp32",
    "SMALL": r"G:/demo/21_xiaozhi/code/small_secreen/xiaozhi-esp32",
}

def rsha(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for c in iter(lambda: f.read(1 << 20), b""):
            h.update(c)
    return h.hexdigest()

for label, REPO in REPOS.items():
    cfg = json.load(open(os.path.join(REPO, ".aoci", "config.json")))
    base = json.load(open(os.path.join(REPO, ".aoci", "baseline.json")))
    files = base["files"]
    ex_dir = set(cfg.get("exclude_dirs") or []) | {".git", ".aoci", ".workbuddy"}
    ex_f = cfg.get("exclude_files") or []
    disk = {}
    for root, dirs, fnames in os.walk(REPO):
        dirs[:] = [d for d in dirs if d not in ex_dir]
        for fn in fnames:
            if any(fnmatch.fnmatch(fn, pat) for pat in ex_f):
                continue
            full = os.path.join(root, fn)
            rel = os.path.relpath(full, REPO).replace(os.sep, "/")
            try:
                disk[rel] = rsha(full)
            except Exception as e:
                print("HASHERR", rel, e)
    changed = [p for p in files if not p.startswith(".workbuddy/") and p in disk and files[p].get("sha256") != disk[p]]
    new = [p for p in disk if p not in files]
    deleted = [p for p in files if p not in disk and not p.startswith(".workbuddy/")]
    print(f"[{label}] files={len(files)} disk={len(disk)} CHANGED={len(changed)} NEW={len(new)} DELETED={len(deleted)}")
    for p in changed[:15]:
        print("   C", p, files[p].get("role"))
    for p in new[:10]:
        print("   +", p)
    for p in deleted[:10]:
        print("   -", p)

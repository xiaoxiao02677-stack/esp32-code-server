#!/usr/bin/env python3
"""Survey all yuhe occurrences in the repo (READ-ONLY)."""
import os
import re
import collections

ROOT = r"G:\demo\21_xiaozhi"

EXCLUDE_DIRS = {
    ".git", "build", "managed_components", "node_modules", "dist", "target",
    ".venv", "venv", "__pycache__", "models", "tmp", "data", ".workbuddy",
    ".trash", ".idea", ".vscode", ".tmp", "artifacts", ".cache", "unpacked",
    ".devcontainer", "coverage",
}

BIN_EXT = {
    ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".ico", ".webp", ".woff", ".woff2",
    ".ttf", ".otf", ".bin", ".elf", ".wav", ".mp3", ".ogg", ".opus", ".zip",
    ".gz", ".tar", ".7z", ".pdf", ".exe", ".dll", ".so", ".a", ".o", ".lib",
    ".jar", ".class", ".mp4", ".avi", ".wasm", ".db", ".sqlite", ".onnx",
    ".pt", ".pth", ".pcapng", ".img", ".bin",
}

VARIANTS = [
    b"yuhe", b"Yuhe", b"YUHE", b"Yuhe", b"Yuhe",
    b"yuhe", b"yuhe", b"Yuhe", b"YUHE", b"Yuhe",
]
URL_PAT = re.compile(rb"https?://[^\s\"'<>()]*[xX][iI][aA][oO][zZ][hH][iI]")


def area_of(rel):
    p = rel.replace("\\", "/")
    parts = p.split("/")
    if parts[0] == "hardware":
        if p.startswith("hardware/sets/yuhe-esp32/"):
            return "fw:sets/yuhe-esp32"
        if parts[1:2] == ["sets"]:
            return "hw:sets-other"
        return "hw:" + parts[1]
    if parts[0] == "yh":
        if len(parts) > 1:
            return "yh:" + parts[1]
        return "yh:root"
    if parts[0] in ("docs", "tools", "code", "third_party"):
        return parts[0] if len(parts) == 1 else parts[0]
    return "root"


file_stats = collections.defaultdict(lambda: [0, 0])
variant_counter = collections.Counter()
urls = []
name_hits = []
binary_hits = []
errors = []

for dirpath, dirnames, filenames in os.walk(ROOT):
    for d in dirnames:
        if "yuhe" in d.lower():
            name_hits.append(os.path.relpath(os.path.join(dirpath, d), ROOT) + "/")
    dirnames[:] = [d for d in dirnames if d not in EXCLUDE_DIRS]
    for fn in filenames:
        fp = os.path.join(dirpath, fn)
        rel = os.path.relpath(fp, ROOT)
        ext = os.path.splitext(fn)[1].lower()
        if "yuhe" in fn.lower():
            name_hits.append(rel)
        if ext in BIN_EXT:
            continue
        try:
            with open(fp, "rb") as f:
                data = f.read()
        except OSError as e:
            errors.append(f"{rel}: {e}")
            continue
        if b"\x00" in data[:8192]:
            if any(v in data for v in (b"yuhe", b"Yuhe", b"YUHE")):
                binary_hits.append(rel)
            continue
        total = 0
        for v in VARIANTS:
            c = data.count(v)
            if c:
                variant_counter[v.decode()] += c
                total += c
        for m in URL_PAT.finditer(data):
            urls.append((rel, m.group(0).decode("utf-8", "replace")))
        if total:
            a = area_of(rel)
            file_stats[a][0] += 1
            file_stats[a][1] += total

print("=== per-area (files, occurrences) ===")
for a in sorted(file_stats):
    print(f"{a:36s} files={file_stats[a][0]:5d} hits={file_stats[a][1]:6d}")
print("\n=== variants ===")
for v, c in variant_counter.most_common():
    print(f"{v:12s} {c}")
print(f"\n=== URLs containing yuhe ({len(urls)}) ===")
seen = set()
for rel, u in urls:
    key = (rel, u)
    if key in seen:
        continue
    seen.add(key)
    print(f"{rel}: {u[:140]}")
print(f"\n=== dir/file names containing yuhe ({len(name_hits)}) ===")
for n in name_hits[:100]:
    print(" ", n)
if len(name_hits) > 100:
    print(f"  ... +{len(name_hits) - 100} more")
print(f"\n=== binary files with hits ({len(binary_hits)}) ===")
for b in binary_hits[:20]:
    print(" ", b)
if errors:
    print("\n=== errors ===")
    for e in errors[:10]:
        print(" ", e)

total_hits = sum(v[1] for v in file_stats.values())
total_files = sum(v[0] for v in file_stats.values())
print(f"\nTOTAL: {total_files} files, {total_hits} occurrences")

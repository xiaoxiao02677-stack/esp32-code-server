#!/usr/bin/env python3
"""Batch rename yuhe -> yuhe across the repo (content + git mv).

Usage:
  python _rename_yuhe_yuhe.py --dry    # report only, no writes
  python _rename_yuhe_yuhe.py --apply  # rewrite files + git mv

Strategy:
  1. Protect (placeholder-stash) all exempt byte patterns & external URLs.
  2. Apply case-variant replacements (yuhe->yuhe, Yuhe->Yuhe, ...).
  3. Restore placeholders.
  4. git mv files/dirs whose names contain the variants (top-most only).

Exemptions (protected):
  - 21_xiaozhi                  repo root physical path (kept as-is)
  - nihaoxiaozhi / NIHAOXIAOZHI espressif wake-word model name & URLs
  - xiaozhi-fonts               espressif component registry package
  - xiaozhi_esp32_server        production MySQL database name
  - /root/xiaozhi-server        production deploy path
  - /opt/xiaozhi                production java path
  - xiaozhi-esp32-api.jar       production jar artifact name
  - xiaozhi-manager             production nginx site name
  - whole URLs whose host is external (github.com, dl.espressif.com, ...)
"""
import argparse
import collections
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(r"G:\demo\21_xiaozhi")

# dirs never touched for CONTENT replacement (rename via git ls-files is separate)
EXCLUDE_DIRS = {
    ".git", "build", "build-small_secreen", "build-camera", "build-big_secreen",
    "managed_components", "node_modules", "dist", "dist-admin", "target",
    ".venv", "venv", "__pycache__", "models", "tmp", "data", ".trash",
    ".idea", ".vscode", ".tmp", ".tmpbuild", "artifacts", ".cache", "unpacked",
    ".devcontainer", "coverage", "out", ".pytest_cache", "test-results",
    "server_versions",  # wc_sync_work snapshots (also via SKIP_SUBTREES)
}

BIN_EXT = {
    ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".ico", ".webp", ".woff", ".woff2",
    ".ttf", ".otf", ".bin", ".elf", ".wav", ".mp3", ".ogg", ".opus", ".zip",
    ".gz", ".tar", ".7z", ".pdf", ".exe", ".dll", ".so", ".a", ".o", ".lib",
    ".jar", ".class", ".mp4", ".avi", ".wasm", ".db", ".sqlite", ".onnx",
    ".pt", ".pth", ".pcapng", ".img", ".pack", ".idx", ".index",
}

REPLACEMENTS = [
    (b"YUHE", b"YUHE"),
    (b"Yuhe", b"Yuhe"),
    (b"Yuhe", b"Yuhe"),
    (b"Yuhe", b"Yuhe"),
    (b"yuhe", b"yuhe"),
    (b"yuhe", b"yuhe"),
    (b"yuhe", b"yuhe"),
    (b"Yuhe", b"Yuhe"),
    (b"YUHE", b"YUHE"),
    (b"Yuhe", b"Yuhe"),
]

PROTECTED_LITERALS = [
    b"21_xiaozhi",
    b"nihaoxiaozhi", b"NIHAOXIAOZHI",
    b"xiaozhi-fonts",
    b"xiaozhi_esp32_server",
    b"/root/xiaozhi-server",
    b"/opt/xiaozhi",
    b"xiaozhi-esp32-api.jar",
    b"xiaozhi-manager",
]

EXTERNAL_HOSTS = {
    "github.com", "api.star-history.com", "star-history.com",
    "dl.espressif.com", "spotpear.cn", "files.waveshare.com",
    "oshwhub.com", "gitee.com", "raw.githubusercontent.com",
}
URL_RE = re.compile(rb"https?://[^\s\"'<>()\\[\]{}]+")
HOST_RE = re.compile(rb"https?://([^/:]+)")

# whole files skipped for content AND rename (production copies / migration-manual)
SKIP_FILES = {
    "yh/console-v2/deploy/prod-yuhe-common.conf",   # manual: dual-route rewrite
    "code/.workbuddy/yuhe-server.service",           # prod systemd copy
    "code/.workbuddy/nginx-site-xiaozhi-manager.conf",  # prod nginx copy
    "code/.workbuddy/nginx-snippet-yuhe-common.conf",
    "code/.workbuddy/nginx_yuhe_manager_fixed.conf",
}

# subtrees skipped for content AND rename (history logs / snapshots)
SKIP_SUBTREES = [
    ".workbuddy/wc_sync_work",
    "code/.workbuddy/memory",
    "code/.workbuddy/wc_sync_work",
    "code/.workbuddy/tmp",
    ".workbuddy/memory",
]

# untracked plain dirs (no git history): rename via os.rename
PLAIN_RENAME_DIRS = [
    "hardware/small_secreen_test",
    "hardware/small_screen_camera",
    "hardware/sets_test_envirment",
]

# nested git repos: run a second pass inside them (paths relative to repo)
NESTED_REPOS = {
    "hardware/camera": "camera",   # rel-prefix in main repo -> repo dir name
}

MARK = b"\x00\x01RK%d\x01\x00"

stash_stats = collections.Counter()
ext_url_hosts = collections.Counter()


def is_skipped(rel_posix: str) -> bool:
    if rel_posix in SKIP_FILES:
        return True
    for sub in SKIP_SUBTREES:
        if rel_posix == sub or rel_posix.startswith(sub + "/"):
            return True
    return False


def protect(data: bytes) -> tuple[bytes, list[bytes]]:
    stash = []

    def keep(value: bytes) -> bytes:
        stash.append(value)
        return MARK % (len(stash) - 1)

    for lit in PROTECTED_LITERALS:
        n = data.count(lit)
        if n:
            stash_stats[lit.decode()] += n
            data = data.replace(lit, keep(lit))

    def keep_url(m):
        url = m.group(0)
        hm = HOST_RE.match(url)
        host = (hm.group(1).decode("utf-8", "replace").lower()
                if hm else "")
        if host in EXTERNAL_HOSTS:
            ext_url_hosts[host] += 1
            return keep(url)
        return url

    data = URL_RE.sub(keep_url, data)
    return data, stash


def restore(data: bytes, stash: list[bytes]) -> bytes:
    for i, s in enumerate(stash):
        data = data.replace(MARK % i, s)
    return data


def transform(data: bytes) -> tuple[bytes, dict]:
    counts = {}
    protected, stash = protect(data)
    for old, new in REPLACEMENTS:
        c = protected.count(old)
        if c:
            counts[old.decode()] = c
            protected = protected.replace(old, new)
    out = restore(protected, stash)
    return out, counts


def collect_content_files():
    files = []
    for dirpath, dirnames, filenames in os.walk(ROOT):
        dirnames[:] = [d for d in dirnames
                       if d not in EXCLUDE_DIRS
                       and not (d.lower().startswith("build"))]  # build* dirs
        for fn in filenames:
            fp = Path(dirpath) / fn
            rel = fp.relative_to(ROOT).as_posix()
            if is_skipped(rel):
                continue
            if fp.suffix.lower() in BIN_EXT:
                continue
            if fn == ".gitignore" or fn.startswith(".git"):
                pass  # .gitignore is a normal text file, keep it
            try:
                with open(fp, "rb") as f:
                    head = f.read(8192)
            except OSError:
                continue
            if b"\x00" in head:
                continue  # binary / utf-16
            files.append(fp)
    return files


def new_name(name: str) -> str | None:
    """Return renamed name if any variant applies and no protected literal."""
    low = name.lower()
    if any(p.decode().lower() in low for p in PROTECTED_LITERALS):
        return None
    out = name
    for old, new in REPLACEMENTS:
        if old.decode() in out:
            out = out.replace(old.decode(), new.decode())
    return out if out != name else None


def collect_renames():
    """Collect (old_rel, new_rel) rename pairs from git-tracked paths."""
    out = subprocess.run(
        ["git", "ls-files", "-z"], cwd=ROOT, capture_output=True, check=True)
    tracked = [p for p in out.stdout.decode("utf-8", "replace").split("\0") if p]
    pairs = []
    seen_dirs = set()
    for rel in tracked:
        if is_skipped(rel):
            continue
        parts = rel.split("/")
        # find the shallowest path component that would be renamed
        renamed_parts = [new_name(p) or p for p in parts]
        if renamed_parts == parts:
            continue
        new_rel = "/".join(renamed_parts)
        # if an ancestor dir is already renamed as another entry, git mv of
        # the ancestor covers this file; dedupe by ancestor mapping
        pairs.append((rel, new_rel))
    # keep only top-most renames: drop entries whose old path is inside
    # another entry's old path (dir) that also gets renamed
    top = []
    for old, new in sorted(pairs, key=lambda x: x[0].count("/")):
        if any(old != o2 and old.startswith(o2.rstrip("/") + "/")
               for o2, _ in top):
            continue
        top.append((old, new))
    return top


def area_of(rel: str) -> str:
    p = rel
    parts = p.split("/")
    if parts[0] == "hardware":
        if p.startswith("hardware/sets/"):
            return "fw:sets"
        return "hw:" + parts[1]
    if parts[0] == "yh":
        return "yh:" + parts[1] if len(parts) > 1 else "yh:root"
    return parts[0] if parts[0] in ("docs", "tools", "code", "third_party") else "root"


def main():
    global ROOT
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--root", default=str(ROOT))
    ap.add_argument("--plain", action="store_true",
                    help="run in plain (non-git) mode for nested/untracked dirs")
    args = ap.parse_args()
    do_apply = args.apply
    ROOT = Path(args.root)

    # ---- content pass ----
    area_stats = collections.defaultdict(lambda: [0, 0])
    variant_totals = collections.Counter()
    changed_files = []
    residual = []

    for fp in collect_content_files():
        rel = fp.relative_to(ROOT).as_posix()
        with open(fp, "rb") as f:
            data = f.read()
        counts = {}
        for old, _ in REPLACEMENTS:
            c = data.count(old)
            if c:
                counts[old.decode()] = c
        if not counts:
            continue
        new_data, _ = transform(data)
        a = area_of(rel)
        area_stats[a][0] += 1
        area_stats[a][1] += sum(counts.values())
        for v, c in counts.items():
            variant_totals[v] += c
        changed_files.append((rel, counts))
        if do_apply:
            with open(fp, "wb") as f:
                f.write(new_data)

    # ---- rename pass (main repo, git-tracked) ----
    renames = collect_renames()

    # plain dirs: top-level yuhe-named dirs/files inside them
    plain_renames = []
    for d in PLAIN_RENAME_DIRS:
        base = ROOT / d
        if not base.is_dir():
            continue
        # the dir itself contains "yuhe" in its own name? (e.g. .../yuhe-esp32/)
        for dirpath, dirnames, filenames in os.walk(base):
            # rename files first, then dirs bottom-up
            for fn in filenames:
                if any(v.decode() in fn for v, _ in REPLACEMENTS):
                    fp = Path(dirpath) / fn
                    plain_renames.append(("file", str(fp), str(fp.parent / new_name(fn))))
            for dn in list(dirnames):
                if any(v.decode() in dn for v, _ in REPLACEMENTS):
                    dp = Path(dirpath) / dn
                    plain_renames.append(("dir", str(dp), str(dp.parent / new_name(dn))))
            dirnames[:] = [d for d in dirnames if d not in EXCLUDE_DIRS and not d.lower().startswith("build")]
    # sort: deepest first (children before parents), dirs after files in same dir
    plain_renames.sort(key=lambda t: (-t[1].count("\\"), -t[1].count("/"), 0 if t[0] == "file" else 1))

    print("=== content replacement (per-area) ===")
    for a in sorted(area_stats):
        print(f"{a:24s} files={area_stats[a][0]:5d} hits={area_stats[a][1]:6d}")
    print("\n=== per-variant ===")
    for v, c in variant_totals.most_common():
        print(f"{v:10s} {c}")
    print(f"\nTOTAL content: {len(changed_files)} files, "
          f"{sum(variant_totals.values())} replacements")
    print(f"\n=== protected literals (kept as-is) ===")
    for k, v in stash_stats.most_common():
        print(f"{k:28s} {v}")
    print(f"\n=== protected external URL hosts ===")
    for h, c in ext_url_hosts.most_common():
        print(f"{h:32s} {c}")
    print(f"\n=== rename plan: {len(renames)} git-tracked top-level entries ===")
    for old, new in renames:
        print(f"  {old}  ->  {new}")
    print(f"\n=== rename plan: {len(plain_renames)} plain (untracked) entries ===")
    for kind, old, new in plain_renames[:40]:
        print(f"  [{kind}] {old}  ->  {new}")
    if len(plain_renames) > 40:
        print(f"  ... +{len(plain_renames) - 40} more")

    if not do_apply:
        print("\n[DRY RUN] no files written. Re-run with --apply.")
        return

    # apply git mv (top-most only; git mv of a dir moves the whole tree)
    ok, fail = 0, 0
    for old, new in renames:
        r = subprocess.run(["git", "mv", "--", old, new], cwd=ROOT,
                           capture_output=True, text=True)
        if r.returncode == 0:
            ok += 1
        else:
            fail += 1
            print(f"git mv FAILED: {old} -> {new}: {r.stderr.strip()}")
    print(f"\ngit mv: {ok} ok, {fail} failed")

    # apply plain renames (deepest first)
    pok, pfail = 0, 0
    for kind, old, new in plain_renames:
        try:
            os.rename(old, new)
            pok += 1
        except OSError as e:
            pfail += 1
            print(f"rename FAILED [{kind}] {old}: {e}")
    print(f"plain rename: {pok} ok, {pfail} failed")

    # nested repos: recurse into each with same logic (self-invocation)
    for repo_dir, label in NESTED_REPOS.items():
        print(f"\n>>> nested repo {repo_dir} — run again inside it")
    print("\nDone. Next: manual compatibility edits + verification.")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Fixup pass: complete renames that `git mv` failed (missing target parent).

Strategy:
  1. Recompute rename plan from git ls-files (current index state).
  2. Split into: top-most DIR renames (os.rename moves untracked content too)
     and file-only renames (basename change).
  3. Execute with makedirs; skip sources that no longer exist (already done).
  4. git add -u (stage modifications/deletions) + git add <new paths>.
"""
import os
import subprocess
from pathlib import Path

ROOT = Path(r"G:\demo\21_xiaozhi")

REPLACEMENTS = [
    ("XIAOZHI", "YUHE"), ("XiaoZhi", "Yuhe"), ("Xiaozhi", "Yuhe"),
    ("xiaoZhi", "Yuhe"), ("xiaozhi", "yuhe"), ("xiao-zhi", "yuhe"),
    ("xiao_zhi", "yuhe"), ("Xiao_Zhi", "Yuhe"), ("XIAO_ZHI", "YUHE"),
    ("Xiao-Zhi", "Yuhe"),
]
PROTECTED = ["21_xiaozhi", "nihaoxiaozhi", "NIHAOXIAOZHI", "xiaozhi-fonts",
             "xiaozhi_esp32_server", "/root/xiaozhi-server", "/opt/xiaozhi",
             "xiaozhi-esp32-api.jar", "xiaozhi-manager", "wn9_nihaoxiaozhi"]

SKIP_PREFIXES = [
    ".workbuddy/wc_sync_work", "code/.workbuddy/memory",
    "code/.workbuddy/wc_sync_work", "code/.workbuddy/tmp", ".workbuddy/memory",
]
SKIP_FILES = {
    "yh/console-v2/deploy/prod-xiaozhi-common.conf",
    "code/.workbuddy/xiaozhi-server.service",
    "code/.workbuddy/nginx-site-xiaozhi-manager.conf",
    "code/.workbuddy/nginx-snippet-xiaozhi-common.conf",
    "code/.workbuddy/nginx_xiaozhi_manager_fixed.conf",
}


def new_comp(name: str):
    low = name.lower()
    if any(p.lower() in low for p in PROTECTED):
        return None
    out = name
    for old, new in REPLACEMENTS:
        if old in out:
            out = out.replace(old, new)
    return out if out != name else None


def new_path(rel: str):
    parts = rel.split("/")
    renamed = [new_comp(p) or p for p in parts]
    return "/".join(renamed) if renamed != parts else None


def main():
    out = subprocess.run(["git", "ls-files", "-z"], cwd=ROOT,
                         capture_output=True, check=True)
    tracked = [p for p in out.stdout.decode("utf-8", "replace").split("\0") if p]

    # Build full plan (only entries where path still contains a variant AND
    # the source exists on disk).
    plan = []
    for rel in tracked:
        if rel in SKIP_FILES or any(rel.startswith(s + "/") or rel == s
                                    for s in SKIP_PREFIXES):
            continue
        np = new_path(rel)
        if not np:
            continue
        if not (ROOT / rel).exists():
            continue  # already moved by earlier git mv
        plan.append((rel, np))

    # Derive top-most DIR renames: for each plan entry, find shallowest
    # component that changes -> that's a dir rename boundary (or file rename
    # if it's the last component).
    dir_renames = {}   # old_dir -> new_dir (relative)
    file_renames = []  # (old_file, new_file) where only basename changes
    for old, new in plan:
        op, np_ = old.split("/"), new.split("/")
        # find first differing component
        i = next((k for k in range(len(op)) if op[k] != np_[k]), None)
        if i is None:
            continue
        if i == len(op) - 1:
            # only basename differs -> file rename (parent unchanged)
            file_renames.append((old, new))
        else:
            # a directory component differs -> record dir rename old->new
            od = "/".join(op[:i + 1])
            nd = "/".join(np_[:i + 1])
            prev = dir_renames.get(od)
            if prev and prev != nd:
                print(f"CONFLICT dir mapping {od}: {prev} vs {nd}")
            dir_renames[od] = nd

    # sort dir renames shallow-first
    dir_items = sorted(dir_renames.items(), key=lambda kv: kv[0].count("/"))

    print(f"plan: {len(plan)} entries -> {len(dir_items)} dir renames, "
          f"{len(file_renames)} file renames")
    for od, nd in dir_items:
        print(f"  [dir ] {od} -> {nd}")

    ok = fail = 0
    # dir renames first (shallow-first; children come along)
    for od, nd in dir_items:
        src, dst = ROOT / od, ROOT / nd
        try:
            dst.parent.mkdir(parents=True, exist_ok=True)
            if dst.exists():
                # target exists (e.g. partially created by earlier git mv):
                # move remaining children individually
                for ch in src.iterdir():
                    tgt = dst / ch.name
                    if tgt.exists():
                        print(f"  SKIP (both exist): {ch} vs {tgt}")
                        continue
                    os.rename(ch, tgt)
                src.rmdir()
            else:
                os.rename(src, dst)
            ok += 1
        except OSError as e:
            fail += 1
            print(f"dir rename FAILED {od} -> {nd}: {e}")

    # file renames (skip those whose parent was already renamed -> path gone)
    fok = ffail = 0
    for of, nf in file_renames:
        src, dst = ROOT / of, ROOT / nf
        if not src.exists():
            continue  # parent renamed already moved it under new tree
        try:
            dst.parent.mkdir(parents=True, exist_ok=True)
            os.rename(src, dst)
            fok += 1
        except OSError as e:
            ffail += 1
            print(f"file rename FAILED {of} -> {nf}: {e}")

    # ALSO: files under renamed dirs whose BASENAME changes (e.g.
    # xiaozhi_ogg_converter.py inside xiaozhi-esp32 tree). After dir rename
    # they sit under the NEW tree with old basename.
    bfok = bffail = 0
    for rel in tracked:
        if rel in SKIP_FILES or any(rel.startswith(s + "/") or rel == s
                                    for s in SKIP_PREFIXES):
            continue
        np_ = new_path(rel)
        if not np_:
            continue
        # candidate new-tree path with old basename still present?
        parts = np_.split("/")
        base_old = rel.split("/")[-1]
        if new_comp(base_old) is None:
            continue
        # locate actual file: old path if exists, else new-tree path with old basename
        cand_old = ROOT / rel
        parts_np = np_.split("/")
        parts_np[-1] = base_old
        cand_moved = ROOT / "/".join(parts_np)
        src = cand_old if cand_old.exists() else (cand_moved if cand_moved.exists() else None)
        if not src:
            continue
        dst = ROOT / np_
        if dst.exists():
            continue
        try:
            dst.parent.mkdir(parents=True, exist_ok=True)
            os.rename(src, dst)
            bfok += 1
        except OSError as e:
            bffail += 1
            print(f"basename rename FAILED {src} -> {dst}: {e}")

    print(f"\ndir renames: {ok} ok, {fail} failed")
    print(f"file renames: {fok} ok, {ffail} failed")
    print(f"basename renames (post dir-move): {bfok} ok, {bffail} failed")

    # stage: modifications + deletions of tracked, then new paths
    r = subprocess.run(["git", "add", "-u"], cwd=ROOT)
    new_paths = [ROOT / np_ for _, np_ in plan if (ROOT / np_).exists()]
    # add in batches of 200 (Windows cmdline limits)
    added = 0
    for i in range(0, len(new_paths), 200):
        batch = [str(p.relative_to(ROOT)).replace("\\", "/")
                 for p in new_paths[i:i + 200]]
        r2 = subprocess.run(["git", "add", "--"] + batch, cwd=ROOT)
        if r2.returncode != 0:
            print(f"git add batch {i} FAILED")
        else:
            added += len(batch)
    print(f"staged new paths: {added}")
    print("done")


if __name__ == "__main__":
    main()

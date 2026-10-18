#!/usr/bin/env python3
"""Residual xiaozhi scan after rename (exempt-aware, line-level)."""
import os
import re

ROOT = r"G:\demo\21_xiaozhi"

EXCLUDE = {".git", "build", "managed_components", "node_modules", "dist", "dist-admin",
           "target", ".venv", "venv", "__pycache__", "models", "tmp", "data", ".trash",
           ".idea", ".vscode", ".tmp", ".tmpbuild", "artifacts", ".cache", "unpacked",
           ".devcontainer", "coverage", "out", ".pytest_cache", "test-results",
           "server_versions", "wc_sync_work", "deploy-backup-local", "deploy_prod_20261017",
           "_scout_py", "verify", "bp"}

BIN_EXT = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".ico", ".webp", ".woff", ".woff2",
           ".ttf", ".otf", ".bin", ".elf", ".wav", ".mp3", ".ogg", ".opus", ".zip",
           ".gz", ".tar", ".7z", ".pdf", ".exe", ".dll", ".so", ".a", ".o", ".lib",
           ".jar", ".class", ".mp4", ".avi", ".wasm", ".db", ".sqlite", ".onnx",
           ".pt", ".pth", ".pcapng", ".img", ".pack", ".idx", ".index"}

EXEMPT_LINE = re.compile(
    r"21_xiaozhi|nihaoxiaozhi|NIHAOXIAOZHI|xiaozhi-fonts|xiaozhi_esp32_server|"
    r"/root/xiaozhi-server|/opt/xiaozhi|xiaozhi-esp32-api\.jar|xiaozhi-manager|"
    r"github\.com/78/xiaozhi|github\.com/xinnan-tech/xiaozhi|github\.com/joey-zhou/xiaozhi|"
    r"github\.com/AnimeAIChat/xiaozhi|github\.com/huangjunsen0406/py-xiaozhi|github\.com/TOM88812/xiaozhi|"
    r"github\.com/100askTeam/xiaozhi|github\.com/QuecPython/solution-xiaozhi|"
    r"star-history\.com|oshwhub\.com|dl\.espressif\.com|spotpear\.cn|files\.waveshare\.com|"
    r"xiaozhi\.server\.com|xiaozhi-esp32-server-web|_rename_xiaozhi|_survey_xiaozhi|"
    r"wn9s_nihaoxiaozhi|logrotate_xiaozhi|prod-xiaozhi-common|nginx[^/]*xiaozhi|xiaozhi-server\.service",
    re.IGNORECASE)

# file-level exempts (production deploy copies, migration docs, tool scripts)
EXEMPT_FILE_SUBSTR = [
    "prod-xiaozhi-common.conf", "xiaozhi-server.service",
    "nginx-site-xiaozhi-manager.conf", "nginx-snippet-xiaozhi-common.conf",
    "nginx_xiaozhi_manager_fixed.conf", "deploy-backup-local", "deploy_prod_20261017",
    "_scout_py", "code/.workbuddy/verify", "docs/bp", "code/.workbuddy/memory",
    ".workbuddy/memory", "wc_sync_work", "code/.workbuddy/tmp",
    "_rename_xiaozhi_yuhe.py", "_survey_xiaozhi.py", "_rename_fixup.py",
]

HIT = re.compile(r"xiaozhi|xiao[-_]zhi|XiaoZhi|Xiaozhi|XIAOZHI", re.IGNORECASE)


def exempt_path(rel: str) -> bool:
    rl = rel.replace("\\", "/")
    return any(s in rl for s in EXEMPT_FILE_SUBSTR)


def main():
    hits = []
    nfiles = 0
    for dirpath, dirnames, filenames in os.walk(ROOT):
        dirnames[:] = [d for d in dirnames
                       if d not in EXCLUDE
                       and not d.lower().startswith("build")]
        for fn in filenames:
            fp = os.path.join(dirpath, fn)
            rel = os.path.relpath(fp, ROOT)
            if exempt_path(rel):
                continue
            ext = os.path.splitext(fn)[1].lower()
            if ext in BIN_EXT:
                continue
            try:
                with open(fp, "rb") as f:
                    data = f.read()
            except OSError:
                continue
            if b"\x00" in data[:8192]:
                continue
            nfiles += 1
            for i, line in enumerate(data.split(b"\n"), 1):
                t = line.decode("utf-8", "replace")
                if HIT.search(t) and not EXEMPT_LINE.search(t):
                    hits.append(f"{rel}:{i}: {t.strip()[:150]}")

    print(f"scanned {nfiles} files")
    print(f"residual lines: {len(hits)}")
    for h in hits[:100]:
        print(h)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Auto git sync watchdog: commit & push workspace changes every cycle.

- Polls `git status --porcelain`; on any change: add -A, commit, push.
- Commits to master; push failures are logged and retried next cycle.
- Also revives the AOCI authoring pipelines (supervisor behavior folded in).
"""
import json
import subprocess
import time

ROOT = "G:/demo/21_xiaozhi"
AOCI = "D:/INSTALL/aoci/aoci.exe"
REPOS = {
    "code-server-mirror": ROOT + "/code-server-mirror",
    "hermes-agent-main": ROOT + "/hermes-agent-main",
}
INTERVAL = 900  # 15 min


def sh(*args, timeout=600):
    return subprocess.run(list(args), cwd=ROOT, capture_output=True,
                          timeout=timeout, text=True, encoding="utf-8",
                          errors="replace")


def git_sync():
    st = sh("git", "status", "--porcelain")
    if st.returncode != 0:
        print("[gitsync] status error:", st.stderr[:200], flush=True)
        return
    changes = st.stdout.strip()
    if not changes:
        print("[gitsync] clean", flush=True)
        return
    n = len(changes.splitlines())
    stamp = time.strftime("%Y-%m-%d %H:%M")
    sh("git", "add", "-A")
    cm = sh("git", "commit", "-m", f"auto-sync {stamp}: {n} changed paths")
    if cm.returncode != 0:
        print("[gitsync] commit failed:", cm.stderr[:300], flush=True)
        return
    ps = sh("git", "push", "origin", "master")
    if ps.returncode == 0:
        h = sh("git", "rev-parse", "--short", "HEAD").stdout.strip()
        print(f"[gitsync] pushed {h} ({n} paths)", flush=True)
    else:
        print("[gitsync] push failed:", ps.stderr[:300], flush=True)


def pipelines_running():
    r = subprocess.run(
        ["wmic", "process", "where",
         "commandline like '%auto_author.py%' and name like 'python%'",
         "get", "commandline", "/format:csv"],
        capture_output=True, timeout=30)
    out = r.stdout.decode("utf-8", "replace")
    return {n for n in REPOS if f"auto_author.py {n}" in out}


def authoring_remaining(path):
    r = subprocess.run([AOCI, "--repo", path, "scope", "status", "--json"],
                       capture_output=True, timeout=300)
    d = json.loads(r.stdout.decode("utf-8", "replace"))
    return d.get("authoring_targets", 0)


def revive_pipelines():
    active = pipelines_running()
    for name, path in REPOS.items():
        try:
            remaining = authoring_remaining(path)
        except Exception as e:
            print("[aoci] status error", name, str(e)[:100], flush=True)
            continue
        if remaining > 0 and name not in active:
            log = open((ROOT + "/.workbuddy/full_server.log"
                        if "server" in name
                        else ROOT + "/.workbuddy/full_hermes.log"),
                       "a", encoding="utf-8")
            log.write(f"\n=== gitsync revive {time.strftime('%H:%M:%S')} ===\n")
            log.flush()
            subprocess.Popen(
                ["python", ROOT + "/.workbuddy/auto_author.py", name],
                stdout=log, stderr=log, cwd=ROOT)
            print(f"[aoci] revived {name} ({remaining} targets)", flush=True)


if __name__ == "__main__":
    while True:
        try:
            git_sync()
            revive_pipelines()
        except Exception as e:
            print("[watchdog] error:", str(e)[:200], flush=True)
        time.sleep(INTERVAL)

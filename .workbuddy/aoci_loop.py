#!/usr/bin/env python3
"""
AOCI authoring loop: maintain -> [human/model authored entries] -> update_entry.

Phase 1 (--stage): for each repo, call maintain and save the current batch to
  .workbuddy/aoci/<repo>/batch.json  (one file, overwritten per iteration).
Phase 2 (--submit <repo> <entries.json>): submit a fully authored entries file
  through aoci_update_entry using code_batch_id from batch.json.

Authoring happens between the two phases (by the agent).
"""
import json
import os
import subprocess
import sys
import threading
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WORK = os.path.join(ROOT, ".workbuddy", "aoci")
AOCI = "D:/INSTALL/aoci/aoci.exe"


def mcp_session(repo):
    proc = subprocess.Popen(
        [AOCI, "--repo", repo, "mcp"],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE,
        stderr=subprocess.PIPE, text=True, encoding="utf-8", bufsize=1,
    )
    outbox = []
    threading.Thread(
        target=lambda: [outbox.append(json.loads(l))
                        for l in proc.stdout if l.strip()],
        daemon=True,
    ).start()
    _id = [0]

    def send(msg):
        proc.stdin.write(json.dumps(msg) + "\n")
        proc.stdin.flush()

    def call(method, params=None, timeout=3600):
        _id[0] += 1
        rid = _id[0]
        send({"jsonrpc": "2.0", "id": rid, "method": method,
              "params": params or {}})
        deadline = time.time() + timeout
        while time.time() < deadline:
            for i, m in enumerate(outbox):
                if m.get("id") == rid:
                    outbox.pop(i)
                    return m
            time.sleep(0.05)
        return {"error": "timeout", "id": rid}

    call("initialize", {
        "protocolVersion": "2024-11-05", "capabilities": {},
        "clientInfo": {"name": "hermes-aoci-loop", "version": "1.0"},
    })
    send({"jsonrpc": "2.0", "method": "notifications/initialized"})
    return call, proc


def tool_text(r):
    content = r.get("result", {}).get("content", [])
    out = ""
    for c in content:
        out += c.get("text", "")
    return out


def stage(repo):
    call, proc = mcp_session(repo)
    r = call("tools/call", {"name": "aoci_maintain", "arguments": {}})
    text = tool_text(r)
    proc.terminate()
    data = json.loads(text)
    os.makedirs(os.path.join(WORK, "stage"), exist_ok=True)
    name = os.path.basename(os.path.normpath(repo))
    path = os.path.join(WORK, "stage", name + ".json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    ab = data.get("authoring_batch", {})
    print(f"[{name}] status={data.get('status')} "
          f"included={ab.get('included')} remaining={ab.get('remaining')} "
          f"complete={ab.get('complete_candidate_set_for_current_batch')}")
    print(f"[{name}] saved -> {path}")
    if data.get("status") == "stopped":
        print(f"[{name}] STOPPED: {data.get('next_action')} "
              f"{data.get('next_commands')}")


def submit(repo, entries_path):
    staged_path = os.path.join(
        WORK, "stage", os.path.basename(os.path.normpath(repo)) + ".json")
    with open(staged_path, encoding="utf-8") as f:
        batch = json.load(f)
    with open(entries_path, encoding="utf-8") as f:
        authored = json.load(f)

    call, proc = mcp_session(repo)
    args = {
        "code_batch_id": authored["code_batch_id"],
        "entries": authored["entries"],
    }
    r = call("tools/call", {
        "name": "aoci_update_entry",
        "arguments": args,
    })
    text = tool_text(r)
    proc.terminate()
    os.makedirs(os.path.join(WORK, "results"), exist_ok=True)
    name = os.path.basename(os.path.normpath(repo))
    ts = time.strftime("%Y%m%d_%H%M%S")
    path = os.path.join(WORK, "results", f"{name}_{ts}.json")
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
    try:
        res = json.loads(text)
        status = res.get("status") or res.get("result")
        print(f"[{name}] submit result: {status} -> {path}")
        if res.get("status") == "repair_required" or "Finding" in text:
            print(text[:4000])
    except json.JSONDecodeError:
        print(f"[{name}] non-JSON response -> {path}")
        print(text[:2000])


if __name__ == "__main__":
    mode = sys.argv[1]
    if mode == "--stage":
        for repo in sys.argv[2:]:
            stage(repo)
    elif mode == "--submit":
        submit(sys.argv[2], sys.argv[3])
    else:
        print(__doc__)
        sys.exit(2)

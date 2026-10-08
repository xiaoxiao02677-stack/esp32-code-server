#!/usr/bin/env python3
"""
Full-cycle authoring pipeline driver.

Usage:
  python aoci_pipeline.py next <repo-name>       # stage next batch (writes stage/<name>.json + <name>_paths.txt)
  python aoci_pipeline.py assemble <repo-name> <out-files...>   # merge authored outputs, validate, build payload
  python aoci_pipeline.py submit <repo-name> <payload.json>    # submit through MCP
"""
import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WORK = os.path.join(ROOT, ".workbuddy", "aoci")
AOCI = "D:/INSTALL/aoci/aoci.exe"
REPOS = {
    "code-server-mirror": "G:/demo/21_xiaozhi/code-server-mirror",
    "hermes-agent-main": "G:/demo/21_xiaozhi/hermes-agent-main",
}


def mcp_call(repo, tool, arguments, timeout=3600):
    proc = subprocess.Popen(
        [AOCI, "--repo", repo, "mcp"],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE,
        stderr=subprocess.PIPE, text=True, encoding="utf-8", bufsize=1,
    )
    import threading
    import time
    outbox = []
    threading.Thread(
        target=lambda: [outbox.append(json.loads(l))
                        for l in proc.stdout if l.strip()],
        daemon=True,
    ).start()

    def send(msg):
        proc.stdin.write(json.dumps(msg) + "\n")
        proc.stdin.flush()

    send({"jsonrpc": "2.0", "id": 1, "method": "initialize",
          "params": {"protocolVersion": "2024-11-05", "capabilities": {},
                     "clientInfo": {"name": "hermes-pipeline", "version": "1.0"}}})
    time.sleep(0.5)
    send({"jsonrpc": "2.0", "method": "notifications/initialized"})
    send({"jsonrpc": "2.0", "id": 2, "method": "tools/call",
          "params": {"name": tool, "arguments": arguments}})
    deadline = time.time() + timeout
    result = None
    while time.time() < deadline:
        for i, m in enumerate(outbox):
            if m.get("id") == 2:
                outbox.pop(i)
                result = m
                break
        if result:
            break
        time.sleep(0.05)
    proc.terminate()
    if not result:
        return {"error": "timeout"}
    content = result.get("result", {}).get("content", [])
    text = "".join(c.get("text", "") for c in content)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return {"_raw": text}


def next_batch(name):
    repo = REPOS[name]
    data = mcp_call(repo, "aoci_maintain", {})
    os.makedirs(os.path.join(WORK, "stage"), exist_ok=True)
    stage_path = os.path.join(WORK, "stage", name + ".json")
    with open(stage_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    ab = data.get("authoring_batch", {})
    cands = data.get("candidates", [])
    paths = [c["path"] for c in cands]
    with open(os.path.join(WORK, "stage", name + "_paths.txt"), "w", encoding="utf-8") as f:
        f.write("\n".join(paths))
    status = data.get("status")
    print(f"[{name}] status={status} included={len(cands)} "
          f"remaining={ab.get('remaining')} -> {stage_path}")
    if status == "stopped":
        print(f"[{name}] STOPPED next_action={data.get('next_action')}")
    return data


def submit(name, payload_path):
    repo = REPOS[name]
    with open(payload_path, encoding="utf-8") as f:
        payload = json.load(f)
    res = mcp_call(repo, "aoci_update_entry", payload)
    os.makedirs(os.path.join(WORK, "results"), exist_ok=True)
    out = os.path.join(WORK, "results",
                       f"{name}_{os.path.basename(payload_path)}")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(res, f, ensure_ascii=False, indent=1)
    status = res.get("status") or ("error" if "error" in res else "?")
    print(f"[{name}] submit status={status} -> {out}")
    if status not in ("applied", "ok") :
        print(json.dumps(res, ensure_ascii=False)[:3000])
    return res


if __name__ == "__main__":
    mode = sys.argv[1]
    if mode == "next":
        next_batch(sys.argv[2])
    elif mode == "submit":
        submit(sys.argv[2], sys.argv[3])
    else:
        print(__doc__)
        sys.exit(2)

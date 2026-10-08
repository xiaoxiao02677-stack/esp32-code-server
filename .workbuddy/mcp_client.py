#!/usr/bin/env python3
"""Minimal MCP stdio client for driving aoci mcp (JSON-RPC 2.0)."""
import json
import subprocess
import sys
import threading

REPO = sys.argv[1]
CMD = ["D:/INSTALL/aoci/aoci.exe", "--repo", REPO, "mcp"]

proc = subprocess.Popen(
    CMD, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
    stderr=subprocess.PIPE, text=True, encoding="utf-8", bufsize=1,
)


def send(msg):
    proc.stdin.write(json.dumps(msg) + "\n")
    proc.stdin.flush()


def reader(outbox):
    for line in proc.stdout:
        line = line.strip()
        if not line:
            continue
        try:
            outbox.append(json.loads(line))
        except json.JSONDecodeError:
            pass


outbox = []
threading.Thread(target=reader, args=(outbox,), daemon=True).start()

_id = 0


def call(method, params=None, timeout=600):
    global _id
    _id += 1
    rid = _id
    send({"jsonrpc": "2.0", "id": rid, "method": method, "params": params or {}})
    import time
    deadline = time.time() + timeout
    while time.time() < deadline:
        for i, m in enumerate(outbox):
            if m.get("id") == rid:
                outbox.pop(i)
                return m
        time.sleep(0.05)
    return {"error": "timeout", "id": rid}


# --- initialize handshake ---
r = call("initialize", {
    "protocolVersion": "2024-11-05",
    "capabilities": {},
    "clientInfo": {"name": "hermes-driver", "version": "1.0"},
})
print("== initialize ==")
print(json.dumps(r.get("result", r), ensure_ascii=False)[:2000])
send({"jsonrpc": "2.0", "method": "notifications/initialized"})

# --- tools/list ---
r = call("tools/list")
tools = r.get("result", {}).get("tools", [])
print("\n== tools ==")
for t in tools:
    print("-", t["name"], ":", t.get("description", "")[:100].replace("\n", " "))

# --- call tools named on the command line: toolname:json-args ---
import os
outdir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "mcp_out")
os.makedirs(outdir, exist_ok=True)
seq = 0
for arg in sys.argv[2:]:
    name, _, js = arg.partition(":")
    params = {"name": name, "arguments": json.loads(js) if js else {}}
    r = call("tools/call", params, timeout=3600)
    print(f"\n== {name} ==")
    content = r.get("result", {}).get("content", [])
    full = ""
    if content:
        for c in content:
            full += c.get("text", "")
    else:
        full = json.dumps(r, ensure_ascii=False)
    seq += 1
    path = os.path.join(outdir, f"{seq:03d}_{name}.txt")
    with open(path, "w", encoding="utf-8") as f:
        f.write(full)
    print(f"[saved {len(full)} chars -> {path}]")
    print(full[:1500])

proc.terminate()

#!/usr/bin/env python3
"""Dump full MCP tool schemas."""
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


outbox = []
threading.Thread(
    target=lambda: [outbox.append(json.loads(l)) for l in proc.stdout if l.strip()],
    daemon=True,
).start()

_id = 0


def call(method, params=None, timeout=300):
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
    return {"error": "timeout"}


call("initialize", {
    "protocolVersion": "2024-11-05", "capabilities": {},
    "clientInfo": {"name": "hermes-driver", "version": "1.0"},
})
send({"jsonrpc": "2.0", "method": "notifications/initialized"})
r = call("tools/list")
for t in r.get("result", {}).get("tools", []):
    print("=" * 20, t["name"], "=" * 20)
    print("DESC:", t.get("description", ""))
    print("SCHEMA:", json.dumps(t.get("inputSchema", {}), ensure_ascii=False, indent=1))
proc.terminate()

#!/usr/bin/env python3
"""On-server matrix test: find working config for clone voice S_HfQF5xwg2."""
import json
import subprocess
import sys

CFG = json.loads(subprocess.run(
    ["mysql", "-uroot", "-p123456", "xiaozhi_esp32_server", "-N", "-B",
     "-e", "select config_json from ai_model_config where id='TTS_DoubaoV3'"],
    capture_output=True, text=True).stdout.strip().splitlines()[-1])

SECRET = subprocess.run(
    ["mysql", "-uroot", "-p123456", "xiaozhi_esp32_server", "-N", "-B",
     "-e", "select param_value from sys_params where param_code='server.secret'"],
    capture_output=True, text=True).stdout.strip().splitlines()[-1]

print("cfg keys:", list(CFG.keys()))
print("has appid:", bool(CFG.get("appid")), "has access_token:", bool(CFG.get("access_token")), "has api_key:", bool(CFG.get("api_key")))

MATRIX = []
for res in ("seed-tts-2.0", "seed-icl-1.0", "volc.service_type.10029"):
    MATRIX.append({"resource_id": res, "keep_api_key": True})
    MATRIX.append({"resource_id": res, "keep_api_key": False})  # drop api_key -> use appid+access_token

import urllib.request
import urllib.error

for m in MATRIX:
    cfg = dict(CFG)
    cfg["resource_id"] = m["resource_id"]
    cfg["voice"] = "S_HfQF5xwg2"
    cfg["speaker"] = "S_HfQF5xwg2"
    if not m["keep_api_key"]:
        cfg.pop("api_key", None)
        cfg["access_token"] = None  # force appid+access_token path? we don't have token; skip
        # Actually doubao_v3 needs access_token for dual-header; we don't have one.
        # So only test dropping api_key if access_token exists
        if not CFG.get("access_token"):
            print(f"skip (no access_token): {m}")
            continue
    body = json.dumps(cfg).encode()
    req = urllib.request.Request(
        f"http://127.0.0.1:8003/api/tts/preview?voice=S_HfQF5xwg2&text=hello",
        data=body, method="POST",
        headers={"Authorization": f"Bearer {SECRET}", "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = resp.read()
            print(f"RES={m['resource_id']} key={'api' if m['keep_api_key'] else 'dual'}: HTTP {resp.status}, {len(data)} bytes, head={data[:8]!r}")
    except urllib.error.HTTPError as e:
        try:
            msg = json.loads(e.read())["msg"][:150]
        except Exception:
            msg = "?"
        print(f"RES={m['resource_id']} key={'api' if m['keep_api_key'] else 'dual'}: HTTP {e.code} {msg}")

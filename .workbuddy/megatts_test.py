#!/usr/bin/env python3
"""Test clone voice with volc.megatts.default resource (megaTTS 2.0 clone synthesis)."""
import json
import subprocess
import urllib.request
import urllib.error
import urllib.parse

CFG = json.loads(subprocess.run(
    ["mysql", "-uroot", "-p123456", "xiaozhi_esp32_server", "-N", "-B",
     "-e", "select config_json from ai_model_config where id='TTS_DoubaoV3'"],
    capture_output=True, text=True).stdout.strip().splitlines()[-1])

SECRET = subprocess.run(
    ["mysql", "-uroot", "-p123456", "xiaozhi_esp32_server", "-N", "-B",
     "-e", "select param_value from sys_params where param_code='server.secret'"],
    capture_output=True, text=True).stdout.strip().splitlines()[-1]

# megaTTS 2.0 clone: resource volc.megatts.default, dual-header auth (drop api_key)
cfg = dict(CFG)
cfg["resource_id"] = "volc.megatts.default"
cfg["voice"] = "S_HfQF5xwg2"
cfg["speaker"] = "S_HfQF5xwg2"
cfg.pop("api_key", None)

body = json.dumps(cfg).encode()
req = urllib.request.Request(
    "http://127.0.0.1:8003/api/tts/preview?voice=S_HfQF5xwg2&text=" + urllib.parse.quote("你好"),
    data=body, method="POST",
    headers={"Authorization": f"Bearer {SECRET}", "Content-Type": "application/json"})
try:
    with urllib.request.urlopen(req, timeout=60) as resp:
        data = resp.read()
        print(f"megatts+dual: HTTP {resp.status}, {len(data)} bytes, head={data[:8]!r}")
except urllib.error.HTTPError as e:
    try:
        msg = json.loads(e.read())["msg"]
    except Exception:
        msg = "?"
    print(f"megatts+dual: HTTP {e.code} {msg[:300]}")

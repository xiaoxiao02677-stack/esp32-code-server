#!/usr/bin/env python3
"""Verify seed-icl-2.0 resource works for clone voice S_N8pC5xwg2 (per user's working script)."""
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

# Per user's script: same api_key, resource_id=seed-icl-2.0, speaker=S_xxx, mp3/24000
cfg = dict(CFG)
cfg["resource_id"] = "seed-icl-2.0"
cfg["voice"] = "S_N8pC5xwg2"
cfg["speaker"] = "S_N8pC5xwg2"
cfg["format"] = "mp3"
cfg["sample_rate"] = 24000

body = json.dumps(cfg).encode()
req = urllib.request.Request(
    "http://127.0.0.1:8003/api/tts/preview?voice=S_N8pC5xwg2&text=" + urllib.parse.quote("你好啊，今天天气还不错哈。"),
    data=body, method="POST",
    headers={"Authorization": f"Bearer {SECRET}", "Content-Type": "application/json"})
try:
    with urllib.request.urlopen(req, timeout=60) as resp:
        data = resp.read()
        print(f"RESULT: HTTP 200, {len(data)} bytes, head={data[:4]!r}")
except urllib.error.HTTPError as e:
    try:
        msg = json.loads(e.read())["msg"]
    except Exception:
        msg = "?"
    print(f"FAIL: HTTP {e.code} | {msg[:300]}")

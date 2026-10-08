#!/usr/bin/env python3
"""Matrix test for user's custom clone voice S_N8pC5xwg2 under TTS_DoubaoV3."""
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

print("appid:", CFG.get("appid"))
print("resource_id:", CFG.get("resource_id"))
print()

TESTS = [
    ("user-clone S_N8pC5xwg2 + seed-tts-2.0 + api_key", {"voice": "S_N8pC5xwg2"}),
    ("user-clone S_N8pC5xwg2 + volc.megatts.default + api_key", {"voice": "S_N8pC5xwg2", "resource_id": "volc.megatts.default"}),
    ("user-clone S_N8pC5xwg2 + seed-icl-1.0 + api_key", {"voice": "S_N8pC5xwg2", "resource_id": "seed-icl-1.0"}),
    ("user-clone S_N8pC5xwg2 + megatts + dual-header", {"voice": "S_N8pC5xwg2", "resource_id": "volc.megatts.default", "drop_api_key": True}),
    ("old-clone S_HfQF5xwg2 + megatts + dual", {"voice": "S_HfQF5xwg2", "resource_id": "volc.megatts.default", "drop_api_key": True}),
    ("stock xiaohe (control)", {"voice": "zh_female_xiaohe_uranus_bigtts"}),
]

for name, patch in TESTS:
    cfg = dict(CFG)
    cfg["voice"] = patch["voice"]
    cfg["speaker"] = patch["voice"]
    if "resource_id" in patch:
        cfg["resource_id"] = patch["resource_id"]
    if patch.get("drop_api_key"):
        cfg.pop("api_key", None)
    body = json.dumps(cfg).encode()
    req = urllib.request.Request(
        "http://127.0.0.1:8003/api/tts/preview?voice=" + patch["voice"] + "&text=" + urllib.parse.quote("你好"),
        data=body, method="POST",
        headers={"Authorization": f"Bearer {SECRET}", "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = resp.read()
            print(f"PASS {name}: HTTP 200, {len(data)} bytes audio")
    except urllib.error.HTTPError as e:
        try:
            msg = json.loads(e.read())["msg"]
            msg = msg[:140]
        except Exception:
            msg = "?"
        print(f"FAIL {name}: HTTP {e.code} | {msg}")
    except Exception as e:
        print(f"FAIL {name}: {e}")

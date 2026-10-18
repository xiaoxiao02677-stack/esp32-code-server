#!/usr/bin/env python3
"""Check agent-models config push for device 14:c1:9f:d1:33:48 (TTS type present?)."""
import json
import subprocess

r = subprocess.run(
    ["python", "code/.workbuddy/ssh_run.py",
     'S1=$(mysql -N -uroot -p123456 xiaozhi_esp32_server -e "select param_value from sys_params where param_code=\'server.secret\'" 2>/dev/null | tail -1); '
     'curl -s -m 30 -X POST "http://127.0.0.1:8002/yuhe/config/agent-models" '
     '-H "Authorization: Bearer $S1" -H "Content-Type: application/json" '
     '-d \'{"macAddress":"14:c1:9f:d1:33:48","selectedModule":{}}\''],
    capture_output=True, text=True, encoding="utf-8", errors="replace",
    timeout=120, cwd="G:/demo/21_xiaozhi")
for line in r.stdout.splitlines():
    s = line.strip()
    if s.startswith('{"code"'):
        d = json.loads(s)
        data = d.get("data") or {}
        print("code:", d.get("code"))
        print("top keys:", list(data.keys()))
        tts = data.get("TTS") or {}
        print("TTS:", json.dumps({k: {kk: vv for kk, vv in v.items() if kk in ("type", "resource_id", "private_voice", "speaker")} for k, v in tts.items()}, ensure_ascii=False))
        sel = data.get("selected_module") or {}
        print("selected:", sel)
        break

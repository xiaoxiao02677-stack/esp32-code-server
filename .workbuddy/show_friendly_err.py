#!/usr/bin/env python3
"""Print full friendly error message for S_N8pC5xwg2."""
import json
import subprocess

r = subprocess.run(
    ["python", "code/.workbuddy/ssh_run.py",
     'SECRET=$(mysql -N -uroot -p123456 xiaozhi_esp32_server -e "select param_value from sys_params where param_code=\'server.secret\'" 2>/dev/null | tail -1); '
     'CFG=$(mysql -N -uroot -p123456 xiaozhi_esp32_server -e "select config_json from ai_model_config where id=\'TTS_DoubaoV3\'" 2>/dev/null | tail -1); '
     'curl -s -m 60 -X POST "http://127.0.0.1:8003/api/tts/preview?voice=S_N8pC5xwg2&text=hi" '
     '-H "Authorization: Bearer $SECRET" -H "Content-Type: application/json" -d "$CFG"'],
    capture_output=True, text=True, encoding="utf-8", errors="replace",
    timeout=120, cwd="G:/demo/21_xiaozhi")
for line in r.stdout.splitlines():
    s = line.strip()
    if s.startswith('{"code"'):
        print(json.loads(s)["msg"])
        break

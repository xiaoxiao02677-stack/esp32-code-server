#!/usr/bin/env python3
"""Check agent detail fields for simulator fix."""
import json
import subprocess

r = subprocess.run(
    ["python", "G:/demo/21_xiaozhi/code/.workbuddy/ssh_run.py",
     'TOKEN=$(MYSQL_PWD=123456 mysql -uroot xiaozhi_esp32_server -N -e "SELECT token FROM sys_user_token ORDER BY update_date DESC LIMIT 1"); '
     'curl -s "http://127.0.0.1:8002/yuhe/agent/a8b7726cf67f42fc8511a3a4ea82ca69" -H "Authorization: Bearer $TOKEN"'],
    capture_output=True, text=True, encoding="utf-8", errors="replace",
    timeout=120, cwd="G:/demo/21_xiaozhi")
for line in r.stdout.splitlines():
    line = line.strip()
    if line.startswith('{"code"'):
        d = json.loads(line)
        a = d.get("data") or {}
        for k in ("id", "agentName", "llmModelId", "ttsModelId",
                  "ttsVoiceId", "asrModelId", "memModelId", "systemPrompt"):
            v = a.get(k)
            if k == "systemPrompt" and v:
                v = v[:30] + "..."
            print(k, "=", v)
        break

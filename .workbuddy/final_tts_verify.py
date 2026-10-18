#!/usr/bin/env python3
"""Final verify: TTS via nginx full path, 3x (flaky-upstream check) + simulator E2E rerun."""
import json
import subprocess

ROOT = "G:/demo/21_xiaozhi"


def ssh(cmd, timeout=180):
    r = subprocess.run(
        ["python", f"{ROOT}/code/.workbuddy/ssh_run.py", cmd],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        timeout=timeout, cwd=ROOT)
    return r.stdout


# 3x TTS via nginx (browser path)
for i in range(3):
    out = ssh(
        'TOKEN=$(MYSQL_PWD=123456 mysql -uroot xiaozhi_esp32_server -N -e "SELECT token FROM sys_user_token ORDER BY update_date DESC LIMIT 1"); '
        'curl -s -m 90 -o /tmp/tts_check.bin -w "%{content_type} %{size_download} %{http_code}" '
        '"http://127.0.0.1:8001/yuhe/models/ttsPreview?modelId=TTS_QwenTTS_Flash&voice=Cherry&text=%E4%BD%A0%E5%A5%BD%E5%91%80%EF%BD%8C%E4%BB%8A%E5%A4%A9%E6%9C%89%E4%BB%80%E4%B9%88%E6%83%B3%E8%81%8A%E7%9A%84%E5%98%9B" '
        '-H "Authorization: Bearer $TOKEN"')
    line = [l for l in out.splitlines() if l.strip() and l.strip()[0] in "auh" or " " in l][-1] if out else ""
    ok = "audio" in line and "200" in line
    print(f"run{i+1}: {'PASS' if ok else 'FAIL'} | {line.strip()[:80]}")

print()
print("=== full simulator E2E rerun ===")
r = subprocess.run(["python", f"{ROOT}/.workbuddy/e2e_simulator.py"],
                   capture_output=True, text=True, encoding="utf-8", errors="replace",
                   timeout=600, cwd=ROOT)
print(r.stdout[-600:])

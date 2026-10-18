#!/usr/bin/env python3
"""Run on server: POST webm to asrRecognize, print result."""
import json
import subprocess
import urllib.request
import urllib.error

TOKEN = subprocess.run(
    ["mysql", "-uroot", "-p123456", "xiaozhi_esp32_server", "-N", "-B",
     "-e", "SELECT token FROM sys_user_token ORDER BY update_date DESC LIMIT 1"],
    capture_output=True, text=True).stdout.strip().splitlines()[-1]

with open("/tmp/asr_test.webm", "rb") as f:
    audio = f.read()
print("audio bytes:", len(audio))

req = urllib.request.Request(
    "http://127.0.0.1:8002/yuhe/models/asrRecognize?modelId=ASR_Qwen3Flash",
    data=audio, method="POST",
    headers={"Authorization": f"Bearer {TOKEN}", "Content-Type": "audio/webm"})
try:
    with urllib.request.urlopen(req, timeout=150) as resp:
        print("HTTP", resp.status)
        print(resp.read().decode("utf-8")[:500])
except urllib.error.HTTPError as e:
    print("HTTP", e.code)
    print(e.read().decode("utf-8")[:500])

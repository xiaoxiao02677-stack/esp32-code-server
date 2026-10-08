#!/usr/bin/env python3
"""E2E: server-side ASR recognize — generate speech (edge-tts style via ffmpeg sine? no —
use Python TTS preview endpoint to synthesize a WAV, then feed it to /api/asr/recognize)."""
import json
import subprocess
import urllib.request
import urllib.error
import urllib.parse

API = "http://127.0.0.1:8002/xiaozhi"


def ssh(cmd, timeout=240):
    r = subprocess.run(["python", "code/.workbuddy/ssh_run.py", cmd],
                       capture_output=True, text=True, encoding="utf-8", errors="replace",
                       timeout=timeout, cwd="G:/demo/21_xiaozhi")
    return r.stdout


def get_token():
    out = ssh('TOKEN=$(MYSQL_PWD=123456 mysql -uroot xiaozhi_esp32_server -N -e "SELECT token FROM sys_user_token ORDER BY update_date DESC LIMIT 1"); echo "TK$TOKEN"')
    for line in out.splitlines():
        if line.startswith("TK"):
            return line[2:].strip()
    return ""


token = get_token()
assert token
print("token ok")

# 1. synthesize a speech WAV via TTS preview (DoubaoV3 stock voice)
out = ssh(
    f'TOKEN={token}; curl -s -m 60 -o /tmp/asr_test.wav -w "%{{http_code}} %{{content_type}} %{{size_download}}" '
    f'"{API}/models/ttsPreview?modelId=TTS_DoubaoV3&voice=zh_female_xiaohe_uranus_bigtts&text=%E4%BD%A0%E5%A5%BD%E5%91%80%E4%BB%8A%E5%A4%A9%E5%A4%A9%E6%B0%94%E6%80%8E%E4%B9%88%E6%A0%B7" '
    '-H "Authorization: Bearer $TOKEN"')
line = [l for l in out.splitlines() if l.strip() and l.strip()[0].isdigit()][-1]
print("1. synth speech:", line.strip())
assert "audio" in line, "synth failed"

# 2. convert WAV -> webm/opus (simulate browser MediaRecorder output)
out = ssh('ffmpeg -y -i /tmp/asr_test.wav -c:a libopus -b:a 32k /tmp/asr_test.webm 2>&1 | tail -1; ls -la /tmp/asr_test.webm | awk \'{print "webm size:", $5}\'')
print("2. convert to webm:", " ".join(out.split()[-4:]))

# 3. POST to /models/asrRecognize (the exact browser path, via nginx too)
out = ssh(
    f'TOKEN={token}; curl -s -m 90 -X POST '
    f'"http://127.0.0.1:8001/xiaozhi/models/asrRecognize?modelId=ASR_Qwen3Flash" '
    '-H "Authorization: Bearer $TOKEN" -H "Content-Type: audio/webm" '
    '--data-binary @/tmp/asr_test.webm')
for line in out.splitlines():
    s = line.strip()
    if s.startswith('{"code"'):
        d = json.loads(s)
        print("3. ASR result:", json.dumps(d, ensure_ascii=False))
        break

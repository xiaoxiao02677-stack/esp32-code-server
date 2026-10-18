#!/usr/bin/env python3
"""E2E part2: voice CRUD by DB id."""
import json
import subprocess

ROOT = "G:/demo/21_xiaozhi"
API = "http://127.0.0.1:8002/yuhe"
VID = "2107854015092224001"


def ssh(cmd, timeout=180):
    r = subprocess.run(
        ["python", f"{ROOT}/code/.workbuddy/ssh_run.py", cmd],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        timeout=timeout, cwd=ROOT)
    return r.stdout


def api(path, method="GET", body=None):
    jbody = json.dumps(body, ensure_ascii=False) if body is not None else ""
    cmd = (
        'TOKEN=$(MYSQL_PWD=123456 mysql -uroot xiaozhi_esp32_server -N -e '
        '"SELECT token FROM sys_user_token ORDER BY update_date DESC LIMIT 1"); '
        f'curl -s -m 60 -X {method} "{API}{path}" -H "Authorization: Bearer $TOKEN"'
    )
    if body is not None:
        cmd += f" -H 'Content-Type: application/json' -d '{jbody}'"
    out = ssh(cmd)
    for line in out.splitlines():
        line = line.strip()
        if line.startswith('{"code"'):
            try:
                return json.loads(line)
            except json.JSONDecodeError:
                pass
    return None


# 4. preview custom voice (real synthesis)
out = ssh(
    'TOKEN=$(MYSQL_PWD=123456 mysql -uroot xiaozhi_esp32_server -N -e "SELECT token FROM sys_user_token ORDER BY update_date DESC LIMIT 1"); '
    f'curl -s -m 60 -o /tmp/qa_voice.bin -w "%{{content_type}} %{{size_download}}" '
    f'"{API}/models/ttsPreview?modelId=TTS_DoubaoV3&voice=zh_female_xiaohe_uranus_bigtts&text=%E4%BD%A0%E5%A5%BD" '
    '-H "Authorization: Bearer $TOKEN"')
line = [l for l in out.splitlines() if "audio" in l or "json" in l]
print(f"4. preview custom voice: {line[-1].strip() if line else '?'}")

# 5. update
r = api(f"/ttsVoice/{VID}", "PUT", {
    "name": "QA-自定义音色-改名", "ttsVoice": "zh_female_xiaohe_uranus_bigtts",
    "ttsModelId": "TTS_DoubaoV3", "languages": "普通话", "sort": 98,
    "voiceInstruction": "语速放慢一点", "voiceDemo": "",
})
print(f"5. update: code={r.get('code')} msg={r.get('msg')}")

# 5b. confirm update in DB
out = ssh(f'mysql -uroot -p123456 xiaozhi_esp32_server -N -e "select name, voice_instruction from ai_tts_voice where id=\'{VID}\'" 2>/dev/null | tail -1')
print(f"5b. DB after update: {out.strip()}")

# 6. delete
r = api("/ttsVoice/delete", "POST", [VID])
print(f"6. delete: code={r.get('code')} msg={r.get('msg')}")

# 7. confirm gone
out = ssh(f'mysql -uroot -p123456 xiaozhi_esp32_server -N -e "select count(*) from ai_tts_voice where id=\'{VID}\'" 2>/dev/null | tail -1')
print(f"7. DB after delete: count={out.strip()}")

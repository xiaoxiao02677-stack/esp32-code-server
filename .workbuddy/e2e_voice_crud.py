#!/usr/bin/env python3
"""E2E: voice CRUD via real API (simulate user adding a custom voice)."""
import json
import subprocess
import urllib.parse

ROOT = "G:/demo/21_xiaozhi"
API = "http://127.0.0.1:8002/xiaozhi"


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


# 1. list voices of DoubaoV3
r = api("/ttsVoice?ttsModelId=TTS_DoubaoV3&page=1&limit=5")
vlist = ((r or {}).get("data") or {}).get("list") or []
print(f"1. list voices: {len(vlist)} (code={r.get('code')})")

# 2. create custom voice (use a known-good stock voice code)
r = api("/ttsVoice", "POST", {
    "name": "QA-自定义音色-小何温柔版", "ttsVoice": "zh_female_xiaohe_uranus_bigtts",
    "ttsModelId": "TTS_DoubaoV3", "languages": "普通话", "sort": 99,
    "voiceInstruction": "", "voiceDemo": "",
})
print(f"2. create: code={r.get('code')} msg={r.get('msg')}")

# 3. find it in list
r = api("/ttsVoice?ttsModelId=TTS_DoubaoV3&page=1&limit=100&name=QA-自定义")
hits = ((r or {}).get("data") or {}).get("list") or []
vid = hits[0]["id"] if hits else None
print(f"3. find created: id={vid} name={hits[0]['name'] if hits else None}")

# 4. preview it (audio synthesis with the custom voice)
if vid:
    out = ssh(
        'TOKEN=$(MYSQL_PWD=123456 mysql -uroot xiaozhi_esp32_server -N -e "SELECT token FROM sys_user_token ORDER BY update_date DESC LIMIT 1"); '
        f'curl -s -m 60 -o /tmp/qa_voice.bin -w "%{{content_type}} %{{size_download}}" '
        f'"{API}/models/ttsPreview?modelId=TTS_DoubaoV3&voice=zh_female_xiaohe_uranus_bigtts&text=%E4%BD%A0%E5%A5%BD" '
        '-H "Authorization: Bearer $TOKEN"')
    line = [l for l in out.splitlines() if "audio" in l or "json" in l]
    print(f"4. preview custom voice: {line[-1].strip() if line else '?'}")

    # 5. update it
    r = api(f"/ttsVoice/{vid}", "PUT", {
        "name": "QA-自定义音色-改名", "ttsVoice": "zh_female_xiaohe_uranus_bigtts",
        "ttsModelId": "TTS_DoubaoV3", "languages": "普通话", "sort": 98,
        "voiceInstruction": "语速放慢一点", "voiceDemo": "",
    })
    print(f"5. update: code={r.get('code')} msg={r.get('msg')}")

    # 6. delete it
    r = api("/ttsVoice/delete", "POST", [vid])
    print(f"6. delete: code={r.get('code')} msg={r.get('msg')}")

    # 7. confirm gone
    r = api("/ttsVoice?ttsModelId=TTS_DoubaoV3&page=1&limit=100&name=QA-自定义")
    hits = ((r or {}).get("data") or {}).get("list") or []
    print(f"7. confirm deleted: {'PASS' if not hits else 'FAIL (still there)'}")

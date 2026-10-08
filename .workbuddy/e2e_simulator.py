#!/usr/bin/env python3
"""E2E: simulate the cc-console simulator pipeline exactly as the frontend does.

Steps (mirror runSimPipeline):
1. GET /agent/{id}            -> llmModelId, ttsModelId, ttsVoiceId, systemPrompt
2. GET /models/llmPreview     -> reply text
3. GET /models/{ttsModelId}/voices -> find ttsVoice code by ttsVoiceId
4. GET /models/ttsPreview     -> audio bytes (must be > 200 bytes)
All with the real session token via Java (8002), i.e. the exact browser path.
"""
import json
import subprocess

API = "http://127.0.0.1:8002/xiaozhi"
AGENT_ID = "a8b7726cf67f42fc8511a3a4ea82ca69"


def ssh(cmd):
    r = subprocess.run(
        ["python", "G:/demo/21_xiaozhi/code/.workbuddy/ssh_run.py", cmd],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        timeout=180, cwd="G:/demo/21_xiaozhi")
    return r.stdout


def one_line_json(out):
    for line in out.splitlines():
        line = line.strip()
        if line.startswith('{"code"'):
            return json.loads(line)
    return None


# token
out = ssh('TOKEN=$(MYSQL_PWD=123456 mysql -uroot xiaozhi_esp32_server -N -e "SELECT token FROM sys_user_token ORDER BY update_date DESC LIMIT 1"); echo "TOKENIS$TOKEN"')
token = ""
for line in out.splitlines():
    if line.startswith("TOKENIS"):
        token = line[len("TOKENIS"):].strip()
        break
assert token, "no token"
print("token ok:", token[:8] + "...")

# 1. agent detail
out = ssh(f'TOKEN={token}; curl -s "{API}/agent/{AGENT_ID}" -H "Authorization: Bearer $TOKEN"')
detail = one_line_json(out)
assert detail and detail.get("code") == 0, out[:200]
agent = detail["data"]
llm_id = agent["llmModelId"]
tts_id = agent["ttsModelId"]
voice_id = agent["ttsVoiceId"]
prompt = agent.get("systemPrompt") or ""
print(f"step1 agent detail: llm={llm_id} tts={tts_id} voice={voice_id}")

# 2. LLM preview
text = "你好，请用一句话介绍你自己"
out = ssh(f'TOKEN={token}; curl -s "{API}/models/llmPreview?modelId={llm_id}&text={subprocess.list2cmdline([text]) if False else __import__("urllib.parse", fromlist=["quote"]).quote(text)}&systemPrompt={__import__("urllib.parse", fromlist=["quote"]).quote(prompt[:500])}" -H "Authorization: Bearer $TOKEN"')
llm = one_line_json(out)
assert llm and llm.get("code") == 0 and (llm.get("data") or {}).get("reply"), out[:300]
reply = llm["data"]["reply"]
print(f"step2 LLM reply ({llm['data']['elapsed_ms']}ms): {reply[:60]}")

# 3. voice code lookup
out = ssh(f'TOKEN={token}; curl -s "{API}/models/{tts_id}/voices" -H "Authorization: Bearer $TOKEN"')
voices = one_line_json(out)
vlist = (voices or {}).get("data") or []
hit = next((v for v in vlist if v.get("id") == voice_id), None)
voice_code = (hit or {}).get("ttsVoice") or voice_id
print(f"step3 voice code: {voice_id} -> {voice_code}")

# 4. TTS preview
tts_text = reply[:60]
import urllib.parse
out = ssh(f'TOKEN={token}; curl -s -o /tmp/sim_tts.bin -w "%{{http_code}} %{{size_download}}" "{API}/models/ttsPreview?modelId={tts_id}&voice={urllib.parse.quote(voice_code)}&text={urllib.parse.quote(tts_text)}" -H "Authorization: Bearer $TOKEN"')
line = [l for l in out.splitlines() if l.strip() and l.strip()[0].isdigit()][-1] if out else ""
parts = line.split()
status, size = (parts[0], int(parts[1])) if len(parts) >= 2 else ("?", 0)
assert status == "200" and size > 200, f"tts failed: {line}"
print(f"step4 TTS audio: HTTP {status}, {size} bytes")

print()
print("E2E SIMULATOR PIPELINE: ALL PASS ✓")

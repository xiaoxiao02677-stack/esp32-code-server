#!/usr/bin/env python3
"""Verify template-based agent creation uses the SELECTED template, not the default (巫医)."""
import json
import subprocess

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


# 1. get template id for 好奇男孩
r = api("/agent/template/page?page=1&limit=100")
tpls = (r or {}).get("data", {}).get("list") or []
tpl = next((t for t in tpls if t.get("agentName") == "好奇男孩"), None)
assert tpl, f"template not found: {[t.get('agentName') for t in tpls]}"
print(f"template: {tpl['agentName']} id={tpl['id']}")
print(f"  template prompt head: {(tpl.get('systemPrompt') or '')[:40]!r}")

# 2. create agent from this template
r = api("/agent", "POST", {"agentName": "QA-模板创建-好奇男孩", "templateId": tpl["id"]})
new_id = (r or {}).get("data")
assert r and r.get("code") == 0 and new_id, json.dumps(r, ensure_ascii=False)[:200]
print(f"created agent id={new_id}")

# 3. fetch detail and check systemPrompt
r = api(f"/agent/{new_id}")
d = (r or {}).get("data") or {}
prompt = d.get("systemPrompt") or ""
print(f"agent prompt head: {prompt[:40]!r}")
ok = "小男孩" in prompt or "好奇" in prompt[:60]
print("PROMPT FROM SELECTED TEMPLATE:", "PASS" if ok else "FAIL (still 巫医?)")

# 4. cleanup test agent
r = api(f"/agent/{new_id}", "DELETE")
print("cleanup delete:", (r or {}).get("code") == 0 and "PASS" or "FAIL", (r or {}).get("msg", ""))

print()
print("ALL DONE", "✓" if ok else "✗")

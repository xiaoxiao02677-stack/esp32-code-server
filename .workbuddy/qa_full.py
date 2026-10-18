#!/usr/bin/env python3
"""QA: 模拟用户走 cc-console 全部新功能的 API 链路（一次跑完）。"""
import json
import subprocess
import urllib.parse

ROOT = "G:/demo/21_xiaozhi"
API = "http://127.0.0.1:8002/yuhe"
AGENT_ID = "a8b7726cf67f42fc8511a3a4ea82ca69"

results = []


def ssh(cmd, timeout=180):
    r = subprocess.run(
        ["python", f"{ROOT}/code/.workbuddy/ssh_run.py", cmd],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        timeout=timeout, cwd=ROOT)
    return r.stdout


def api(path, method="GET", body=None, timeout=180):
    """Call API with real session token, return parsed json (or None)."""
    jbody = json.dumps(body, ensure_ascii=False) if body is not None else ""
    cmd = (
        'TOKEN=$(MYSQL_PWD=123456 mysql -uroot xiaozhi_esp32_server -N -e '
        '"SELECT token FROM sys_user_token ORDER BY update_date DESC LIMIT 1"); '
        f'curl -s -m 60 -X {method} "{API}{path}" '
        f'-H "Authorization: Bearer $TOKEN" '
    )
    if body is not None:
        cmd += f" -H 'Content-Type: application/json' -d '{jbody}' "
    out = ssh(cmd, timeout)
    for line in out.splitlines():
        line = line.strip()
        if line.startswith('{"code"'):
            try:
                return json.loads(line)
            except json.JSONDecodeError:
                pass
    return None


def check(name, cond, detail=""):
    results.append((name, bool(cond)))
    print(("PASS " if cond else "FAIL ") + name + (f" | {detail[:100]}" if detail else ""))


# ── 1. 模型一键测试（LLM + TTS 真实调用） ──
r = api(f"/models/modelTest?modelId=LLM_DeepSeek&modelType=LLM")
check("1a 模型一键测试-LLM", r and r.get("code") == 0 and (r.get("data") or {}).get("ok") is True,
      ((r or {}).get("data") or {}).get("message", ""))

r = api(f"/models/modelTest?modelId=TTS_QwenTTS_Flash&modelType=TTS")
check("1b 模型一键测试-TTS", r and r.get("code") == 0 and (r.get("data") or {}).get("ok") is True,
      ((r or {}).get("data") or {}).get("message", ""))

# ── 2. 模型列表（TTS/LLM/ASR 三类） ──
for t in ("TTS", "LLM", "ASR"):
    r = api(f"/models/list?modelType={t}&page=1&limit=10")
    n = len(((r or {}).get("data") or {}).get("list") or [])
    check(f"2 模型列表-{t}", r and r.get("code") == 0 and n > 0, f"{n} 个")

# ── 3. 供应器列表 ──
r = api("/models/LLM/provideTypes")
n = len((r or {}).get("data") or [])
check("3 供应器列表-LLM", r and r.get("code") == 0 and n > 0, f"{n} 个供应器")

# ── 4. 自定义模型：新增→编辑→删除 全生命周期 ──
create_body = {
    "modelName": "QA测试-自定义接口", "isDefault": 0, "isEnabled": 1,
    "configJson": {"type": "openai", "api_key": "test-key",
                   "base_url": "http://127.0.0.1:9/v1", "model_name": "test"},
}
r = api("/models/LLM/custom", "POST", create_body)
new_id = ((r or {}).get("data") or {}).get("id") if isinstance(r.get("data"), dict) else (r.get("data") if r else None)
check("4a 新增自定义模型", r and r.get("code") == 0 and new_id, f"id={new_id}")

if new_id:
    create_body["modelName"] = "QA测试-改名"
    r = api(f"/models/LLM/custom/{new_id}", "PUT", create_body)
    check("4b 编辑自定义模型", r and r.get("code") == 0, "")

    r = api(f"/models/{new_id}", "DELETE")
    check("4c 删除自定义模型", r and r.get("code") == 0, "")
    # DB 确认删除
    out = ssh(f'mysql -uroot -p123456 xiaozhi_esp32_server -N -e "select count(*) from ai_model_config where id=\'{new_id}\';" 2>/dev/null | tail -1')
    gone = out.strip().splitlines()[-1].strip() == "0" if out.strip() else False
    check("4d DB确认已删", gone, out.strip().splitlines()[-1] if out.strip() else "?")

# ── 5. MCP 一键测试 ──
r = api(f"/agent/mcp/test/{AGENT_ID}")
d = (r or {}).get("data") or {}
check("5 MCP一键测试", r and r.get("code") == 0 and "ok" in d,
      f"ok={d.get('ok')} msg={str(d.get('message'))[:60]}")

# ── 6. 链路模拟器-LLM 阶段（Java 代理路径） ──
r = api(f"/models/llmPreview?modelId=LLM_DeepSeek&text={urllib.parse.quote('回复：正常')}")
reply = ((r or {}).get("data") or {}).get("reply") or ""
check("6 链路模拟器-LLM", r and r.get("code") == 0 and reply, reply[:50])

# ── 7. 设备绑定-非法码被拒（不 500） ──
r = api("/device/bind/000000", "POST")
check("7 设备绑定-非法码拒绝", r is not None and r.get("code") != 0,
      f"code={r.get('code') if r else 'None'} msg={str(r.get('msg'))[:50] if r else ''}")

# ── 8. 记忆列表 ──
r = api("/memory/agents")
agents = (r or {}).get("data") or []
check("8a 记忆-智能体列表", r and r.get("code") == 0, f"{len(agents)} 个")
if agents:
    aid = agents[0].get("agent_id") or agents[0].get("agentId")
    r = api(f"/memory/facts?agent_id={aid}&page=1&size=5")
    n = len(((r or {}).get("data") or {}).get("list") or [])
    check("8b 记忆-事实列表", r and r.get("code") == 0, f"{n} 条")

# ── 9. 模板列表（7 个种子） ──
r = api("/agent/template/page?page=1&limit=100")
n = len(((r or {}).get("data") or {}).get("list") or [])
check("9 模板列表", r and r.get("code") == 0 and n > 0, f"{n} 个模板")

# ── 10. 智能体详情（链路模拟器依赖） ──
r = api(f"/agent/{AGENT_ID}")
d = (r or {}).get("data") or {}
check("10 智能体详情-模型ID字段", bool(d.get("llmModelId")) and bool(d.get("ttsModelId")),
      f"llm={d.get('llmModelId')} tts={d.get('ttsModelId')}")

print()
passed = sum(1 for _, ok in results if ok)
print(f"===== QA RESULT: {passed}/{len(results)} PASS =====")
fails = [n for n, ok in results if not ok]
if fails:
    print("FAILED:", fails)

#!/usr/bin/env python3
"""E2E verification for cc-console PRD features (R1/R2/R3).

Logs in via the real login flow (SM2 + captcha needs manual token...),
so instead: use the direct captcha-bypass debug token if available, else
prompt. Simpler: we login by reusing the known demo account flow used in
test_java_api.sh (needs captcha). For automated smoke we use Python
internal endpoints via server-side curl (loopback) where possible, plus
unauthenticated checks (401 vs 404 tells us routing is live).
"""
import subprocess
import sys

ROOT = "G:/demo/21_xiaozhi"


def ssh(cmd, timeout=120):
    r = subprocess.run(
        ["python", f"{ROOT}/code/.workbuddy/ssh_run.py", cmd],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        timeout=timeout, cwd=ROOT)
    return r.stdout


checks = []


def check(name, cond, detail=""):
    checks.append((name, bool(cond), detail))
    print(("PASS " if cond else "FAIL ") + name + (" | " + detail if detail else ""))


# 1. Python /api/llm/preview routing + auth gate (401 expected without token)
out = ssh("curl -s -o /dev/null -w '%{http_code}' -X POST http://127.0.0.1:8003/api/llm/preview")
check("R2 llm preview endpoint live (401 unauth)", "401" in out, out.strip())

# 2. with server.secret it should reach the handler (400 missing text)
out = ssh("SECRET=$(mysql -N -uroot -p123456 xiaozhi_esp32_server -e \"select param_value from sys_params where param_code='server.secret'\" 2>/dev/null | tail -1); "
          "curl -s -w '\\nHTTP=%{http_code}' -X POST -H \"Authorization: Bearer $SECRET\" http://127.0.0.1:8003/api/llm/preview -H 'Content-Type: application/json' -d '{\"type\":\"openai\"}'")
check("R2 llm preview auth+validation (400 text required)", "400" in out, out.strip().replace("\n", " ")[:120])

# 3. Java /xiaozhi/models/llmPreview routing (401 business code without login)
out = ssh("curl -s 'http://127.0.0.1:8002/xiaozhi/models/llmPreview?modelId=x&text=hi'")
check("R2 llmPreview proxy route live (code:401 unauth)", '"code":401' in out, out.strip()[:80])

# 4. Java session-delete route live (401 business code without login)
out = ssh("curl -s -X DELETE 'http://127.0.0.1:8002/xiaozhi/agent/abc/chat-history/sid'")
check("R3 chat session delete route live (code:401 unauth)", '"code":401' in out, out.strip()[:80])

# 5. MCP read routes live
out = ssh("curl -s -o /dev/null -w '%{http_code}' 'http://127.0.0.1:8002/xiaozhi/agent/mcp/address/abc'")
check("R1 mcp address route live", ("401" in out or "200" in out), out.strip())

# 5. web bundle deployed (fix: strip the echoed command noise)
out = ssh("curl -s http://127.0.0.1:8001/cc/ | grep -o 'index-[A-Za-z0-9_-]*\\.js' | head -1")
bundle = [seg for seg in out.split() if seg.startswith("index-") and seg.endswith(".js")]
bundle = bundle[0] if bundle else ""
check("R4 web bundle deployed", bool(bundle), bundle)

# 7. device update route exists (401 business code)
out = ssh("curl -s -X PUT -H 'Content-Type: application/json' -d '{\"alias\":\"t\"}' 'http://127.0.0.1:8002/xiaozhi/device/update/xxx'")
check("R3 device update route live (code:401 unauth)", '"code":401' in out, out.strip()[:80])

# 8. otaMag upload route exists (401/400 business code without file)
out = ssh("curl -s -X POST 'http://127.0.0.1:8002/xiaozhi/otaMag/upload'")
check("R3 ota upload route live", ('"code":401' in out or '"code":400' in out), out.strip()[:80])

print()
passed = sum(1 for _, ok, _ in checks if ok)
print(f"RESULT: {passed}/{len(checks)} passed")
sys.exit(0 if passed == len(checks) else 1)

#!/usr/bin/env python3
"""E2E verification round 2: user's 5 issues."""
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
    print(("PASS " if cond else "FAIL ") + name + (" | " + detail[:110] if detail else ""))


# 1. Python /api/model/test routing + auth gate
out = ssh("curl -s -o /dev/null -w '%{http_code}' -X POST 'http://127.0.0.1:8003/api/model/test?type=TTS'")
check("Q3 python /api/model/test live (401 unauth)", "401" in out, out.strip())

# 2. Python /api/model/test with secret: 400 missing body
out = ssh("SECRET=$(mysql -N -uroot -p123456 xiaozhi_esp32_server -e \"select param_value from sys_params where param_code='server.secret'\" 2>/dev/null | tail -1); "
          "curl -s -w '\\nHTTP=%{http_code}' -X POST -H \"Authorization: Bearer $SECRET\" 'http://127.0.0.1:8003/api/model/test?type=TTS' -H 'Content-Type: application/json' -d '{}'")
check("Q3 python model test auth+validation (400)", "400" in out, out.strip().replace("\n", " ")[:110])

# 3. Java /models/modelTest route
out = ssh("curl -s 'http://127.0.0.1:8002/yuhe/models/modelTest?modelId=x&modelType=TTS'")
check("Q3 java modelTest route (code:401 unauth)", '"code":401' in out, out.strip()[:90])

# 4. Java MCP test route
out = ssh("curl -s 'http://127.0.0.1:8002/yuhe/agent/mcp/test/abc'")
check("Q5 java mcp test route (code:401 unauth)", '"code":401' in out, out.strip()[:90])

# 5. device bind routes (bind by code + manual-add)
out = ssh("curl -s -X POST 'http://127.0.0.1:8002/yuhe/device/bind/abc/123456'; echo; curl -s -X POST -H 'Content-Type: application/json' -d '{}' 'http://127.0.0.1:8002/yuhe/device/manual-add'")
check("Q1 device bind + manual-add routes (code:401)", '"code":401' in out, out.strip().replace("\n", " ")[:110])

# 6. web bundle live
out = ssh("curl -s http://127.0.0.1:8001/cc/ | grep -o 'index-[A-Za-z0-9_-]*\\.js' | head -1")
bundle = [s for s in out.split() if s.startswith("index-") and s.endswith(".js")]
check("Q2/Q4 web bundle live", bool(bundle), bundle[0] if bundle else out[:60])

# 7. all services active
out = ssh("systemctl is-active yuhe-server xiaozhi-manager-api nginx")
check("all services active", out.count("active") >= 3, out.strip().replace("\n", " "))

print()
passed = sum(1 for _, ok, _ in checks if ok)
print(f"RESULT: {passed}/{len(checks)} passed")
sys.exit(0 if passed == len(checks) else 1)

#!/usr/bin/env bash
# =============================================================================
# test_internal_api.sh — xiaozhi-server 内部记忆管理 API 复验（部署后 #7 复用）
# 验收对应：A2 管理页 CRUD（服务端侧）、A3 搜索筛选、A7 审核流、A9 数据链路
#
# 端点：http://{HOST}:{PORT}/api/memory/**（默认 127.0.0.1:8003）
# 鉴权：Authorization: Bearer {server.secret}（= manager-api.secret，两端共享）
#
# ⚠️ loopback 限制说明：http_server.py 的 memory_loopback_middleware 只放行
#    127.0.0.1 / ::1。本脚本必须【在服务器本机】执行（ssh_run.py 到
#    sandyun.top 后运行本脚本），从外网/局域网直连 8003 会先收到
#    403 {"code":403,"msg":"禁止访问"}。manager-api 与 xiaozhi-server 同机部署，
#    经 127.0.0.1 互调，故部署后从本机 curl 即为真实生产路径。
#
# 鉴权三态（脚本内置）：
#   1) 无 Authorization 头      -> 预期 HTTP 401 {"code":401}
#   2) 错误 key（Bearer wrong） -> 预期 HTTP 401 {"code":401}
#   3) 正确 key                 -> 预期 HTTP 200 {"code":0}
#
# 用法：
#   AUTH_KEY=xxxx bash test_internal_api.sh              # 手动传共享密钥
#   AUTH_KEY=xxxx HOST=127.0.0.1 PORT=8003 bash test_internal_api.sh
#   AUTH_KEY=xxxx AGENT_ID=03532a34... bash test_internal_api.sh  # 指定 Agent
#
# 退出码：0=全部通过；1=存在失败项
# =============================================================================
set -u

HOST="${HOST:-127.0.0.1}"
PORT="${PORT:-8003}"
AUTH_KEY="${AUTH_KEY:-}"
AGENT_ID="${AGENT_ID:-qa-memory-test-agent}"   # 脚本专用测试 Agent，避免污染试点 demo 数据
BASE="http://${HOST}:${PORT}/api/memory"
PASS=0; FAIL=0; FAILED_NAMES=""

if [ -z "$AUTH_KEY" ]; then
  echo "[FATAL] 请通过环境变量 AUTH_KEY 传入共享密钥（server.secret / manager-api.secret）"
  echo "        例如: AUTH_KEY=\$(ssh 服务器 grep secret xiaozhi-server/data/.config.yaml) bash $0"
  exit 2
fi

# ---- 工具函数 -----------------------------------------------------------------
hdr_auth="Authorization: Bearer ${AUTH_KEY}"

# check <名称> <预期HTTP码> <实际HTTP码> <响应体>
check() {
  local name="$1" want="$2" got="$3" body="$4"
  if [ "$want" = "$got" ]; then
    PASS=$((PASS+1)); echo "  [PASS] ${name} (HTTP ${got})"
  else
    FAIL=$((FAIL+1)); FAILED_NAMES="${FAILED_NAMES}|${name}"
    echo "  [FAIL] ${name} 期望 HTTP ${want} 实得 ${got}: $(echo "$body" | head -c 200)"
  fi
}

# code0 <名称> <响应体>：code=0 且 data 存在即通过
code0() {
  local name="$1" body="$2" code
  code=$(echo "$body" | python3 -c "import sys,json;print(json.load(sys.stdin).get('code'))" 2>/dev/null)
  if [ "$code" = "0" ]; then
    PASS=$((PASS+1)); echo "  [PASS] ${name} (code=0)"
  else
    FAIL=$((FAIL+1)); FAILED_NAMES="${FAILED_NAMES}|${name}"
    echo "  [FAIL] ${name} code=${code}: $(echo "$body" | head -c 200)"
  fi
}

echo "== 目标: ${BASE}  (Agent: ${AGENT_ID}) =="
echo "== 前置检查: 8003 从本机可达 =="
curl -s -o /dev/null -w "   health http_code=%{http_code}\n" --max-time 5 "${BASE}/agents" || true

echo ""
echo "== T0 鉴权三态（GET /api/memory/agents）=="
body=$(curl -s -w '\n%{http_code}' --max-time 10 "${BASE}/agents"); code=${body##*$'\n'}; body=${body%$'\n'*}
check "T0-1 无 Authorization 头 -> 401" 401 "$code" "$body"
body=$(curl -s -w '\n%{http_code}' --max-time 10 -H "Authorization: Bearer wrong-key" "${BASE}/agents"); code=${body##*$'\n'}; body=${body%$'\n'*}
check "T0-2 错误 key -> 401" 401 "$code" "$body"
body=$(curl -s -w '\n%{http_code}' --max-time 10 -H "$hdr_auth" "${BASE}/agents"); code=${body##*$'\n'}; body=${body%$'\n'*}
check "T0-3 正确 key -> 200" 200 "$code" "$body"
code0 "T0-4 agents 响应 code=0 且 data 为数组" "$body"

echo ""
echo "== T1 写入测试数据（POST /api/memory/{agent}/facts）=="
body=$(curl -s -w '\n%{http_code}' --max-time 10 -X POST -H "$hdr_auth" -H "Content-Type: application/json" \
  -d "{\"content\":\"QA测试：${AGENT_ID} 喜欢听粤语歌\",\"category\":\"preference\",\"tags\":\"qa,music\",\"trust_score\":0.5}" \
  "${BASE}/${AGENT_ID}/facts"); code=${body##*$'\n'}; body=${body%$'\n'*}
check "T1-1 新增记忆 -> 200" 200 "$code" "$body"
FACT_ID=$(echo "$body" | python3 -c "import sys,json;print(json.load(sys.stdin)['data']['fact_id'])" 2>/dev/null)
echo "   fact_id=${FACT_ID}"

body=$(curl -s -w '\n%{http_code}' --max-time 10 -X POST -H "$hdr_auth" -H "Content-Type: application/json" \
  -d "{\"content\":\"QA测试：${AGENT_ID} 喜欢听粤语歌\",\"category\":\"preference\"}" \
  "${BASE}/${AGENT_ID}/facts"); code=${body##*$'\n'}; body=${body%$'\n'*}
check "T1-2 重复 content 幂等 -> 200" 200 "$code" "$body"
FACT_ID2=$(echo "$body" | python3 -c "import sys,json;print(json.load(sys.stdin)['data']['fact_id'])" 2>/dev/null)
if [ -n "$FACT_ID" ] && [ "$FACT_ID" = "$FACT_ID2" ]; then
  PASS=$((PASS+1)); echo "  [PASS] T1-3 幂等返回同一 fact_id=${FACT_ID}"
else
  FAIL=$((FAIL+1)); FAILED_NAMES="${FAILED_NAMES}|T1-3"; echo "  [FAIL] T1-3 幂等返回不同 id: ${FACT_ID} vs ${FACT_ID2}"
fi

body=$(curl -s -w '\n%{http_code}' --max-time 10 -X POST -H "$hdr_auth" -H "Content-Type: application/json" \
  -d '{"content":""}' "${BASE}/${AGENT_ID}/facts"); code=${body##*$'\n'}; body=${body%$'\n'*}
check "T1-4 空 content -> 400" 400 "$code" "$body"

body=$(curl -s -w '\n%{http_code}' --max-time 10 -X POST -H "$hdr_auth" -H "Content-Type: application/json" \
  -d '{"content":"路径穿越测试"}' "${BASE}/..%2Fetc%2Fpasswd/facts"); code=${body##*$'\n'}; body=${body%$'\n'*}
if [ "$code" = "400" ] || [ "$code" = "401" ] || [ "$code" = "404" ] || [ "$code" = "403" ]; then
  PASS=$((PASS+1)); echo "  [PASS] T1-5 非法 agent_id（路径穿越）被拒绝 (HTTP ${code})"
else
  FAIL=$((FAIL+1)); FAILED_NAMES="${FAILED_NAMES}|T1-5"; echo "  [FAIL] T1-5 非法 agent_id 未拦截: HTTP ${code}"
fi

echo ""
echo "== T2 列表 / 详情 / 筛选（GET facts）=="
body=$(curl -s -w '\n%{http_code}' --max-time 10 -H "$hdr_auth" "${BASE}/${AGENT_ID}/facts?page=1&size=20"); code=${body##*$'\n'}; body=${body%$'\n'*}
check "T2-1 列表 -> 200" 200 "$code" "$body"
code0 "T2-2 列表 code=0 且含 total/items" "$body"

body=$(curl -s -w '\n%{http_code}' --max-time 10 -H "$hdr_auth" "${BASE}/${AGENT_ID}/facts?keyword=粤语歌"); code=${body##*$'\n'}; body=${body%$'\n'*}
check "T2-3 关键词搜索（中文 FTS）-> 200" 200 "$code" "$body"
total=$(echo "$body" | python3 -c "import sys,json;print(json.load(sys.stdin)['data']['total'])" 2>/dev/null)
if [ "$total" -ge 1 ] 2>/dev/null; then PASS=$((PASS+1)); echo "  [PASS] T2-4 关键词命中 ${total} 条"; else FAIL=$((FAIL+1)); FAILED_NAMES="${FAILED_NAMES}|T2-4"; echo "  [FAIL] T2-4 关键词未命中 total=${total}"; fi

body=$(curl -s -w '\n%{http_code}' --max-time 10 -H "$hdr_auth" "${BASE}/${AGENT_ID}/facts?category=preference"); code=${body##*$'\n'}; body=${body%$'\n'*}
check "T2-5 类型筛选 -> 200" 200 "$code" "$body"

body=$(curl -s -w '\n%{http_code}' --max-time 10 -H "$hdr_auth" "${BASE}/${AGENT_ID}/facts?trust_min=0&trust_max=0.3"); code=${body##*$'\n'}; body=${body%$'\n'*}
check "T2-6 信任分区间筛选 -> 200" 200 "$code" "$body"

body=$(curl -s -w '\n%{http_code}' --max-time 10 -H "$hdr_auth" "${BASE}/${AGENT_ID}/facts/${FACT_ID}"); code=${body##*$'\n'}; body=${body%$'\n'*}
check "T2-7 详情 -> 200" 200 "$code" "$body"
code0 "T2-8 详情 code=0 且含 entities" "$body"

body=$(curl -s -w '\n%{http_code}' --max-time 10 -H "$hdr_auth" "${BASE}/${AGENT_ID}/facts/99999999"); code=${body##*$'\n'}; body=${body%$'\n'*}
check "T2-9 不存在的 fact_id -> 404" 404 "$code" "$body"

echo ""
echo "== T3 编辑（PUT）=="
body=$(curl -s -w '\n%{http_code}' --max-time 10 -X PUT -H "$hdr_auth" -H "Content-Type: application/json" \
  -d "{\"content\":\"QA测试：${AGENT_ID} 最喜欢陈奕迅的粤语歌\",\"category\":\"preference\"}" \
  "${BASE}/${AGENT_ID}/facts/${FACT_ID}"); code=${body##*$'\n'}; body=${body%$'\n'*}
check "T3-1 编辑内容（触发实体重抽取）-> 200" 200 "$code" "$body"
code0 "T3-2 编辑后 code=0" "$body"
ent=$(echo "$body" | python3 -c "import sys,json;print(json.load(sys.stdin)['data']['entities'])" 2>/dev/null)
echo "   entities=${ent}"

body=$(curl -s -w '\n%{http_code}' --max-time 10 -X PUT -H "$hdr_auth" -H "Content-Type: application/json" \
  -d '{"trust_score":0.1}' "${BASE}/${AGENT_ID}/facts/${FACT_ID}"); code=${body##*$'\n'}; body=${body%$'\n'*}
check "T3-3 调低信任分 -> 200" 200 "$code" "$body"
code0 "T3-4 信任分更新 code=0" "$body"

echo ""
echo "== T4 反馈（POST feedback）——信任分 ± =="
body=$(curl -s -w '\n%{http_code}' --max-time 10 -X POST -H "$hdr_auth" -H "Content-Type: application/json" \
  -d '{"helpful":true}' "${BASE}/${AGENT_ID}/facts/${FACT_ID}/feedback"); code=${body##*$'\n'}; body=${body%$'\n'*}
check "T4-1 有用反馈 -> 200" 200 "$code" "$body"
newt=$(echo "$body" | python3 -c "import sys,json;print(json.load(sys.stdin)['data']['new_trust'])" 2>/dev/null)
if [ "$newt" = "0.15" ] 2>/dev/null; then PASS=$((PASS+1)); echo "  [PASS] T4-2 0.10 + 0.05 = ${newt}"; else FAIL=$((FAIL+1)); FAILED_NAMES="${FAILED_NAMES}|T4-2"; echo "  [FAIL] T4-2 信任分 0.1+0.05 期望 0.15 实得 ${newt}"; fi

body=$(curl -s -w '\n%{http_code}' --max-time 10 -X POST -H "$hdr_auth" -H "Content-Type: application/json" \
  -d '{"helpful":false}' "${BASE}/${AGENT_ID}/facts/${FACT_ID}/feedback"); code=${body##*$'\n'}; body=${body%$'\n'*}
check "T4-3 无用反馈 -> 200" 200 "$code" "$body"
newt=$(echo "$body" | python3 -c "import sys,json;print(json.load(sys.stdin)['data']['new_trust'])" 2>/dev/null)
if [ "$newt" = "0.05" ] 2>/dev/null; then PASS=$((PASS+1)); echo "  [PASS] T4-4 0.15 - 0.10 = ${newt}（低于检索阈值 0.3，进入待审语义）"; else FAIL=$((FAIL+1)); FAILED_NAMES="${FAILED_NAMES}|T4-4"; echo "  [FAIL] T4-4 信任分 0.15-0.10 期望 0.05 实得 ${newt}"; fi

echo ""
echo "== T5 审核（POST review，P1 接口预演）=="
body=$(curl -s -w '\n%{http_code}' --max-time 10 -X POST -H "$hdr_auth" -H "Content-Type: application/json" \
  -d '{"action":"reject"}' "${BASE}/${AGENT_ID}/facts/${FACT_ID}/review"); code=${body##*$'\n'}; body=${body%$'\n'*}
check "T5-1 驳回 -> 200" 200 "$code" "$body"
st=$(echo "$body" | python3 -c "import sys,json;print(json.load(sys.stdin)['data']['status'])" 2>/dev/null)
if [ "$st" = "rejected" ]; then PASS=$((PASS+1)); echo "  [PASS] T5-2 status=rejected"; else FAIL=$((FAIL+1)); FAILED_NAMES="${FAILED_NAMES}|T5-2"; echo "  [FAIL] T5-2 status=${st}"; fi

body=$(curl -s -w '\n%{http_code}' --max-time 10 -H "$hdr_auth" "${BASE}/${AGENT_ID}/facts?status=rejected"); code=${body##*$'\n'}; body=${body%$'\n'*}
check "T5-3 已驳回筛选可查 -> 200" 200 "$code" "$body"
code0 "T5-4 已驳回筛选 code=0" "$body"

body=$(curl -s -w '\n%{http_code}' --max-time 10 -X POST -H "$hdr_auth" -H "Content-Type: application/json" \
  -d '{"action":"approve"}' "${BASE}/${AGENT_ID}/facts/${FACT_ID}/review"); code=${body##*$'\n'}; body=${body%$'\n'*}
check "T5-5 恢复（approve）-> 200" 200 "$code" "$body"
st=$(echo "$body" | python3 -c "import sys,json;print(json.load(sys.stdin)['data']['status'])" 2>/dev/null)
tr=$(echo "$body" | python3 -c "import sys,json;print(json.load(sys.stdin)['data']['trust_score'])" 2>/dev/null)
if [ "$st" = "active" ] && [ "$tr" = "0.5" ] 2>/dev/null; then PASS=$((PASS+1)); echo "  [PASS] T5-6 approve -> status=active 且 trust=0.5（恢复默认可信水位）"; else FAIL=$((FAIL+1)); FAILED_NAMES="${FAILED_NAMES}|T5-6"; echo "  [FAIL] T5-6 approve 后 status=${st} trust=${tr}"; fi

body=$(curl -s -w '\n%{http_code}' --max-time 10 -X POST -H "$hdr_auth" -H "Content-Type: application/json" \
  -d '{"action":"bogus"}' "${BASE}/${AGENT_ID}/facts/${FACT_ID}/review"); code=${body##*$'\n'}; body=${body%$'\n'*}
check "T5-7 非法 action -> 400" 400 "$code" "$body"

echo ""
echo "== T6 删除（DELETE）=="
body=$(curl -s -w '\n%{http_code}' --max-time 10 -X DELETE -H "$hdr_auth" "${BASE}/${AGENT_ID}/facts/${FACT_ID}"); code=${body##*$'\n'}; body=${body%$'\n'*}
check "T6-1 删除 -> 200" 200 "$code" "$body"
code0 "T6-2 删除响应 code=0 且 removed=true" "$body"

body=$(curl -s -w '\n%{http_code}' --max-time 10 -H "$hdr_auth" "${BASE}/${AGENT_ID}/facts/${FACT_ID}"); code=${body##*$'\n'}; body=${body%$'\n'*}
check "T6-3 删除后再查 -> 404" 404 "$code" "$body"

echo ""
echo "== T7 agents 扫描（部署后应含试点 demo Agent 库文件）=="
body=$(curl -s -w '\n%{http_code}' --max-time 10 -H "$hdr_auth" "${BASE}/agents"); code=${body##*$'\n'}; body=${body%$'\n'*}
check "T7-1 agents -> 200" 200 "$code" "$body"
echo "   agents=$(echo "$body" | head -c 500)"

echo ""
echo "==== RESULT: ${PASS} passed, ${FAIL} failed ===="
if [ "$FAIL" -gt 0 ]; then
  echo "Failed:${FAILED_NAMES}"
  exit 1
fi
exit 0

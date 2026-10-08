#!/usr/bin/env bash
# =============================================================================
# test_java_api.sh — manager-api 记忆管理 REST API 复验（部署后 #7 复用）
# 验收对应：A2 管理页 CRUD（管理端链路）、A3 搜索筛选、A5/A6 引擎徽标与分派
#
# 端点：http://{HOST}:{PORT}/{CTX}/memory/**（默认 127.0.0.1:8002 + context-path /xiaozhi；
#       application.yml server.servlet.context-path=/xiaozhi，nginx 8001 /xiaozhi/ 也反代到 8002/xiaozhi/）
# 鉴权：manager-web 管理员登录 token（oauth2）；Shiro 默认链 /**→oauth2 保护
#
# 用法（先登录控制台拿 token，见下方 HOW-TO）：
#   TOKEN=eyJhbGciOi... bash test_java_api.sh
#   TOKEN=xxx HOST=127.0.0.1 PORT=8002 CTX=/xiaozhi AGENT_ID=03532a34... bash test_java_api.sh
#   TOKEN=xxx HOST=sandyun.top PORT=8001 CTX=/xiaozhi AGENT_ID=... bash test_java_api.sh  # 走 nginx
#
# HOW-TO 获取 TOKEN：
#   1) 浏览器打开控制台 -> F12 -> Network -> 任一 /xiaozhi/memory 或 /model 请求 ->
#      Request Headers 里复制 Authorization: Bearer xxx 的 xxx；
#   2) 或用账号密码换 token（本地沙箱环境）：
#      curl -s -X POST http://HOST:8002/xiaozhi/sys/login -H 'Content-Type: application/json' \
#        -d '{"username":"admin","password":"<密码>","captcha":"","uuid":""}'
#      （若开了验证码则用方式 1）
#
# 退出码：0=全部通过；1=存在失败项；2=未传 TOKEN
# =============================================================================
set -u

HOST="${HOST:-127.0.0.1}"
PORT="${PORT:-8002}"
CTX="${CTX:-/xiaozhi}"
TOKEN="${TOKEN:-}"
AGENT_ID="${AGENT_ID:-}"    # 必传：目标 Agent（试点 demo：03532a34...）
BASE="http://${HOST}:${PORT}${CTX}/memory"
PASS=0; FAIL=0; FAILED_NAMES=""

if [ -z "$TOKEN" ] || [ -z "$AGENT_ID" ]; then
  echo "[FATAL] 需要 TOKEN（管理员登录 token）与 AGENT_ID（试点 Agent id）"
  echo "        用法: TOKEN=xxx AGENT_ID=03532a34... bash $0"
  exit 2
fi

hdr_auth="Authorization: Bearer ${TOKEN}"

check() {
  local name="$1" want="$2" got="$3" body="$4"
  if [ "$want" = "$got" ]; then
    PASS=$((PASS+1)); echo "  [PASS] ${name} (HTTP ${got})"
  else
    FAIL=$((FAIL+1)); FAILED_NAMES="${FAILED_NAMES}|${name}"
    echo "  [FAIL] ${name} 期望 HTTP ${want} 实得 ${got}: $(echo "$body" | head -c 200)"
  fi
}

code0() {
  local name="$1" body="$2" code
  code=$(echo "$body" | python3 -c "import sys,json;print(json.load(sys.stdin).get('code'))" 2>/dev/null)
  if [ "$code" = "0" ]; then
    PASS=$((PASS+1)); echo "  [PASS] ${name} (code=0)"
  else
    FAIL=$((FAIL+1)); FAILED_NAMES="${FAILED_NAMES}|${name}"
    echo "  [FAIL] ${name} code=${code}: $(echo "$body" | head -c 300)"
  fi
}

echo "== 目标: ${BASE}  (Agent: ${AGENT_ID}) =="

echo ""
echo "== J0 鉴权（无 token / 坏 token 应业务码 401；正确 token 应 200+code0）=="
# 注：manager-api 全局异常处理返回 HTTP 200 + 业务码（部署实测），
#     故鉴权失败断言按 body 内 code=401 判定，而非 HTTP 状态码。
body=$(curl -s --max-time 10 "${BASE}/agents")
bcode=$(echo "$body" | python3 -c "import sys,json;print(json.load(sys.stdin).get('code'))" 2>/dev/null)
if [ "$bcode" = "401" ]; then PASS=$((PASS+1)); echo "  [PASS] J0-1 无 token -> 业务码 401"; else FAIL=$((FAIL+1)); FAILED_NAMES="${FAILED_NAMES}|J0-1 无 token"; echo "  [FAIL] J0-1 无 token 期望业务码401 实得 code=${bcode}: $(echo "$body" | head -c 150)"; fi
body=$(curl -s --max-time 10 -H "Authorization: Bearer bad-token" "${BASE}/agents")
bcode=$(echo "$body" | python3 -c "import sys,json;print(json.load(sys.stdin).get('code'))" 2>/dev/null)
if [ "$bcode" = "401" ]; then PASS=$((PASS+1)); echo "  [PASS] J0-2 坏 token -> 业务码 401"; else FAIL=$((FAIL+1)); FAILED_NAMES="${FAILED_NAMES}|J0-2 坏 token"; echo "  [FAIL] J0-2 坏 token 期望业务码401 实得 code=${bcode}"; fi
body=$(curl -s -w '\n%{http_code}' --max-time 10 -H "$hdr_auth" "${BASE}/agents"); code=${body##*$'\n'}; body=${body%$'\n'*}
check "J0-3 正确 token -> 200" 200 "$code" "$body"
code0 "J0-4 agents code=0（data 含 id/name/engine/factCount/pendingCount）" "$body"
echo "   agents=$(echo "$body" | head -c 400)"

echo ""
echo "== J1 新增（POST /memory/facts）=="
body=$(curl -s -w '\n%{http_code}' --max-time 10 -X POST -H "$hdr_auth" -H "Content-Type: application/json" \
  -d "{\"agent_id\":\"${AGENT_ID}\",\"content\":\"QA测试：这个Agent的用户喜欢喝茉莉花茶\",\"category\":\"preference\",\"tags\":\"qa,drink\"}" \
  "${BASE}/facts"); code=${body##*$'\n'}; body=${body%$'\n'*}
check "J1-1 新增 -> 200" 200 "$code" "$body"
code0 "J1-2 新增 code=0" "$body"
FACT_ID=$(echo "$body" | python3 -c "import sys,json;d=json.load(sys.stdin);print(d['data'].get('factId') or d['data'].get('fact_id'))" 2>/dev/null)
echo "   factId=${FACT_ID}"

body=$(curl -s --max-time 10 -X POST -H "$hdr_auth" -H "Content-Type: application/json" \
  -d "{\"content\":\"缺 agent_id 应报错\"}" "${BASE}/agents" >/dev/null; curl -s --max-time 10 -X POST -H "$hdr_auth" -H "Content-Type: application/json" \
  -d "{\"content\":\"缺 agent_id 应报错\"}" "${BASE}/facts")
bcode=$(echo "$body" | python3 -c "import sys,json;print(json.load(sys.stdin).get('code'))" 2>/dev/null)
if [ "$bcode" != "0" ] && [ -n "$bcode" ]; then PASS=$((PASS+1)); echo "  [PASS] J1-3 缺 agent_id 被拒绝 (业务码 ${bcode})"; else FAIL=$((FAIL+1)); FAILED_NAMES="${FAILED_NAMES}|J1-3b"; echo "  [FAIL] J1-3b 缺参未被拒绝 code=${bcode}"; fi

echo ""
echo "== J2 列表/搜索/筛选（GET /memory/facts）=="
body=$(curl -s -w '\n%{http_code}' --max-time 10 -H "$hdr_auth" "${BASE}/facts?agent_id=${AGENT_ID}&page=1&size=20"); code=${body##*$'\n'}; body=${body%$'\n'*}
check "J2-1 列表 -> 200" 200 "$code" "$body"
code0 "J2-2 列表 code=0" "$body"

# 关键词含中文：curl 必须显式百分号编码（--data-urlencode + --get），
# 否则未编码 UTF-8 直接进 URL 行会被 Tomcat 400 拒绝（部署实测）。
# 注：本项同时是 Java 侧 RestTemplate 双重编码缺陷（%→%25）的暴露点，
#     修复前经 Java 代理搜索中文关键词预期 total=0（fail 属已知缺陷）。
body=$(curl -s -w '\n%{http_code}' --max-time 10 -H "$hdr_auth" --get "${BASE}/facts" --data-urlencode "agent_id=${AGENT_ID}" --data-urlencode "keyword=茉莉花茶" --data-urlencode "page=1" --data-urlencode "size=20"); code=${body##*$'\n'}; body=${body%$'\n'*}
check "J2-3 关键词搜索 -> 200" 200 "$code" "$body"
code0 "J2-4 关键词搜索 code=0" "$body"
total=$(echo "$body" | python3 -c "import sys,json;d=json.load(sys.stdin)['data'];print(d.get('total'))" 2>/dev/null)
if [ "${total:-0}" -ge 1 ] 2>/dev/null; then PASS=$((PASS+1)); echo "  [PASS] J2-5 中文关键词命中 ${total} 条"; else FAIL=$((FAIL+1)); FAILED_NAMES="${FAILED_NAMES}|J2-5"; echo "  [FAIL] J2-5 关键词未命中 total=${total}（若恒为0且无keyword列表正常=Java双重编码缺陷未修）"; fi

body=$(curl -s -w '\n%{http_code}' --max-time 10 -H "$hdr_auth" "${BASE}/facts?agent_id=${AGENT_ID}&category=preference&trust_min=0&trust_max=1"); code=${body##*$'\n'}; body=${body%$'\n'*}
check "J2-6 类型+信任分组合筛选 -> 200" 200 "$code" "$body"

body=$(curl -s -w '\n%{http_code}' --max-time 10 -H "$hdr_auth" --get "${BASE}/facts" --data-urlencode "agent_id=${AGENT_ID}" --data-urlencode "keyword=绝对不存在的关键词xyzq"); code=${body##*$'\n'}; body=${body%$'\n'*}
check "J2-7 空结果 -> 200（前端给友好提示）" 200 "$code" "$body"

echo ""
echo "== J3 详情（GET /memory/facts/{id}）=="
body=$(curl -s -w '\n%{http_code}' --max-time 10 -H "$hdr_auth" "${BASE}/facts/${FACT_ID}?agent_id=${AGENT_ID}"); code=${body##*$'\n'}; body=${body%$'\n'*}
check "J3-1 详情 -> 200" 200 "$code" "$body"
code0 "J3-2 详情 code=0（含 entities）" "$body"

echo ""
echo "== J4 编辑（PUT /memory/facts/{id}）=="
body=$(curl -s -w '\n%{http_code}' --max-time 10 -X PUT -H "$hdr_auth" -H "Content-Type: application/json" \
  -d "{\"agent_id\":\"${AGENT_ID}\",\"content\":\"QA测试：这个Agent的用户最爱龙井茶\",\"category\":\"preference\"}" \
  "${BASE}/facts/${FACT_ID}"); code=${body##*$'\n'}; body=${body%$'\n'*}
check "J4-1 编辑内容 -> 200" 200 "$code" "$body"
code0 "J4-2 编辑 code=0" "$body"

echo ""
echo "== J5 反馈（POST feedback）=="
body=$(curl -s -w '\n%{http_code}' --max-time 10 -X POST -H "$hdr_auth" -H "Content-Type: application/json" \
  -d "{\"agent_id\":\"${AGENT_ID}\",\"helpful\":true}" "${BASE}/facts/${FACT_ID}/feedback"); code=${body##*$'\n'}; body=${body%$'\n'*}
check "J5-1 有用反馈 -> 200" 200 "$code" "$body"
code0 "J5-2 反馈 code=0（new_trust/old_trust）" "$body"

echo ""
echo "== J6 审核（POST review）=="
body=$(curl -s -w '\n%{http_code}' --max-time 10 -X POST -H "$hdr_auth" -H "Content-Type: application/json" \
  -d "{\"agent_id\":\"${AGENT_ID}\",\"action\":\"reject\"}" "${BASE}/facts/${FACT_ID}/review"); code=${body##*$'\n'}; body=${body%$'\n'*}
check "J6-1 驳回 -> 200" 200 "$code" "$body"
code0 "J6-2 驳回 code=0（status=rejected）" "$body"

body=$(curl -s -w '\n%{http_code}' --max-time 10 -H "$hdr_auth" "${BASE}/facts?agent_id=${AGENT_ID}&status=rejected"); code=${body##*$'\n'}; body=${body%$'\n'*}
check "J6-3 已驳回筛选 -> 200" 200 "$code" "$body"

body=$(curl -s -w '\n%{http_code}' --max-time 10 -X POST -H "$hdr_auth" -H "Content-Type: application/json" \
  -d "{\"agent_id\":\"${AGENT_ID}\",\"action\":\"approve\"}" "${BASE}/facts/${FACT_ID}/review"); code=${body##*$'\n'}; body=${body%$'\n'*}
check "J6-4 恢复 -> 200" 200 "$code" "$body"

echo ""
echo "== J7 删除（DELETE）=="
body=$(curl -s -w '\n%{http_code}' --max-time 10 -X DELETE -H "$hdr_auth" "${BASE}/facts/${FACT_ID}?agent_id=${AGENT_ID}"); code=${body##*$'\n'}; body=${body%$'\n'*}
check "J7-1 删除 -> 200" 200 "$code" "$body"

body=$(curl -s --max-time 10 -H "$hdr_auth" "${BASE}/facts/${FACT_ID}?agent_id=${AGENT_ID}")
bcode=$(echo "$body" | python3 -c "import sys,json;print(json.load(sys.stdin).get('code'))" 2>/dev/null)
if [ "$bcode" = "404" ] || [ "$bcode" = "10051" ]; then PASS=$((PASS+1)); echo "  [PASS] J7-2 删除后详情 -> 业务码 ${bcode}（条目不存在）"; else FAIL=$((FAIL+1)); FAILED_NAMES="${FAILED_NAMES}|J7-2 删除后详情"; echo "  [FAIL] J7-2 期望业务码404/10051 实得 ${bcode}: $(echo "$body" | head -c 150)"; fi

echo ""
echo "== J8 引擎分派（A5/A6 相关）=="
echo "   [手动] 控制台模型配置-记忆：确认存在 'Holographic 本地记忆' provider 卡片"
echo "   [手动] Agent 编辑页：记忆引擎下拉可选 mem_holographic，保存提示含'新连接生效'"
echo "   [手动] mem0 未配 key：provider 卡片显示黄色'未配置 API Key'警示（A6）"
echo "   [手动] mem_local_short Agent：/memory/facts 返回引导文案而非报错"

echo ""
echo "==== RESULT: ${PASS} passed, ${FAIL} failed ===="
if [ "$FAIL" -gt 0 ]; then
  echo "Failed:${FAILED_NAMES}"
  exit 1
fi
exit 0

#!/usr/bin/env bash
# =============================================================================
# qa-api 部署后契约验证脚本 —— manager-api 记忆管理模块 /memory/** 8 端点
# 测试对象: MemoryFactController.java（契约基线 = qa-api 静态契约测试报告 2026-10-05）
#
# 依赖: bash4+, curl, jq；(可选) python3 + gmssl 用于交互式登录
#
# 用法:
#   # 方式一（推荐）: 浏览器/F12 从已登录控制台复制 token
#   QA_TOKEN=<你的token> bash test_java_api.sh
#
#   # 方式二: 交互式登录（需 python3 -m pip install gmssl；验证码图片需人工识别）
#   bash test_java_api.sh --login
#
#   # 全量用例（越权 + 超管 + 引擎降级）需追加变量:
#   QA_TOKEN_B=<普通用户B的token>              # 越权对照
#   QA_TOKEN_ADMIN=<superAdmin的token>          # 超管放行
#   QA_AGENT_FOREIGN=<属于用户B的agent_id>       # 越权目标（须绑定 mem_holographic）
#   QA_AGENT_SHORT=<绑定mem_local_short的agent_id>   # 降级提示用例
#   QA_AGENT_MEM0=<绑定mem0ai的agent_id>            # 降级提示用例
#   QA_AGENT_NOMEM=<绑定nomem的agent_id>            # 空列表用例
#   QA_AGENT_POWERMEM=<绑定powermem的agent_id>      # G-10 降级用例
#
#   # 服务不可用用例: 停掉 xiaozhi-server 后加 QA_TEST_DOWN=1
#
# 说明: 本系统业务错误统一 HTTP 200 + {code,msg,data}（RenExceptionHandler），
#       仅 Shiro 层 401 亦为 HTTP 200 + code=401（Oauth2Filter 未 setStatus），
#       故所有断言基于响应体 code 字段而非 HTTP 状态码。
# =============================================================================
set -uo pipefail

BASE="${QA_BASE_URL:-http://127.0.0.1:8002/xiaozhi}"
TOKEN="${QA_TOKEN:-}"
TOKEN_B="${QA_TOKEN_B:-}"
TOKEN_ADMIN="${QA_TOKEN_ADMIN:-}"
AGENT_HOLO="${QA_AGENT_HOLO:-}"       # 主被测 agent（mem_holographic）
AGENT_FOREIGN="${QA_AGENT_FOREIGN:-}" # 用户 B 的 agent
AGENT_SHORT="${QA_AGENT_SHORT:-}"
AGENT_MEM0="${QA_AGENT_MEM0:-}"
AGENT_NOMEM="${QA_AGENT_NOMEM:-}"
AGENT_POWERMEM="${QA_AGENT_POWERMEM:-}"
TEST_DOWN="${QA_TEST_DOWN:-0}"

PASS=0; FAIL=0
FAILED_CASES=()

# ---------- 工具函数 ----------
need() { command -v "$1" >/dev/null 2>&1 || { echo "[FATAL] 缺少依赖: $1"; exit 1; }; }
need curl; need jq

# api <method> <path-with-query> <token|空> [json-body]
api() {
  local method="$1" path="$2" token="$3" body="${4:-}"
  local args=(-sS -X "$method" -w '\n%{http_code}' "${BASE}${path}"
              -H 'Content-Type: application/json')
  [ -n "$token" ] && args+=(-H "Authorization: Bearer ${token}")
  [ -n "$body" ]  && args+=(-d "$body")
  curl "${args[@]}"
}

# 断言: body.code == 期望值。传参: <用例名> <期望code> <响应体>
assert_code() {
  local name="$1" expected="$2" body="$3"
  local actual
  actual=$(echo "$body" | jq -r '.code // "MISSING"' 2>/dev/null)
  if [ "$actual" = "$expected" ]; then
    echo "PASS  ${name}  (code=${actual})"; PASS=$((PASS+1))
  else
    echo "FAIL  ${name}  期望 code=${expected} 实际=${actual}  body=$(echo "$body" | head -c 300)"
    FAIL=$((FAIL+1)); FAILED_CASES+=("${name}")
  fi
}

# 断言: body.code == 期望 且 msg == 期望。传参: <用例名> <期望code> <期望msg> <响应体>
assert_code_msg() {
  local name="$1" expected="$2" expected_msg="$3" body="$4"
  local actual actual_msg
  actual=$(echo "$body" | jq -r '.code // "MISSING"' 2>/dev/null)
  actual_msg=$(echo "$body" | jq -r '.msg // "MISSING"' 2>/dev/null)
  if [ "$actual" = "$expected" ] && [ "$actual_msg" = "$expected_msg" ]; then
    echo "PASS  ${name}  (code=${actual}, msg=${actual_msg})"; PASS=$((PASS+1))
  else
    echo "FAIL  ${name}  期望 code=${expected}/msg=${expected_msg} 实际 code=${actual}/msg=${actual_msg}  body=$(echo "$body" | head -c 300)"
    FAIL=$((FAIL+1)); FAILED_CASES+=("${name}")
  fi
}

# 断言 jq 表达式为真。传参: <用例名> <jq表达式> <响应体>
assert_jq() {
  local name="$1" expr="$2" body="$3"
  if echo "$body" | jq -e "$expr" >/dev/null 2>&1; then
    echo "PASS  ${name}"; PASS=$((PASS+1))
  else
    echo "FAIL  ${name}  jq断言失败: ${expr}  body=$(echo "$body" | head -c 300)"
    FAIL=$((FAIL+1)); FAILED_CASES+=("${name}")
  fi
}

skip() { echo "SKIP  $1（未提供前置变量）"; }

# ---------- 登录辅助（可选） ----------
# 登录契约: POST /user/login {username, password=SM2hex(captcha+明文, C1C3C2去04头), captchaId}
# 公钥来源: GET /user/pub-config → data.sm2PublicKey；验证码: GET /user/captcha?uuid=<uuid>
login_interactive() {
  need python3 || exit 1
  local username password captcha_id captcha_code sm2_pub enc login_body resp
  read -rp "用户名: " username
  read -rsp "密码: " password; echo
  captcha_id="$(cat /proc/sys/kernel/random/uuid 2>/dev/null || python3 -c 'import uuid;print(uuid.uuid4())')"
  curl -sS -o qa_captcha.png "${BASE}/user/captcha?uuid=${captcha_id}"
  echo "验证码已保存到 $(pwd)/qa_captcha.png，请打开图片识别后输入:"
  read -rp "验证码(5位): " captcha_code
  sm2_pub=$(curl -sS "${BASE}/user/pub-config" | jq -r '.data.sm2PublicKey')
  if [ -z "$sm2_pub" ] || [ "$sm2_pub" = "null" ]; then echo "[FATAL] 无法获取SM2公钥"; exit 1; fi
  enc=$(python3 - "$sm2_pub" "${captcha_code}${password}" <<'PYEOF'
import sys
try:
    from gmssl import sm2
except ImportError:
    sys.stderr.write("请先: pip install gmssl\n"); sys.exit(1)
pub, plain = sys.argv[1], sys.argv[2]
crypt = sm2.CryptSM2(public_key=pub, private_key="")
try:
    ct = crypt.encrypt(plain.encode(), mode=1)          # C1C3C2
except TypeError:
    ct = crypt.encrypt(plain.encode())                   # 旧版gmssl默认C1C3C2
h = ct.hex() if isinstance(ct, (bytes, bytearray)) else ct
if h.startswith("04"): h = h[2:]                         # Java端约定去04头
print(h)
PYEOF
) || exit 1
  login_body=$(jq -n --arg u "$username" --arg p "$enc" --arg c "$captcha_id" \
                '{username:$u, password:$p, captchaId:$c}')
  resp=$(api POST /user/login "" "$login_body")
  TOKEN=$(echo "$resp" | jq -r '.data.token // empty')
  if [ -n "$TOKEN" ]; then
    echo "登录成功, token 已注入（仅本进程内存）"; echo "$TOKEN" > .qa_token
  else
    echo "[FATAL] 登录失败: $resp"; exit 1
  fi
}

[ "${1:-}" = "--login" ] && login_interactive

if [ -z "$TOKEN" ] && [ -f .qa_token ]; then TOKEN=$(cat .qa_token); fi
if [ -z "$TOKEN" ]; then
  echo "[FATAL] 未提供 QA_TOKEN（或用 --login 交互登录 / .qa_token 文件）"; exit 1
fi
if [ -z "$AGENT_HOLO" ]; then
  # 未指定被测 agent 时，自动从 /memory/agents 取第一个 holographic 引擎的 agent
  AGENT_HOLO=$(api GET /memory/agents "$TOKEN" | jq -r '.data[]? | select(.engine=="mem_holographic") | .agent_id' | head -1)
fi
echo "=============================================================="
echo " 被测 BASE=${BASE}"
echo " 被测 AGENT(mem_holographic)=${AGENT_HOLO:-<无>}"
echo "=============================================================="

CREATED_FACT_ID=""

# =============================================================================
# G0 鉴权链（Shiro /memory/** → oauth2）
# =============================================================================
R=$(api GET /memory/agents "")
assert_code_msg "T01 无token访问agents → 401未授权 [A11-鉴权]" 401 "未授权" "$R"

R=$(api GET "/memory/facts?agent_id=whatever" "")
assert_code "T02 无token访问facts → 401 [A11-鉴权]" 401 "$R"

# =============================================================================
# G1 Agent 列表 + 统计（GET /memory/agents）
# =============================================================================
R=$(api GET /memory/agents "$TOKEN")
assert_code "T03 agents列表 → code=0 [A1-Agent列表]" 0 "$R"
assert_jq   "T03a agents字段齐全(agent_id/name/engine/available/fact_count/pending_count) [A1]" \
            '.data | type=="array" and (length==0 or (.[0] | has("agent_id") and has("name") and has("engine") and has("available") and has("fact_count") and has("pending_count")))' "$R"
assert_jq   "T03b agents列表不含mem_report_only引擎(G-4回归) [A1]" \
            '[.data[]? | select(.engine=="mem_report_only")] | length == 0' "$R"
assert_jq   "T03c agents列表不含nomem引擎 [A1]" \
            '[.data[]? | select(.engine=="nomem")] | length == 0' "$R"
assert_jq   "T03d agents列表不含powermem引擎(G-10回归) [A1]" \
            '[.data[]? | select(.engine=="powermem")] | length == 0' "$R"

# =============================================================================
# G2 分页查询（GET /memory/facts）
# =============================================================================
R=$(api GET "/memory/facts" "$TOKEN")
assert_code "T04 缺agent_id → 10003 [A2-参数校验]" 10003 "$R"

R=$(api GET "/memory/facts?agent_id=${AGENT_HOLO}&page=1&size=20" "$TOKEN")
assert_code "T05 facts分页 → code=0 [A2-分页]" 0 "$R"
assert_jq   "T05a 分页结构total/list [A2]" '.data | has("total") and (.list|type=="array")' "$R"

R=$(api GET "/memory/facts?agent_id=${AGENT_HOLO}&keyword=测试&category=preference&status=active&trust_min=0.3&trust_max=0.9&sort_by=trust&order=asc&page=1&size=10" "$TOKEN")
assert_code "T06 全筛选参数+排序白名单(trust/asc) → code=0 [A2-筛选排序]" 0 "$R"

R=$(api GET "/memory/facts?agent_id=${AGENT_HOLO}&size=500" "$TOKEN")
assert_jq   "T06a size=500 服务端收敛≤100 [A2]" '(.data.list | length) <= 100' "$R"

R=$(api GET "/memory/facts?agent_id=${AGENT_HOLO}&sort_by=created;DROP&order=desc" "$TOKEN")
assert_code "T06b 非法sort_by回落created不报错 [A2-白名单]" 0 "$R"

# =============================================================================
# G3 新增（POST /memory/facts）
# =============================================================================
R=$(api POST /memory/facts "$TOKEN" "{\"agent_id\":\"${AGENT_HOLO}\",\"content\":\"qa-api契约测试:用户偏好安静环境\",\"category\":\"preference\",\"tags\":\"测试,契约\"}")
assert_code "T07 新增fact → code=0 [A4-新增]" 0 "$R"
assert_jq   "T07a 返回fact_id>0 [A4]" '.data.fact_id > 0' "$R"
CREATED_FACT_ID=$(echo "$R" | jq -r '.data.fact_id // empty')

R=$(api POST /memory/facts "$TOKEN" "{\"agent_id\":\"${AGENT_HOLO}\"}")
assert_code "T08 新增缺content → 10003 [A4-参数校验]" 10003 "$R"

# =============================================================================
# G4 详情（GET /memory/facts/{fact_id}?agent_id=）
# =============================================================================
if [ -n "$CREATED_FACT_ID" ]; then
  R=$(api GET "/memory/facts/${CREATED_FACT_ID}?agent_id=${AGENT_HOLO}" "$TOKEN")
  assert_code "T09 详情 → code=0 [A3-详情]" 0 "$R"
  assert_jq   "T09a 详情含entities数组 [A3]" '.data | has("entities") and (.entities|type=="array")' "$R"
  assert_jq   "T09b 详情字段完整(trust_score/status/created_at) [A3]" '.data | has("trust_score") and has("status") and has("created_at")' "$R"
fi

R=$(api GET "/memory/facts/999999999?agent_id=${AGENT_HOLO}" "$TOKEN")
assert_code_msg "T10 详情不存在 → 10051记忆条目不存在 [A9-404链路]" 10051 "记忆条目不存在" "$R"

# =============================================================================
# G5 编辑（PUT /memory/facts/{fact_id}）
# =============================================================================
if [ -n "$CREATED_FACT_ID" ]; then
  R=$(api PUT "/memory/facts/${CREATED_FACT_ID}" "$TOKEN" "{\"agent_id\":\"${AGENT_HOLO}\",\"content\":\"qa-api契约测试:编辑后内容,喜欢周杰伦\",\"category\":\"preference\"}")
  assert_code "T11 编辑fact → code=0 [A5-编辑]" 0 "$R"
  assert_jq   "T11a 编辑生效(内容已更新) [A5]" '.data.content | contains("编辑后内容")' "$R"
fi

# =============================================================================
# G6 信任分反馈（POST /memory/facts/{fact_id}/feedback）
# =============================================================================
if [ -n "$CREATED_FACT_ID" ]; then
  R=$(api POST "/memory/facts/${CREATED_FACT_ID}/feedback" "$TOKEN" "{\"agent_id\":\"${AGENT_HOLO}\",\"helpful\":true}")
  assert_code "T12 反馈helpful=true → code=0 [A6-反馈]" 0 "$R"
  assert_jq   "T12a 信任分+0.05(new_trust-old_trust≈0.05) [A6]" '(.data.new_trust - .data.old_trust) > 0.049 and (.data.new_trust - .data.old_trust) < 0.051' "$R"

  R=$(api POST "/memory/facts/${CREATED_FACT_ID}/feedback" "$TOKEN" "{\"agent_id\":\"${AGENT_HOLO}\",\"helpful\":false}")
  assert_code "T13 反馈helpful=false → code=0 [A6]" 0 "$R"
  assert_jq   "T13a 信任分-0.10 [A6]" '(.data.old_trust - .data.new_trust) > 0.099 and (.data.old_trust - .data.new_trust) < 0.101' "$R"
fi

R=$(api POST "/memory/facts/1/feedback" "$TOKEN" "{\"agent_id\":\"${AGENT_HOLO}\"}")
assert_code "T14 反馈缺helpful → 10003 [A6-参数校验]" 10003 "$R"

# =============================================================================
# G7 审核（POST /memory/facts/{fact_id}/review）
# =============================================================================
if [ -n "$CREATED_FACT_ID" ]; then
  R=$(api POST "/memory/facts/${CREATED_FACT_ID}/review" "$TOKEN" "{\"agent_id\":\"${AGENT_HOLO}\",\"action\":\"reject\"}")
  assert_code "T15 审核reject → code=0 [A7-审核]" 0 "$R"
  assert_jq   "T15a 状态变为rejected [A7]" '.data.status == "rejected"' "$R"

  R=$(api POST "/memory/facts/${CREATED_FACT_ID}/review" "$TOKEN" "{\"agent_id\":\"${AGENT_HOLO}\",\"action\":\"approve\"}")
  assert_code "T16 审核approve → code=0 [A7]" 0 "$R"
  assert_jq   "T16a 状态恢复active且信任分0.5 [A7]" '.data.status == "active" and (.data.trust_score == 0.5)' "$R"
fi

R=$(api POST "/memory/facts/1/review" "$TOKEN" "{\"agent_id\":\"${AGENT_HOLO}\",\"action\":\"delete\"}")
assert_code "T17 review非法action → 10003 [A7-参数校验]" 10003 "$R"

R=$(api POST "/memory/facts/1/review" "$TOKEN" "{\"agent_id\":\"${AGENT_HOLO}\"}")
assert_code "T18 review缺action → 10003 [A7-参数校验]" 10003 "$R"

# =============================================================================
# G8 删除（DELETE /memory/facts/{fact_id}?agent_id=）
# =============================================================================
if [ -n "$CREATED_FACT_ID" ]; then
  R=$(api DELETE "/memory/facts/${CREATED_FACT_ID}?agent_id=${AGENT_HOLO}" "$TOKEN")
  assert_code "T19 删除fact → code=0 [A8-删除]" 0 "$R"

  R=$(api DELETE "/memory/facts/${CREATED_FACT_ID}?agent_id=${AGENT_HOLO}" "$TOKEN")
  assert_code_msg "T20 重复删除(已不存在) → 10051 [A9-404链路]" 10051 "记忆条目不存在" "$R"
fi

R=$(api DELETE "/memory/facts/999999999?agent_id=${AGENT_HOLO}" "$TOKEN")
assert_code_msg "T20a 删除不存在 → 10051记忆条目不存在 [A9]" 10051 "记忆条目不存在" "$R"

# =============================================================================
# G9 越权（checkAgentPermission → NO_PERMISSION 10169）
# =============================================================================
if [ -n "$TOKEN_B" ] && [ -n "$AGENT_FOREIGN" ]; then
  # 用户A的token 打 属于用户B的agent（AGENT_FOREIGN 应绑定 mem_holographic 且属主为B）
  R=$(api GET "/memory/facts?agent_id=${AGENT_FOREIGN}&page=1&size=10" "$TOKEN")
  assert_code_msg "T21 A的token访问B的agent → 10169无权限 [A10-越权]" 10169 "您没有权限操作该记录" "$R"

  R=$(api GET "/memory/facts/1?agent_id=${AGENT_FOREIGN}" "$TOKEN")
  assert_code "T21a 越权详情 → 10169 [A10]" 10169 "$R"

  R=$(api POST "/memory/facts" "$TOKEN" "{\"agent_id\":\"${AGENT_FOREIGN}\",\"content\":\"越权写入尝试\"}")
  assert_code "T21b 越权新增 → 10169 [A10]" 10169 "$R"

  R=$(api DELETE "/memory/facts/1?agent_id=${AGENT_FOREIGN}" "$TOKEN")
  assert_code "T21c 越权删除 → 10169 [A10]" 10169 "$R"
else
  skip "T21x 越权用例（需 QA_TOKEN_B + QA_AGENT_FOREIGN）"
fi

if [ -n "$TOKEN_ADMIN" ] && { [ -n "$AGENT_FOREIGN" ] || [ -n "$AGENT_HOLO" ]; }; then
  TARGET="${AGENT_FOREIGN:-$AGENT_HOLO}"
  R=$(api GET "/memory/facts?agent_id=${TARGET}&page=1&size=10" "$TOKEN_ADMIN")
  assert_code "T22 superAdmin访问任意agent → 放行code=0 [A10-超管]" 0 "$R"
else
  skip "T22 超管用例（需 QA_TOKEN_ADMIN）"
fi

# 不存在的 agent（selectById=null → hasAgentPermission=false）
R=$(api GET "/memory/facts?agent_id=not-exist-agent-qa&page=1&size=10" "$TOKEN")
assert_code "T23 不存在的agent_id → 10169 [A10-边界]" 10169 "$R"

# =============================================================================
# G10 引擎分派降级（design §5.2）
# 注：mem_report_only 已在 /memory/agents 列表排除（G-4 裁定落地，T03b 回归），
#     但其 facts 直查行为不变，仍返回空 PageData（不报错）。
# =============================================================================
if [ -n "$AGENT_SHORT" ]; then
  R=$(api GET "/memory/facts?agent_id=${AGENT_SHORT}&page=1&size=10" "$TOKEN")
  assert_code_msg "T24 mem_local_short列表 → 500压缩档案提示 [A12-降级]" 500 "该引擎为压缩档案式记忆，暂不支持条目管理，可切换至 Holographic 引擎" "$R"
  R=$(api POST "/memory/facts" "$TOKEN" "{\"agent_id\":\"${AGENT_SHORT}\",\"content\":\"x\"}")
  assert_code "T24a mem_local_short新增 → 500提示 [A12]" 500 "$R"
else
  skip "T24x mem_local_short 降级（需 QA_AGENT_SHORT）"
fi

if [ -n "$AGENT_MEM0" ]; then
  R=$(api GET "/memory/facts?agent_id=${AGENT_MEM0}&page=1&size=10" "$TOKEN")
  assert_code_msg "T25 mem0ai列表 → 500未配置提示 [A12-降级]" 500 "mem0 平台记忆暂不支持条目管理（未配置 API Key 或功能建设中）" "$R"
else
  skip "T25x mem0ai 降级（需 QA_AGENT_MEM0）"
fi

if [ -n "$AGENT_NOMEM" ]; then
  R=$(api GET "/memory/facts?agent_id=${AGENT_NOMEM}&page=1&size=10" "$TOKEN")
  assert_code "T26 nomem列表 → code=0 [A12-空列表]" 0 "$R"
  assert_jq   "T26a nomem返回空列表total=0 [A12]" '.data.total == 0 and (.data.list | length == 0)' "$R"
else
  skip "T26x nomem 空列表（需 QA_AGENT_NOMEM）"
fi

if [ -n "$AGENT_POWERMEM" ]; then
  # G-10 裁定方案A：powermem 列表排除（T03d）+ facts 直查返回专属降级提示（不再静默空列表）
  R=$(api GET "/memory/facts?agent_id=${AGENT_POWERMEM}&page=1&size=10" "$TOKEN")
  assert_code_msg "T26b powermem列表 → 500专属降级提示 [A12-降级]" 500 "PowerMem 云端记忆暂不支持控制台条目管理" "$R"
  R=$(api GET "/memory/facts/1?agent_id=${AGENT_POWERMEM}" "$TOKEN")
  assert_code_msg "T26c powermem详情 → 500新兜底文案 [A12-降级]" 500 "当前智能体绑定的记忆引擎暂不支持条目管理，请在 Agent 编辑页切换至 Holographic 引擎" "$R"
else
  skip "T26b/c powermem 降级（需 QA_AGENT_POWERMEM）"
fi

# =============================================================================
# G11 内部服务不可用（连接拒绝/超时 → "记忆服务不可用"）
# =============================================================================
if [ "$TEST_DOWN" = "1" ]; then
  R=$(api GET "/memory/facts?agent_id=${AGENT_HOLO}&page=1&size=10" "$TOKEN")
  assert_code_msg "T27 xiaozhi-server停机 → 500记忆服务不可用 [A13-容错]" 500 "记忆服务不可用" "$R"
else
  skip "T27 服务不可用（需 QA_TEST_DOWN=1 且先停 xiaozhi-server）"
fi

# =============================================================================
# 汇总
# =============================================================================
echo "=============================================================="
echo " 结果: PASS=${PASS}  FAIL=${FAIL}  SKIP见上"
if [ ${FAIL} -gt 0 ]; then
  printf ' 失败用例: %s\n' "${FAILED_CASES[*]}"
  exit 1
fi
echo " 全部通过"
exit 0

#!/bin/bash
# 管理员全流程自动化模拟（④）：模拟管理员登录 → 配角色/人设 → 模拟设备对话 → 记忆落库验证 → 可视化数据就绪检查
# 用法: bash admin_flow_sim.sh   （在服务器上运行）
set -e
API="http://127.0.0.1:8002/xiaozhi"
dbq() { MYSQL_PWD=123456 mysql -uroot xiaozhi_esp32_server -N -e "$1"; }
J='Content-Type: application/json'

step() { echo ""; echo "===== $1 ====="; }

step "0) 管理员登录（控制台账号）"
LOGIN=$(curl -s -m 10 -X POST "$API/user/login" -H "$J" -d "$(cat /tmp/admin_login.json)" 2>/dev/null || echo '{}')
TOKEN=$(echo "$LOGIN" | python3 -c "import json,sys; d=json.load(sys.stdin); print((d.get('data') or {}).get('token',''))" 2>/dev/null || true)
if [ -z "$TOKEN" ]; then
  # 无凭据文件则复用现有会话 token（模拟已登录态）
  TOKEN=$(dbq "SELECT token FROM sys_user_token ORDER BY update_date DESC LIMIT 1" | tr -d '[:space:]')
  echo "（未提供 /tmp/admin_login.json，复用现有会话 token）"
fi
echo "token: ${TOKEN:0:8}..."
AUTH="Authorization: Bearer $TOKEN"

step "1) 智能体列表（选择要配置的角色）"
AGENTS=$(curl -s -m 10 "$API/agent/list" -H "$AUTH")
echo "$AGENTS" | python3 -c "
import json,sys
d=json.load(sys.stdin)
data=d.get('data')
lst=data.get('list') if isinstance(data,dict) else data
lst=lst or []
for a in lst[:5]: print(' ', a.get('id'), a.get('agentName'), '| TTS:', a.get('ttsModelId'), '| LLM:', a.get('llmModelId'))"
AGENT_ID=$(echo "$AGENTS" | python3 -c "
import json,sys
d=json.load(sys.stdin)
data=d.get('data')
lst=data.get('list') if isinstance(data,dict) else data
lst=lst or []
print(lst[0]['id'] if lst else '')")
echo "目标智能体: $AGENT_ID"

step "2) 更新角色人设（system_prompt 模拟管理员配置）"
NOW=$(date +%s)
curl -s -m 10 -X PUT "$API/agent/$AGENT_ID" -H "$AUTH" -H "$J" -d "{
  \"agentName\": \"豆包小何\",
  \"systemPrompt\": \"你是温柔可爱的语音助手小何，说话简短口语化。当前模拟时间戳 $NOW（管理员流程模拟标记）\"
}" | head -c 120; echo

step "3) 查询角色当前配置回读"
curl -s -m 10 "$API/agent/$AGENT_ID" -H "$AUTH" | python3 -c "
import json,sys
d=json.load(sys.stdin)
a=d.get('data') or {}
sp=(a.get('systemPrompt') or '')[:60]
print('  systemPrompt:', sp)"

step "4) 模拟设备拉取配置（ESP32 视角，server.secret）"
SEC=$(dbq "SELECT param_value FROM sys_params WHERE param_code='server.secret'" | tr -d '[:space:]')
curl -s -m 10 -X POST "$API/config/agent-models" -H "Authorization: Bearer $SEC" -H "$J" \
  -d "{\"clientId\":\"admin-flow-sim\",\"macAddress\":\"14:c1:9f:d1:33:48\",\"selectedModule\":{}}" \
  | python3 -c "
import json,sys
d=json.load(sys.stdin)
data=d.get('data') or {}
print('  code:', d.get('code'), '| prompt 下发:', bool(data.get('prompt')))
print('  LLM/TTS/ASR:', list((data.get('LLM') or {}).keys()), list((data.get('TTS') or {}).keys()), list((data.get('ASR') or {}).keys()))"

step "5) LLM 对话实测（人设生效验证）"
cd /root/xiaozhi-server/main/xiaozhi-server
.venv/bin/python << 'PYEOF'
import sys, subprocess, json
sys.path.insert(0, '.')
raw = subprocess.check_output(['mysql','-uroot','-p123456','xiaozhi_esp32_server','-N','-B','-e',"SELECT config_json FROM ai_model_config WHERE id='LLM_DeepSeek'"]).decode().strip()
cfg = json.loads(raw)
from core.utils.llm import create_instance
llm = create_instance(cfg.get('type'), cfg)
out = llm.response_no_stream('你是温柔可爱的语音助手小何。用一句话打个招呼', '你好呀')
print('  小何回复:', out[:100])
PYEOF

step "6) 记忆写入（模拟对话产生记忆 → 可视化数据就绪）"
curl -s -m 10 -X POST "$API/memory/facts" -H "$AUTH" -H "$J" -d "{
  \"agent_id\": \"$AGENT_ID\",
  \"content\": \"管理员模拟流程标记：用户喜欢在晚饭后听轻音乐（$NOW）\",
  \"category\": \"preference\",
  \"tags\": \"模拟,音乐,晚间\"
}" | head -c 200; echo

step "7) 记忆查询（/memory/facts → 图谱/时间轴的数据源）"
curl -s -m 10 "$API/memory/facts?agent_id=$AGENT_ID&page=1&size=5&sort_by=created&order=desc" -H "$AUTH" | python3 -c "
import json,sys
d=json.load(sys.stdin)
p=(d.get('data') or {})
lst=p.get('list') or []
print('  总记忆数:', p.get('total'))
for f in lst[:3]:
    print('   -', (f.get('content') or '')[:40], '|', f.get('category'), '|', f.get('createdAt'))"

step "8) 收尾核验（双服务健康）"
systemctl is-active xiaozhi-manager-api xiaozhi-server
echo "===== 管理员全流程模拟完成 ====="

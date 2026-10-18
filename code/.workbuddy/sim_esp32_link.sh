#!/bin/bash
# 模拟 ESP32 设备全链路 v2（修正版：clientId + selectedModule 对象 + DB 直读配置实测 provider）
set -e
SEC=$(MYSQL_PWD=123456 mysql -uroot xiaozhi_esp32_server -N -e "SELECT param_value FROM sys_params WHERE param_code='server.secret'" | tr -d '[:space:]')
MAC="14:c1:9f:d1:33:48"
CID="sim-esp32-test"

echo "== 1) 模拟设备拉全量配置（server.secret 鉴权）:"
curl -s -m 10 -X POST 'http://127.0.0.1:8002/yuhe/config/agent-models' \
  -H "Authorization: Bearer $SEC" -H 'Content-Type: application/json' \
  -d "{\"clientId\":\"$CID\",\"macAddress\":\"$MAC\",\"selectedModule\":{}}" -o /tmp/dev_cfg.json -w "HTTP %{http_code}\n"
python3 -c "
import json
d = json.load(open('/tmp/dev_cfg.json'))
data = d.get('data') or {}
print('code:', d.get('code'), '| 模块:', list(data.keys()))
print('agent_id:', data.get('agent_id'))
print('device_config:', json.dumps(data.get('device_config'), ensure_ascii=False))
for m in ('LLM','TTS','ASR','VAD','Memory'):
    mods = data.get(m) or {}
    for mid, cfg in (mods.items() if isinstance(mods, dict) else []):
        print(f'{m}: {mid} type={cfg.get(\"type\")}')"

echo "== 2) 千问TTS provider 实测（模拟设备语音合成）:"
cd /root/xiaozhi-server/main/yuhe-server
.venv/bin/python << 'PYEOF'
import asyncio, sys, subprocess, json
sys.path.insert(0, '.')
from core.providers.tts.qwen_tts import TTSProvider
raw = subprocess.check_output(['mysql','-uroot','-p123456','xiaozhi_esp32_server','-N','-B','-e',"SELECT config_json FROM ai_model_config WHERE id='TTS_QwenTTS_Flash'"]).decode().strip()
cfg = json.loads(raw)
print('  配置: type=%s model=%s voice=%s' % (cfg.get('type'), cfg.get('model'), cfg.get('voice')))
async def run():
    p = TTSProvider(cfg, delete_audio_file=False)
    out = '/tmp/tts_link_test.wav'
    await p.text_to_speak('链路测试成功，千问语音合成正常工作。', out)
    import os
    sz = os.path.getsize(out)
    ok = open(out,'rb').read(4) == b'RIFF'
    print(f'  TTS 输出: {sz} bytes, WAV头有效={ok}')
asyncio.run(run())
PYEOF

echo "== 3) 千问ASR provider 实测（模拟设备语音识别）:"
.venv/bin/python << 'PYEOF'
import asyncio, sys, subprocess, json, struct, math, wave
sys.path.insert(0, '.')
from core.providers.asr.qwen3_asr_flash import ASRProvider
raw = subprocess.check_output(['mysql','-uroot','-p123456','xiaozhi_esp32_server','-N','-B','-e',"SELECT config_json FROM ai_model_config WHERE id='ASR_Qwen3Flash'"]).decode().strip()
cfg = json.loads(raw)
print('  配置: type=%s model=%s' % (cfg.get('type'), cfg.get('model_name')))
# 生成 1 秒 440Hz 音（链路连通性验证）
with wave.open('/tmp/asr_link_test.wav','w') as w:
    w.setnchannels(1); w.setsampwidth(2); w.setframerate(16000)
    w.writeframes(b''.join(struct.pack('<h', int(3000*math.sin(2*math.pi*440*t/16000))) for t in range(16000)))
class Art:
    temp_path = '/tmp/asr_link_test.wav'
    file_path = '/tmp/asr_link_test.wav'
async def run():
    p = ASRProvider(cfg, delete_audio_file=False)
    text, _ = await p.speech_to_text([b'x'], 'link-test', Art())
    print('  ASR 返回:', repr(text), '(空=纯音无可识别语音，链路HTTP 200即通)')
asyncio.run(run())
PYEOF

echo "== 4) LLM 链路实测（豆包小何当前 LLM_DeepSeek 配置实例化对话）:"
.venv/bin/python << 'PYEOF'
import asyncio, sys, subprocess, json
sys.path.insert(0, '.')
raw = subprocess.check_output(['mysql','-uroot','-p123456','xiaozhi_esp32_server','-N','-B','-e',"SELECT config_json FROM ai_model_config WHERE id='LLM_DeepSeek'"]).decode().strip()
cfg = json.loads(raw)
print('  配置: type=%s model=%s' % (cfg.get('type'), cfg.get('model_name')))
from core.utils.llm import create_instance
llm = create_instance(cfg.get('type'), cfg)
async def run():
    msgs = [{'role':'user','content':'你好，请用一句话介绍你自己'}]
    texts = []
    async for t in llm.response(msgs):
        texts.append(t)
    print('  LLM 回复:', ''.join(texts)[:120])
asyncio.run(run())
PYEOF

echo "== 5) 模拟设备上报 device_config（B线云端记忆）:"
curl -s -m 10 -X POST 'http://127.0.0.1:8002/yuhe/config/device-config' \
  -H "Authorization: Bearer $SEC" -H 'Content-Type: application/json' \
  -d "{\"clientId\":\"$CID\",\"macAddress\":\"$MAC\",\"config\":{\"volume\":42}}" | head -c 150; echo
MYSQL_PWD=123456 mysql -uroot xiaozhi_esp32_server -N -e "SELECT device_id, JSON_EXTRACT(config_json,'$.volume') FROM ai_device_config WHERE device_id LIKE '%d1:33:48%'"
echo "== 全链路模拟完成 =="

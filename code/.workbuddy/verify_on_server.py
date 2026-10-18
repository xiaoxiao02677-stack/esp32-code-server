#!/usr/bin/env python3
"""在服务器真实环境（.venv）里验证 doubao_v3 发包格式与动态指令通道。

不发起真实网络请求，只 mock requests.post 抓 payload。
"""
import sys

sys.path.insert(0, r"G:\demo\21_xiaozhi\code\.workbuddy")
from ssh_run import get_client  # noqa: E402

SCRIPT = r'''
import sys, json, base64, asyncio
sys.path.insert(0, "/root/xiaozhi-server/main/yuhe-server")
from unittest.mock import patch, Mock
from core.providers.tts.doubao_v3 import TTSProvider


def fake_resp():
    body = "\n".join([
        json.dumps({"code": 0, "message": "", "data": base64.b64encode(b"AB").decode()}),
        json.dumps({"code": 20000000, "message": "OK", "data": None}),
    ])
    r = Mock(status_code=200)
    r.text = body
    return r


def mk(**cfg):
    base = {"appid": "1", "access_token": "t", "output_dir": "tmp/test"}
    base.update(cfg)
    return TTSProvider(base, delete_audio_file=True)


def grab(p, text="你好"):
    with patch("core.providers.tts.doubao_v3.requests.post", return_value=fake_resp()) as m:
        asyncio.run(p.text_to_speak(text, None))
    return m.call_args.kwargs["json"]["req_params"]


print("python:", sys.version.split()[0])
p = mk(voice_instruction="用温柔安慰的语气说")
req = grab(p)
print("A 固定指令 additions:", req.get("additions"))
print("A 有无非法 voice_instruction 字段:", "voice_instruction" in req)
assert "voice_instruction" not in req
assert json.loads(req["additions"])["context_texts"] == ["用温柔安慰的语气说"]

p2 = mk(voice_instruction="固定")
p2.set_dynamic_instruction("用轻快俏皮的语气说")
req2 = grab(p2)
print("B 动态覆盖:", json.loads(req2["additions"])["context_texts"])
assert json.loads(req2["additions"])["context_texts"] == ["用轻快俏皮的语气说"]

p3 = mk(resource_id="seed-icl-2.0", voice_instruction="低沉沙哑")
req3 = grab(p3)
print("C 复刻音色 model:", req3.get("model"))
assert req3.get("model") == "seed-tts-2.0-expressive"

p4 = mk()
req4 = grab(p4)
print("D 无指令时 additions:", req4.get("additions"))
assert "additions" not in req4

from core.connection import ConnectionHandler as CH
print("E connection 新方法:", all(hasattr(CH, n) for n in
      ("_tts_config", "_recent_chat_text", "_generate_voice_instruction",
       "_refresh_dynamic_voice_instruction")))
print("\nSERVER VERIFY ALL PASS")
'''

client = get_client()
try:
    cmd = "cd /root/xiaozhi-server/main/yuhe-server && cat > /tmp/_vfy.py <<'PYEOF'\n" + \
          SCRIPT + "\nPYEOF\n.venv/bin/python /tmp/_vfy.py"
    _, out, err = client.exec_command(cmd, timeout=120)
    print(out.read().decode("utf-8", "replace"))
    e = err.read().decode("utf-8", "replace")
    if e.strip():
        print("[stderr]", e)
finally:
    client.close()

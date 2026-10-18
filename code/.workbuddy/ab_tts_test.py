# -*- coding: utf-8 -*-
"""A/B 实测：你的官方脚本 payload vs 项目当前 payload，对同一复刻音色请求。"""
import base64, json, uuid, requests

API_KEY = "d9f77dba-01ca-47fa-a4d3-7002adf6b6a4"
URL = "https://openspeech.bytedance.com/api/v3/tts/unidirectional"
RESOURCE_ID = "seed-icl-2.0"
SPEAKER = "S_N8pC5xwg2"
TEXT = "今天真是个好日子，我太开心啦！"
INSTR = "用非常开心、兴奋、雀跃的语气说话"

def call(name, payload):
    h = {"Content-Type": "application/json",
         "X-Api-Resource-Id": RESOURCE_ID,
         "X-Api-Request-Id": str(uuid.uuid4()),
         "X-Api-Key": API_KEY}
    try:
        r = requests.post(URL, json=payload, headers=h, stream=True, timeout=60)
    except Exception as e:
        print(f"[{name}] 网络异常 {e}"); return
    if r.status_code != 200:
        print(f"[{name}] HTTP {r.status_code}: {r.text[:300]}"); return
    audio = bytearray(); codes = []
    for line in r.iter_lines(decode_unicode=True):
        if not line: continue
        try: o = json.loads(line)
        except Exception: print(f"[{name}] 非JSON行: {line[:120]}"); continue
        codes.append((o.get("code"), o.get("message")))
        if o.get("code", 0) not in (0, 20000000):
            print(f"[{name}] 错误 code={o.get('code')} msg={o.get('message')}")
            break
        d = o.get("data")
        if isinstance(d, str) and d:
            s = "".join(d.split()); s += "=" * ((-len(s)) % 4)
            audio.extend(base64.b64decode(s))
        if o.get("code") == 20000000 and o.get("message") == "ok":
            break
    print(f"[{name}] 字节={len(audio)} codes={codes[:3]}...{codes[-1:] }")

# A: 你的官方脚本原样（namespace + emotion + explicit_language，不带 model）
A = {
    "user": {"uid": "2101000101"},
    "namespace": "BidirectionalTTS",
    "req_params": {
        "speaker": SPEAKER,
        "text": TEXT,
        "audio_params": {"format": "mp3", "sample_rate": 24000,
                         "enable_emotion": True, "emotion": "happy", "emotion_scale": 4},
        "additions": json.dumps({"explicit_language": "zh", "context_texts": [INSTR]},
                                ensure_ascii=False),
    },
}
# B: 项目当前实现（无 namespace，补 model=expressive，context_texts）
B = {
    "user": {"uid": "yuhe-esp32-server"},
    "req_params": {
        "text": TEXT, "speaker": SPEAKER,
        "model": "seed-tts-2.0-expressive",
        "audio_params": {"format": "mp3", "sample_rate": 24000,
                         "speech_rate": 0, "loudness_rate": 0},
        "additions": json.dumps({"context_texts": [INSTR]}, ensure_ascii=False),
    },
}
# C: A 去掉 namespace
C = json.loads(json.dumps(A)); C.pop("namespace")
# D: A 去掉 emotion 三件套
D = json.loads(json.dumps(A))
D["req_params"]["audio_params"] = {"format": "mp3", "sample_rate": 24000}
# E: A 去掉 explicit_language
E = json.loads(json.dumps(A))
E["req_params"]["additions"] = json.dumps({"context_texts": [INSTR]}, ensure_ascii=False)
# F: A 但 context_texts 为空（只靠 emotion）
F = json.loads(json.dumps(A))
F["req_params"]["additions"] = json.dumps({"explicit_language": "zh"}, ensure_ascii=False)

call("A 官方原样", A)
call("B 项目当前", B)
call("C 官方-namespace", C)
call("D 官方-emotion", D)
call("E 官方-explicit_language", E)
call("F 官方-context_texts", F)

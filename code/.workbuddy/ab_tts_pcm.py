# -*- coding: utf-8 -*-
"""用 pcm 格式定量验证：emotion / context_texts 是否真的影响韵律。"""
import base64, json, uuid, struct, requests

API_KEY = "d9f77dba-01ca-47fa-a4d3-7002adf6b6a4"
URL = "https://openspeech.bytedance.com/api/v3/tts/unidirectional"
RES, SPK = "seed-icl-2.0", "S_N8pC5xwg2"
TEXT = "今天真是个好日子。"

def synth(tag, audio_params, additions):
    p = {"user": {"uid": "t"}, "namespace": "BidirectionalTTS",
         "req_params": {"speaker": SPK, "text": TEXT,
                        "audio_params": dict({"format": "pcm", "sample_rate": 24000}, **audio_params)}}
    if additions:
        p["req_params"]["additions"] = json.dumps(additions, ensure_ascii=False)
    h = {"Content-Type": "application/json", "X-Api-Resource-Id": RES,
         "X-Api-Request-Id": str(uuid.uuid4()), "X-Api-Key": API_KEY}
    r = requests.post(URL, json=p, headers=h, stream=True, timeout=60)
    if r.status_code != 200:
        print(f"{tag}: HTTP {r.status_code} {r.text[:200]}"); return None
    buf = bytearray()
    for line in r.iter_lines(decode_unicode=True):
        if not line: continue
        o = json.loads(line)
        if o.get("code", 0) not in (0, 20000000):
            print(f"{tag}: ERR {o.get('code')} {o.get('message')}"); return None
        d = o.get("data")
        if d:
            s = "".join(d.split()); s += "=" * ((-len(s)) % 4); buf.extend(base64.b64decode(s))
        if o.get("code") == 20000000: break
    n = len(buf)//2
    v = struct.unpack(f"<{n}h", buf[:n*2])
    dur = n/24000
    rms = (sum(x*x for x in v)/max(n,1))**0.5
    zc = sum(1 for i in range(1,n) if (v[i-1] < 0) != (v[i] < 0))
    print(f"{tag:26s} dur={dur:5.2f}s rms={rms:7.1f} zcr={zc/max(dur,0.01):7.1f}/s samples={n}")
    return buf

def ap(**kw): return kw

synth("baseline(无情感无指令)", ap(), None)
synth("emotion=happy",          ap(enable_emotion=True, emotion="happy", emotion_scale=5), {"explicit_language":"zh"})
synth("emotion=sad",            ap(enable_emotion=True, emotion="sad",   emotion_scale=5), {"explicit_language":"zh"})
synth("emotion=angry",          ap(enable_emotion=True, emotion="angry", emotion_scale=5), {"explicit_language":"zh"})
synth("仅context_texts(项目现状)", ap(), {"explicit_language":"zh","context_texts":["用非常开心兴奋的语气说话"]})
synth("context+emotion=happy",  ap(enable_emotion=True, emotion="happy", emotion_scale=5), {"explicit_language":"zh","context_texts":["用非常开心兴奋的语气说话"]})
synth("仅speech_rate=+50",      ap(speech_rate=50), {"explicit_language":"zh"})

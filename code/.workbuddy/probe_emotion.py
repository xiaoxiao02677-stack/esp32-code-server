# -*- coding: utf-8 -*-
"""探测 seed-icl-2.0 合法 emotion 取值 & emotion_scale 范围。"""
import base64, json, uuid, requests
API_KEY = "d9f77dba-01ca-47fa-a4d3-7002adf6b6a4"
URL = "https://openspeech.bytedance.com/api/v3/tts/unidirectional"
RES, SPK = "seed-icl-2.0", "S_N8pC5xwg2"
def probe(emotion, scale=5):
    p = {"user":{"uid":"t"},"namespace":"BidirectionalTTS",
         "req_params":{"speaker":SPK,"text":"你好。",
            "audio_params":{"format":"mp3","sample_rate":24000,
                            "enable_emotion":True,"emotion":emotion,"emotion_scale":scale},
            "additions":json.dumps({"explicit_language":"zh"},ensure_ascii=False)}}
    h={"Content-Type":"application/json","X-Api-Resource-Id":RES,
       "X-Api-Request-Id":str(uuid.uuid4()),"X-Api-Key":API_KEY}
    try:
        r=requests.post(URL,json=p,headers=h,stream=True,timeout=40)
    except Exception as e:
        return f"NET {e}"
    if r.status_code!=200: return f"HTTP{r.status_code} {r.text[:150]}"
    n=0
    for line in r.iter_lines(decode_unicode=True):
        if not line: continue
        o=json.loads(line)
        if o.get("code",0) not in (0,20000000): return f"ERR {o.get('code')} {o.get('message')}"
        if o.get("data"): n+=len(o["data"])
        if o.get("code")==20000000: break
    return f"OK bytes~{n}"
cands=["happy","sad","angry","surprised","scared","hate","excited","coldness","neutral",
       "fear","disgust","professional","narrator","comfort","coquettish","singing",
       "upset","depressed","gentle","lovely","serious","开心","garbage_value"]
for c in cands:
    print(f"{c:14s} -> {probe(c)}")
print("--- emotion_scale 边界 ---")
for s in [0,1,3,5,6,10,100]:
    print(f"scale={s:<4d} -> {probe('happy', s)}")

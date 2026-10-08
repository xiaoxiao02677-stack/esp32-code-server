# -*- coding: utf-8 -*-
"""验证：非复刻资源(seed-tts-2.0 + 官方音色)下，namespace 是否安全；以及 model 字段影响。"""
import base64, json, uuid, requests
KEY="d9f77dba-01ca-47fa-a4d3-7002adf6b6a4"; URL="https://openspeech.bytedance.com/api/v3/tts/unidirectional"
def go(tag, res, speaker, ns, model=None):
    rp={"speaker":speaker,"text":"你好，我是小智。","audio_params":{"format":"mp3","sample_rate":24000}}
    if model: rp["model"]=model
    p={"user":{"uid":"t"},"req_params":rp}
    if ns: p["namespace"]=ns
    h={"Content-Type":"application/json","X-Api-Resource-Id":res,"X-Api-Request-Id":str(uuid.uuid4()),"X-Api-Key":KEY}
    r=requests.post(URL,json=p,headers=h,stream=True,timeout=40)
    if r.status_code!=200: print(f"{tag:38s} HTTP{r.status_code} {r.text[:160]}"); return
    n=0; msg=""
    for line in r.iter_lines(decode_unicode=True):
        if not line: continue
        o=json.loads(line)
        if o.get("code",0) not in (0,20000000):
            print(f"{tag:38s} ERR {o.get('code')} {o.get('message')}"); return
        if o.get("data"): n+=len(o["data"])
        if o.get("code")==20000000: msg=o.get("message"); break
    print(f"{tag:38s} OK bytes~{n} end={msg}")
S="zh_female_xiaohe_uranus_bigtts"
go("seed-tts-2.0 官方音色 无namespace","seed-tts-2.0",S,None)
go("seed-tts-2.0 官方音色 有namespace","seed-tts-2.0",S,"BidirectionalTTS")
go("seed-tts-2.0 +model=expressive","seed-tts-2.0",S,None,"seed-tts-2.0-expressive")
go("seed-icl-2.0 复刻 无namespace","seed-icl-2.0","S_N8pC5xwg2",None)
go("seed-icl-2.0 复刻 有namespace","seed-icl-2.0","S_N8pC5xwg2","BidirectionalTTS")
go("seed-icl-2.0 复刻 +model=expressive","seed-icl-2.0","S_N8pC5xwg2","BidirectionalTTS","seed-tts-2.0-expressive")

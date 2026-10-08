# -*- coding: utf-8 -*-
"""pcm 波形判别：哪些 emotion 值真正改变韵律（含重复采样看随机性）。"""
import base64, json, uuid, struct, requests
API_KEY="d9f77dba-01ca-47fa-a4d3-7002adf6b6a4"; URL="https://openspeech.bytedance.com/api/v3/tts/unidirectional"
RES,SPK="seed-icl-2.0","S_N8pC5xwg2"; TEXT="今天真是个好日子，我们一起出去玩吧。"
def synth(emotion, scale=5, rep=0):
    ap={"format":"pcm","sample_rate":24000}
    if emotion is not None: ap.update(enable_emotion=True,emotion=emotion,emotion_scale=scale)
    p={"user":{"uid":"t"},"namespace":"BidirectionalTTS",
       "req_params":{"speaker":SPK,"text":TEXT,"audio_params":ap,
                     "additions":json.dumps({"explicit_language":"zh"},ensure_ascii=False)}}
    h={"Content-Type":"application/json","X-Api-Resource-Id":RES,"X-Api-Request-Id":str(uuid.uuid4()),"X-Api-Key":API_KEY}
    r=requests.post(URL,json=p,headers=h,stream=True,timeout=40)
    if r.status_code!=200: return None
    b=bytearray()
    for line in r.iter_lines(decode_unicode=True):
        if not line: continue
        o=json.loads(line)
        if o.get("code",0) not in (0,20000000): return None
        if o.get("data"):
            s="".join(o["data"].split()); s+="="*((-len(s))%4); b.extend(base64.b64decode(s))
        if o.get("code")==20000000: break
    n=len(b)//2; v=struct.unpack(f"<{n}h",b[:n*2]); d=n/24000
    rms=(sum(x*x for x in v)/max(n,1))**0.5
    zc=sum(1 for i in range(1,n) if (v[i-1]<0)!=(v[i]<0))
    return d,rms,zc/max(d,0.01),n
print(f"{'emotion':14s} {'dur':>6s} {'rms':>8s} {'zcr':>8s} {'samples':>8s}")
for e in [None,"happy","sad","angry","surprised","scared","hate","excited","coldness","neutral","garbage_value"]:
    r1=synth(e); r2=synth(e)
    if not r1: print(f"{str(e):14s} FAILED"); continue
    print(f"{str(e):14s} {r1[0]:6.2f} {r1[1]:8.1f} {r1[2]:8.1f} {r1[3]:8d}   | rep2 rms={r2[1]:8.1f} dur={r2[0]:5.2f}")

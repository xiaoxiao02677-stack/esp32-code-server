#!/usr/bin/env python3
"""完整登录 + customer 首页全部接口 401 排查（一次性定位踢回登录页的元凶）。"""
import json
import ssl
import subprocess
import sys
import urllib.request
import uuid as uuidlib

sys.path.insert(0, r"G:\demo\21_xiaozhi\code\.workbuddy")
from gmssl import sm2

CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE
B = "http://sandyun.top:8001/yuhe"


def http(m, p, body=None, tok=None, raw=False):
    d = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(B + p, data=d, method=m)
    r.add_header("Content-Type", "application/json")
    if tok:
        r.add_header("Authorization", "Bearer " + tok)
    with urllib.request.urlopen(r, timeout=15, context=CTX) as resp:
        payload = resp.read()
        return payload if raw else json.loads(payload.decode())


def ssh(cmd):
    r = subprocess.run(["python", r"G:\demo\21_xiaozhi\code\.workbuddy\ssh_run.py", cmd],
                       capture_output=True, text=True)
    return r.stdout


def main():
    cap_uuid = str(uuidlib.uuid4())
    http("GET", "/user/captcha?uuid=" + cap_uuid, raw=True)
    out = ssh(f"redis-cli get 'sys:captcha:{cap_uuid}'")
    # 解析：输出最后一行的 "XXXXX"（含引号）
    lines = [l for l in out.strip().split("\n") if l.startswith('"') or (l and not l.startswith("$") and "[rc" not in l)]
    code = lines[-1].strip().strip('"') if lines else ""
    print("captcha =", code)
    if not code:
        print("FAIL: no captcha")
        return 1

    pub = http("GET", "/user/pub-config")
    pk = pub["data"]["sm2PublicKey"]
    raw_pk = pk[2:] if pk.startswith("04") and len(pk) == 130 else pk
    crypt = sm2.CryptSM2(public_key=raw_pk, private_key="", mode=1)
    enc = "04" + crypt.encrypt((code + "P@ssword123").encode()).hex()
    res = http("POST", "/user/login", {"username": "demo", "password": enc, "captchaId": cap_uuid})
    print("login:", res["code"], res.get("msg", ""))
    if res["code"] != 0:
        return 1
    tok = res["data"]["token"]
    print("TOKEN:", tok[:12] + "...")

    # 逐个测 customer Home.vue 的全部接口（按 api.js 调用顺序）
    for p in ["/user/info", "/agent/list", "/voiceResource?page=1&limit=100"]:
        try:
            d = http("GET", p, tok=tok)
            print(f"{p:40} -> code={d['code']} data={str(d.get('data'))[:50]}")
        except Exception as e:
            print(f"{p:40} -> EXC {e}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

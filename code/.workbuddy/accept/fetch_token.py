#!/usr/bin/env python3
"""获取测试环境 demo 账号的登录 token（SM2 加密 + Redis 验证码过闸）。

链路：8101/yuhe/ -> 8002 manager-api（同一 DB，demo 账号沿用）
验证码：触发 /user/captcha 后从 Redis key 'sys:captcha:{uuid}' 读取明文。
"""
import json
import ssl
import subprocess
import sys
import urllib.request
import uuid as uuidlib

from gmssl import sm2

B = "https://sandyun.top:8101/yuhe"
CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE

SSH_CMD = [
    "ssh", "-p", "22223", "root@sandyun.top",
    "redis-cli get 'sys:captcha:{uuid}'",
]


def http(m, p, body=None, raw=False):
    d = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(B + p, data=d, method=m)
    r.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(r, timeout=20, context=CTX) as resp:
        payload = resp.read()
        return payload if raw else json.loads(payload.decode())


def redis_captcha(cap_uuid):
    cmd = [s.replace("{uuid}", cap_uuid) for s in SSH_CMD]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    lines = [l for l in r.stdout.strip().split("\n") if l and "rc=" not in l]
    return lines[-1].strip().strip('"') if lines else ""


def login(username, password):
    # 1. 公钥
    pub = http("GET", "/user/pub-config")
    pk = pub["data"]["sm2PublicKey"]
    raw_pk = pk[2:] if pk.startswith("04") and len(pk) == 130 else pk
    crypt = sm2.CryptSM2(public_key=raw_pk, private_key="", mode=1)

    # 2. 验证码
    cap_uuid = str(uuidlib.uuid4())
    http("GET", "/user/captcha?uuid=" + cap_uuid, raw=True)
    code = redis_captcha(cap_uuid)
    if not code:
        print("FAIL: captcha not cached")
        sys.exit(1)

    # 3. 登录（契约: '04' + sm2(captcha+password)）
    enc = "04" + crypt.encrypt((code + password).encode()).hex()
    res = http("POST", "/user/login",
               {"username": username, "password": enc, "captchaId": cap_uuid})
    if res.get("code") != 0:
        print("LOGIN FAIL:", res)
        sys.exit(1)
    data = res["data"]
    tok = data.get("token") or (data.get("tokenInfo") or {}).get("tokenValue")
    print("TOKEN=" + tok)
    return tok


if __name__ == "__main__":
    u = sys.argv[1] if len(sys.argv) > 1 else "demo"
    p = sys.argv[2] if len(sys.argv) > 2 else "P@ssword123"
    login(u, p)

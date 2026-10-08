#!/usr/bin/env python3
"""注册测试账号 hermes_test（超强密码），Redis 验证码过闸，全程走 /user/register 契约。"""
import json
import ssl
import subprocess
import sys
import urllib.request
import uuid as uuidlib

from gmssl import sm2

CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE
B = "http://sandyun.top:8001/xiaozhi"
USERNAME = "hermes_test"
PASSWORD = "Xk9#mQ2$vL8@wR5!nZ4+pJ7&bH3"


def http(m, p, body=None, raw=False):
    d = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(B + p, data=d, method=m)
    r.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(r, timeout=15, context=CTX) as resp:
        payload = resp.read()
        return payload if raw else json.loads(payload.decode())


def redis_captcha(cap_uuid):
    r = subprocess.run(["python", r"G:\demo\21_xiaozhi\code\.workbuddy\ssh_run.py",
                        f"redis-cli get 'sys:captcha:{cap_uuid}'"],
                       capture_output=True, text=True)
    lines = [l for l in r.stdout.strip().split("\n")
             if l.startswith('"') and "rc=" not in l]
    return lines[-1].strip().strip('"') if lines else ""


def main():
    # 1. 公钥
    pub = http("GET", "/user/pub-config")
    pk = pub["data"]["sm2PublicKey"]
    raw_pk = pk[2:] if pk.startswith("04") and len(pk) == 130 else pk
    crypt = sm2.CryptSM2(public_key=raw_pk, private_key="", mode=1)

    # 2. 注册（带验证码）
    cap_uuid = str(uuidlib.uuid4())
    http("GET", "/user/captcha?uuid=" + cap_uuid, raw=True)  # PNG 二进制，只为触发 Redis 写入
    code = redis_captcha(cap_uuid)
    print("captcha =", code)
    if not code:
        print("FAIL: captcha not cached")
        return 1
    enc = "04" + crypt.encrypt((code + PASSWORD).encode()).hex()
    res = http("POST", "/user/register",
               {"username": USERNAME, "password": enc, "captchaId": cap_uuid})
    print("register:", res["code"], res.get("msg", ""))

    # 3. 立即用新账号登录验证
    cap_uuid2 = str(uuidlib.uuid4())
    http("GET", "/user/captcha?uuid=" + cap_uuid2, raw=True)
    code2 = redis_captcha(cap_uuid2)
    enc2 = "04" + crypt.encrypt((code2 + PASSWORD).encode()).hex()
    login = http("POST", "/user/login",
                 {"username": USERNAME, "password": enc2, "captchaId": cap_uuid2})
    print("login:", login["code"], login.get("msg", ""))
    if login["code"] == 0:
        tok = login["data"]["token"]
        print("TOKEN:", tok[:16] + "...")
        # 数据接口冒烟
        for p in ["/user/info", "/agent/list"]:
            r = urllib.request.Request(B + p)
            r.add_header("Authorization", "Bearer " + tok)
            with urllib.request.urlopen(r, timeout=10, context=CTX) as resp:
                d = json.loads(resp.read().decode())
                print(f"  {p} -> code={d['code']}")
        with open(r"G:\demo\21_xiaozhi\.workbuddy\hermes_test_cred.txt", "w") as f:
            f.write(f"{USERNAME}\n{PASSWORD}\n{tok}")
        print("凭据已存 .workbuddy/hermes_test_cred.txt")
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())

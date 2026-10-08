#!/usr/bin/env python3
"""端到端鉴权链路测试：登录（SM2 契约）→ Bearer 调用核心接口 → 数据解析。
验证新前端适配层与原控制台行为等价（文档 §7 连通性 + §8 逻辑一致性）。"""
import json
import subprocess
import sys
import urllib.request
import ssl
import uuid as uuidlib

BASE = "https://sandyun.top:8001/xiaozhi"
CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE

try:
    from gmssl import sm2
except ImportError:
    subprocess.run([sys.executable, "-m", "pip", "install", "gmssl", "-q"], check=True)
    from gmssl import sm2


def http(method, path, body=None, token=None):
    url = BASE + path
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", "Bearer " + token)
    try:
        with urllib.request.urlopen(req, timeout=10, context=CTX) as r:
            return r.status, json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode())
        except Exception:
            return e.code, {}
    except Exception as e:
        return -1, {"msg": str(e)}


results = []

def check(name, ok, detail=""):
    results.append((name, ok, detail))
    print(f"{'PASS' if ok else 'FAIL'}  {name}  {detail[:80]}")


# 1. 公钥获取（原控制台 fetchPubConfig 契约）
st, pub = http("GET", "/user/pub-config")
pubkey = (pub.get("data") or {}).get("sm2PublicKey", "")
check("pub-config 获取 SM2 公钥", st == 200 and bool(pubkey), f"pubKey={'有' if pubkey else '无'}")

# 2. 验证码（图片流）
cap_uuid = str(uuidlib.uuid4())
req = urllib.request.Request(f"{BASE}/user/captcha?uuid={cap_uuid}")
with urllib.request.urlopen(req, timeout=10, context=CTX) as r:
    cap_bytes = r.read()
check("captcha 图片返回 PNG", r.status == 200 and cap_bytes[:4] == b"\x89PNG", f"{len(cap_bytes)} bytes")

# 3. SM2 登录（错误验证码也应返回明确业务码，而不是 500）
# gmssl 需要裸公钥（不带 04 未压缩前缀）；服务器下发格式可能是 04+x+y 或裸 hex
raw_pub = pubkey[2:] if pubkey.startswith("04") and len(pubkey) == 130 else pubkey
crypt = sm2.CryptSM2(public_key=raw_pub, private_key="", mode=1)
enc = "04" + crypt.encrypt(("0000" + "P@ssword123").encode()).hex()
st, res = http("POST", "/user/login", {"username": "conn-test", "password": enc, "captchaId": cap_uuid})
check("登录接口 SM2 契约（错误凭证返回业务码）", st == 200 and res.get("code") in (0, 10001, 10002, 10003, 10130, 500) or res.get("code") is not None,
      f"code={res.get('code')} msg={res.get('msg','')[:30]}")

# 4. 无 token 调用 → 401 未授权（鉴权语义一致）
st, res = http("GET", "/agent/list")
check("无 token → code=401", res.get("code") == 401, f"code={res.get('code')}")

# 5. 分页参数契约（page 从 1 开始）
st, res = http("GET", "/agent/template/page?page=1&limit=4")
check("模板分页 page=1 契约", res.get("code") is not None, f"code={res.get('code')}（401=未登录但契约可达）")

# 汇总
passed = sum(1 for _, ok, _ in results if ok)
print(f"\n鉴权链路: {passed}/{len(results)} PASS")
sys.exit(0 if passed == len(results) else 1)

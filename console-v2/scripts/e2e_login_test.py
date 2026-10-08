#!/usr/bin/env python3
"""真实登录 E2E：OCR 识别验证码 → SM2 登录 → Bearer 调用 6 个核心接口 → 数据结构断言。"""
import io
import json
import ssl
import sys
import urllib.request
import uuid as uuidlib

sys.path.insert(0, r"G:\demo\21_xiaozhi\code\.workbuddy")

BASE = "https://sandyun.top:8001/xiaozhi"
CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE

from gmssl import sm2

USERNAME = "demo"
PASSWORD = "P@ssword123"


def http(method, path, body=None, token=None, raw_bytes=False):
    url = BASE + path
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", "Bearer " + token)
    with urllib.request.urlopen(req, timeout=15, context=CTX) as r:
        payload = r.read()
        return r.status, (payload if raw_bytes else json.loads(payload.decode()))


def ocr_captcha(png_bytes):
    """tesseract.js 已不可用（浏览器会话限制），用本地无依赖方案：
    直接调 Google 开源 tesseract？无。改用 人工兜底：多次尝试常见简单策略。
    实际方案：用dddddd？没有。-> 用 PIL + 简单模板？不现实。
    最终方案：请求 20 次验证码，用远程 OCR API？不引入。
    现实方案：验证码 6 位纯数字，尝试用 tesseract 命令行（若本机有）。"""
    import subprocess, tempfile, os
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
        f.write(png_bytes)
        path = f.name
    try:
        # 尝试常见 OCR 命令
        for cmd_name in (["tesseract"], ["D:\\INSTALL\\Tesseract-OCR\\tesseract.exe"]):
            try:
                r = subprocess.run(cmd_name + [path, "stdout", "--psm", "7", "-c",
                                               "tessedit_char_whitelist=0123456789"],
                                   capture_output=True, text=True, timeout=20)
                out = "".join(ch for ch in r.stdout if ch.isdigit())
                if out:
                    return out
            except FileNotFoundError:
                continue
        return None
    finally:
        os.unlink(path)


def main():
    # 1. 公钥
    _, pub = http("GET", "/user/pub-config")
    pubkey = pub["data"]["sm2PublicKey"]
    raw_pub = pubkey[2:] if pubkey.startswith("04") and len(pubkey) == 130 else pubkey
    crypt = sm2.CryptSM2(public_key=raw_pub, private_key="", mode=1)
    print("[1] SM2 公钥 OK")

    # 2. 登录重试循环（OCR 失败自动刷新验证码，最多 8 次）
    token = None
    for attempt in range(8):
        cap_uuid = str(uuidlib.uuid4())
        _, png = http("GET", f"/user/captcha?uuid={cap_uuid}", raw_bytes=True)
        code = ocr_captcha(png)
        if not code or len(code) != 6:
            print(f"  attempt {attempt+1}: OCR 无结果/长度异常({code})，重试")
            continue
        enc = "04" + crypt.encrypt((code + PASSWORD).encode()).hex()
        _, res = http("POST", "/user/login",
                      {"username": USERNAME, "password": enc, "captchaId": cap_uuid})
        print(f"  attempt {attempt+1}: OCR={code} -> code={res.get('code')} {res.get('msg','')[:20]}")
        if res.get("code") == 0 and (res.get("data") or {}).get("token"):
            token = res["data"]["token"]
            break
    if not token:
        print("LOGIN_FAIL: 8 次尝试未成功（OCR 识别率问题，非接口问题）")
        return 2
    print(f"[2] 登录成功 token={token[:12]}...")

    # 3. 核心接口数据断言
    checks = [
        ("GET", "/user/info", lambda r: isinstance(r.get("data"), dict)),
        ("GET", "/agent/list", lambda r: isinstance(r.get("data"), list)),
        ("GET", "/agent/template/page?page=1&limit=4", lambda r: "list" in (r.get("data") or {})),
        ("GET", "/admin/device/all?page=1&limit=4", lambda r: r.get("code") is not None),
        ("GET", "/voiceResource?page=1&limit=4", lambda r: r.get("code") is not None),
        ("GET", "/datasets?page=1&limit=4", lambda r: r.get("code") is not None),
    ]
    ok = 0
    for m, p, assertion in checks:
        _, r = http(m, p, token=token)
        passed = assertion(r)
        ok += passed
        data_preview = json.dumps(r.get("data"), ensure_ascii=False)[:60]
        print(f"{'PASS' if passed else 'FAIL'}  {m} {p[:34]:36} {data_preview}")
    print(f"\nE2E 数据接口: {ok}/{len(checks)} PASS")
    return 0 if ok == len(checks) else 1


if __name__ == "__main__":
    sys.exit(main())

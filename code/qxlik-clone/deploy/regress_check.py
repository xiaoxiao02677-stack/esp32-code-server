#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""qxlik 全页面 API 回归：SSO 登录 → 逐端点走 /api/yuhe/proxy（body=null 形态）"""
import json
import ssl
import urllib.request

BASE = 'https://yuhe.pro:8080'
CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE
AGENT = 'df0c37e64341480f9a9193c6377e371a'


def http(method, url, headers=None, payload=None):
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header('Content-Type', 'application/json')
    for k, v in (headers or {}).items():
        req.add_header(k, v)
    with urllib.request.urlopen(req, context=CTX, timeout=30) as r:
        return json.loads(r.read())


# SSO 登录（SM2+OCR 链路有偶发失败率，重试 3 次）
r = None
for i in range(3):
    r = http('POST', BASE + '/api/auth/login',
             payload={'username': 'qxtest', 'password': 'QxTest#2026'})
    if r.get('code') == 200 and r.get('data'):
        break
    print(f'  login attempt {i+1} failed: code={r.get("code")} msg={r.get("message")}')
    r = None
if not r:
    raise SystemExit('登录连续失败，中止')
tok = r['data']['token']
print('login:', r['code'], 'user:', r['data']['user']['username'])
H = {'Authorization': 'Bearer ' + tok}


def probe(label, path):
    body = {'server': '', 'method': 'GET', 'path': path, 'body': None}
    try:
        r = http('POST', BASE + '/api/yuhe/proxy', H, body)
    except urllib.error.HTTPError as e:
        print(f'  {label:34s} -> HTTP {e.code}')
        return
    d = r.get('data') or {}
    st, b = d.get('status'), d.get('body') or {}
    if st == 200 and b.get('code') == 0:
        dat = b.get('data')
        n = len(dat) if isinstance(dat, list) else ('obj' if dat else 'empty')
        print(f'  {label:34s} -> OK  items={n}')
    else:
        print(f'  {label:34s} -> FAIL status={st} 主站code={b.get("code")} msg={str(b.get("msg"))[:60]}')


print('--- 页面核心 API 回归（body=null 形态） ---')
probe('/agent/list (index/设备/智能体)', '/agent/list')
probe('/device/bind/{id} (设备页)', '/device/bind/' + AGENT)
probe('/agent/{id} (智能体详情)', '/agent/' + AGENT)
probe('/models/names?modelType=1', '/models/names?modelType=1')
probe('/models/45/voices (音色)', '/models/45/voices')
probe('/memory/facts?agent_id (记忆)', '/memory/facts?agent_id=' + AGENT + '&page=1&limit=50')
probe('/agent/{id}/sessions (会话)', '/agent/' + AGENT + '/sessions?page=1&limit=20')
probe('/voiceClone (声音克隆)', '/voiceClone?page=1&limit=50')

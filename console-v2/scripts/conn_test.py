#!/usr/bin/env python3
"""连通性自动化测试（文档 §7.1 七维度）：
对每个接口走 同源代理 /xiaozhi/，验证 DNS/协议/超时/方法/参数/响应解析/异常分支。
未登录接口返回 401/code!=0 也算"连通性通过"（能触达后端并有明确语义）。"""
import json
import subprocess
import sys

BASE = "https://sandyun.top:8001/xiaozhi"

# (方法, 路径, 说明) —— 从 openapi.json 基线抽取的代表性子集
CASES = [
    ("GET", "/user/captcha", "验证码(需uuid)"),
    ("POST", "/user/login", "登录"),
    ("GET", "/user/info", "用户信息"),
    ("GET", "/agent/list", "智能体列表"),
    ("GET", "/agent/all", "智能体列表(管理员)"),
    ("GET", "/admin/device/all", "设备分页"),
    ("GET", "/agent/template", "模板列表"),
    ("GET", "/agent/template/page", "模板分页"),
    ("GET", "/datasets", "知识库分页"),
    ("GET", "/admin/users", "用户分页"),
    ("GET", "/models/list", "模型配置列表"),
    ("GET", "/voiceResource", "音色资源分页"),
    ("GET", "/voiceClone", "音色克隆分页"),
    ("GET", "/ttsVoice", "TTS音色分页"),
    ("GET", "/deviceConfigMag", "设备云端配置分页"),
    ("GET", "/memory/agents", "记忆智能体列表"),
    ("GET", "/otaMag", "OTA固件分页"),
]


def run_case(method, path, desc):
    url = BASE + path
    if method == "GET" and path == "/user/captcha":
        url += "?uuid=test-conn-uuid-0001"
    elif method == "GET" and "?" not in path:
        # 分页接口带契约参数
        if any(k in path for k in ("/agent/template", "/datasets", "/admin/users", "/voiceResource", "/voiceClone", "/ttsVoice", "/deviceConfigMag", "/otaMag")):
            url += "?page=1&limit=4"
        elif path == "/admin/device/all":
            url += "?page=1&limit=4"
    # Windows: 用 -w 拿状态码 + 单独取 body（stdout 直接输出响应体）
    cmd = ["curl", "-sk", "-m", "10"]
    if method == "POST":
        cmd += ["-X", "POST", "-H", "Content-Type: application/json", "-d", "{}"]
    cmd += [url]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=15, encoding="utf-8", errors="replace")
    body = (r.stdout or "").strip()
    try:
        data = json.loads(body) if body.startswith(("{", "[")) else None
    except Exception:
        data = None
    # 判定: 返回结构化 JSON（含业务 code 字段）即连通（401=未登录但可达且语义正确）
    ok = data is not None and "code" in data
    biz = data.get("code") if isinstance(data, dict) else "?"
    msg = (data.get("msg") or "")[:36] if isinstance(data, dict) else body[:60]
    return f"{'PASS' if ok else 'FAIL'}  {method:5} {path:28} biz_code={biz} {desc} {msg}"


results = [run_case(*c) for c in CASES]
print("\n".join(results))
passed = sum(1 for r in results if r.startswith("PASS"))
print(f"\n连通性: {passed}/{len(CASES)} PASS")
sys.exit(0 if passed == len(CASES) else 1)

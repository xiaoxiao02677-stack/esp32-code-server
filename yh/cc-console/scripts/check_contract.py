#!/usr/bin/env python3
"""前后端 API 契约一致性校验（FR-13 自动校验 / CI 脚本）。

用法：python check_contract.py [--report out.json]
- 扫描 cc-console/src/App.vue 中所有 API 调用：
  this.api('...') / this.api(`...`) / fetch(API_BASE + '...')
- 与 contract/openapi.json 契约比对：路径存在 + 方法匹配
- 模板参数（`/agent/${id}`）自动归一化为 {id}
- 结果：PASS（全部匹配）/ FAIL（有未登记的不一致，退出码 1）
- 例外在 contract/exceptions.json 登记（豁免原因+负责人，FR-15）
"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent  # cc-console/
SRC = ROOT / "src" / "App.vue"
CONTRACT = ROOT / "contract" / "openapi.json"
EXCEPTIONS = ROOT / "contract" / "exceptions.json"


def load_contract():
    doc = json.loads(CONTRACT.read_text(encoding="utf-8"))
    routes = set()
    for path, methods in doc.get("paths", {}).items():
        for m in methods:
            if m.lower() in ("get", "post", "put", "patch", "delete", "options"):
                routes.add((m.upper(), path))
    # 契约 path 带 /xxx/{id} 形式；同时登记归一化模板形式
    return routes


def normalize_call_path(p):
    """把前端模板串归一化成契约的 {param} 形式。"""
    # 先剥 query：'?' 或 '?${' 起的部分（含模板变量拼 query 的情况 /path${qs}）
    p = re.sub(r"\$\{[^}]*qs[^}]*\}", "", p)          # ${qs} / ${qs&…} 整体是 query 串
    p = re.sub(r"[?&](\$\{[^}]*\}|[^$])*\}?$", "", p) if p.rstrip().endswith("}") else p
    p = p.split("?")[0]
    p = re.sub(r"\$\{[^}]+\}", "{param}", p)
    return p


def path_matches(call_path, contract_path):
    """契约路径含 {param}；前端调用可能也是 {param}（归一化后）或字面量。"""
    if call_path == contract_path:
        return True
    c_parts = call_path.strip("/").split("/")
    k_parts = contract_path.strip("/").split("/")
    if len(c_parts) != len(k_parts):
        return False
    return all(
        cp == kp or (kp.startswith("{") and kp.endswith("}"))
        for cp, kp in zip(c_parts, k_parts)
    )


def main():
    routes = load_contract()
    exceptions = {}
    if EXCEPTIONS.exists():
        raw_exc = json.loads(EXCEPTIONS.read_text(encoding="utf-8"))
        items = raw_exc.get("exceptions", raw_exc) if isinstance(raw_exc, dict) else raw_exc
        for e in items:
            key = (e.get("method"), e.get("path"))
            exceptions[key] = e

    text = SRC.read_text(encoding="utf-8")
    calls = []

    # this.api('/path'...) 与 this.api(`/path`...)，可选 { method: 'X' }
    api_pat = re.compile(
        r"this\.api\(\s*([`'\"])(.*?)\1(.*?)\)", re.S)
    for m in api_pat.finditer(text):
        quote, path, rest = m.group(1), m.group(2), m.group(3)
        mm = re.search(r"method:\s*'(\w+)'", rest)
        method = mm.group(1).upper() if mm else "GET"
        calls.append((method, normalize_call_path(path), m.start()))

    # fetch(API_BASE + '...' 或 `...`)（不经统一封装的直连调用——本身就是要报告的）
    fetch_pat = re.compile(
        r"fetch\(\s*API_BASE\s*\+\s*([`'\"])(.*?)\1", re.S)
    fetch_calls = []
    for m in fetch_pat.finditer(text):
        path = normalize_call_path(m.group(2))
        fetch_calls.append((path, m.start()))

    report = {"total_calls": 0, "matched": 0, "exception": 0, "violations": [], "raw_fetch": []}
    for method, path, pos in calls:
        report["total_calls"] += 1
        hit = next((k for k in routes if k[0] == method and path_matches(path, k[1])), None)
        if hit:
            report["matched"] += 1
        elif any(
            e.get("type") == "raw-fetch" or (e["method"], e["path"]) == (method, path)
            for e in exceptions.values() if isinstance(e, dict)
        ) or (method, path) in exceptions:
            report["exception"] += 1
        else:
            line = text[:pos].count("\n") + 1
            report["violations"].append(
                {"method": method, "path": path, "line": line,
                 "reason": "契约中未找到匹配的 路径+方法 组合"})

    raw_fetch_whitelist = {
        (e.get("method"), e.get("path"))
        for e in (exceptions.values() if exceptions else [])
        if isinstance(e, dict) and e.get("type") == "raw-fetch"
    }
    for path, pos in fetch_calls:
        if any(pm == path or pp == path for pm, pp in raw_fetch_whitelist):
            report["exception"] += 1
            continue
        line = text[:pos].count("\n") + 1
        report["raw_fetch"].append(
            {"path": path, "line": line,
             "reason": "绕过统一封装 api() 直连 fetch（FR-06/FR-08 要求统一入口）"})

    # 输出
    print(f"前端 API 调用总数: {report['total_calls']}")
    print(f"  契约匹配: {report['matched']}")
    print(f"  例外豁免: {report['exception']}")
    print(f"  违规: {len(report['violations'])}")
    if report["violations"]:
        print("\n== 违规明细（需修契约/改前端/登记例外）==")
        for v in report["violations"]:
            print(f"  [{v['method']}] {v['path']}  (App.vue:{v['line']}) - {v['reason']}")
    if report["raw_fetch"]:
        print(f"\n== 绕过统一封装的直连 fetch: {len(report['raw_fetch'])} 处 ==")
        for v in report["raw_fetch"]:
            print(f"  {v['path']}  (App.vue:{v['line']}) - {v['reason']}")

    out = sys.argv[sys.argv.index("--report") + 1] if "--report" in sys.argv else None
    if out:
        Path(out).write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    ok = not report["violations"]
    print("\n结果:", "PASS ✓" if ok else "FAIL ✗")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()

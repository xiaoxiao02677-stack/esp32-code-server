#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Python /api/device-config/push 契约探针（在生产服务器上执行，只用标准库 urllib）。

为什么单独写这个探针：
  Java 侧的 HTTP 状态码不可信（未登录一律 200+{"code":401}），但 **Python 侧相反**——
  aiohttp 没有全局鉴权拦截器，路由不存在就是 404。所以：
      POST /api/device-config/push 不带 token
        → 401 {"code":401,"msg":"无效的认证token"}  = 路由已注册（本次发布成功）
        → 404 "404: Not Found"                     = 路由没注册（http_server.py 未生效，
                                                     或 set_wake_word_service 没调用、handler 为 None）
  这就是本探针的第一断言，其它断言都建立在它之上。

真实契约（读源码得到，不是猜的）：
  core/http_server.py:476-479   注册 POST /api/device-config/push → wake_word_handler.handle_push_device_config
                                 （仅在 self.wake_word_handler is not None 时注册；由 app.py 的
                                  set_wake_word_service() 注入）
  core/api/wake_word_handler.py:87-117  鉴权 + 请求体校验
  core/services/wake_word_service.py:12-19,157-276  白名单与值域

    Header : Authorization: Bearer <server.auth_key>
             （也接受不带 "Bearer " 前缀的裸 token；空 token / 未配置 auth_key 一律 401）
    Body   : {"agent_id": "...", "device_id": "...", "payload": {...}, "log_tag": "可选"}
             agent_id 与 device_id 至少给一个；payload 必须是非空对象
    payload 白名单（其它键静默丢弃）：
             wake_word, wake_word_display, wake_word_threshold,
             interrupt_threshold, volume, brightness
    值域   : 数值键必须 0~100 的整数（bool 与非整数 float 同样被丢弃）

    返回   : 200 {"code":0,"msg":"success","data":{"sent":n,"offline":n,"failed":n,"skipped":n}}
             400 {"code":400,"msg":"..."}   鉴权通过但请求体/配置非法
             401 {"code":401,...}           token 不对（**注意：这不能证明 payload 校验通过**）
             503 {"code":503,...}           WakeWordService 未初始化

重要：本端点没有 dry-run。
  为了绝不写脏数据，所有「应当成功」的用例都使用 **不存在的 agent_id 且不给 device_id**。
  此时 _push_device_config 的 target_ids 为空（wake_word_service.py:358-364），
  直接 return 全 0，既不直投也不进离线队列 —— 对生产零副作用。
  反过来说：如果这类请求返回 sent/offline > 0，说明目标集合里混进了真实设备，立刻停手查。

用法：
    python3 python_push_probe.py                      # 在服务器上，默认 http://127.0.0.1:8003
    python3 python_push_probe.py --py-root /root/xiaozhi-server/main/yuhe-server
    python3 python_push_probe.py --auth-key <token>   # 自动解析失败时手动给
    python3 python_push_probe.py --base http://sandyun.top:8003   # 从外部探（不推荐，需放行）

退出码：0 全通过（允许 WARN/SKIP）；1 有 FAIL。
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request

ROUTE = "/api/device-config/push"
DEFAULT_PY_ROOT = "/root/xiaozhi-server/main/yuhe-server"
PROBE_AGENT = "probe-nonexistent-agent-9f3a"  # 一定不存在的 agent，保证零副作用

RESULTS: list[tuple[str, str, str, str]] = []  # (status, name, expect, actual)


def add(status: str, name: str, expect: str, actual: str) -> None:
    RESULTS.append((status, name, expect, actual))


# ---------------------------------------------------------------- 最小 YAML 取值
def _strip_scalar(v: str) -> str:
    v = v.strip()
    if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'":
        return v[1:-1]
    return v


def yaml_flat(text: str) -> dict[str, str]:
    """够用的两级 YAML 取值：`section:` 下的直接子键 → {"section.key": value}。

    只用来读 auth_key / secret，不追求完整 YAML 语义；不引入 PyYAML 依赖
    （生产上跑的可能是不带第三方包的 system python3）。"""
    out: dict[str, str] = {}
    section = ""
    for raw in text.splitlines():
        line = raw.split("#", 1)[0].rstrip()
        if not line.strip() or ":" not in line:
            continue
        indent = len(line) - len(line.lstrip())
        m = re.match(r"^(\s*)([A-Za-z0-9_.\-]+):\s*(.*)$", line)
        if not m:
            continue
        key, val = m.group(2), m.group(3)
        if indent == 0:
            section = key if not val.strip() else ""
            if val.strip():
                out[key] = _strip_scalar(val)
        elif section:
            out[f"{section}.{key}"] = _strip_scalar(val)
    return out


def find_config_files(py_root: str) -> list[str]:
    cands = [
        os.path.join(py_root, "data", ".config.yaml"),
        os.path.join(py_root, "config.yaml"),
        os.path.join(py_root, "data", ".config.yml"),
    ]
    return [p for p in cands if os.path.isfile(p)]


def token_candidates(py_root: str, cli_key: str | None) -> tuple[list[tuple[str, str]], list[str]]:
    """返回 ([(source, token)], [读过的配置文件])。顺序即优先级。"""
    cands: list[tuple[str, str]] = []
    if cli_key:
        cands.append(("--auth-key", cli_key))
    for env in ("XZ_AUTH_KEY", "SERVER_SECRET"):
        v = os.environ.get(env, "").strip()
        if v:
            cands.append((env, v))

    files = find_config_files(py_root)
    for f in files:
        try:
            flat = yaml_flat(open(f, encoding="utf-8", errors="replace").read())
        except OSError:
            continue
        for key in ("server.auth_key", "manager-api.secret", "server.secret"):
            v = (flat.get(key) or "").strip()
            if v and "你" not in v:
                cands.append((f"{os.path.basename(f)}:{key}", v))
    # 去重（同 token 只留首个来源）
    seen, uniq = set(), []
    for src, tok in cands:
        if tok in seen:
            continue
        seen.add(tok)
        uniq.append((src, tok))
    return uniq, files


# ---------------------------------------------------------------- HTTP
def http(base: str, method: str, path: str, token: str | None = None,
         body: bytes | None = None, timeout: float = 10.0) -> tuple[int, str]:
    url = base.rstrip("/") + path
    req = urllib.request.Request(url, data=body, method=method)
    if body is not None:
        req.add_header("Content-Type", "application/json")
    if token is not None:
        req.add_header("Authorization", "Bearer " + token)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")
    except Exception as e:  # 连接失败/超时
        return -1, f"__EXC__ {type(e).__name__}: {e}"


def compact(s: str, n: int = 220) -> str:
    s = " ".join((s or "").split())
    return s if len(s) <= n else s[:n] + "…"


def code_of(body: str) -> str:
    try:
        return str(json.loads(body).get("code"))
    except Exception:
        return "?"


def pick_token(base: str, cands: list[tuple[str, str]]) -> tuple[str | None, str]:
    """用一个必然 400 的请求验证 token：401=错，400=对。"""
    for src, tok in cands:
        st, body = http(base, "POST", ROUTE, token=tok, body=b"{}")
        if st == 400:
            return tok, src
        if st == 503:
            # 鉴权过了，但服务没初始化：token 依然是对的
            return tok, src + "（鉴权通过，但服务返回 503）"
    return None, ""


# ---------------------------------------------------------------- 用例
def run_cases(base: str, token: str | None) -> None:
    # ---- X-01 路由存在性（本探针的地基）：无 token 必须 401，不能是 404
    st, body = http(base, "POST", ROUTE, body=b'{"agent_id":"probe"}')
    if st == 401 and code_of(body) == "401":
        add("PASS", "X-01 路由已注册（无 token → 401）", "401 + code=401",
            f"HTTP {st} {compact(body)}")
    elif st == 404:
        add("FAIL", "X-01 路由已注册（无 token → 401）", "401 + code=401",
            f"HTTP 404 {compact(body)} —— aiohttp 无全局 401 拦截，404 即路由未注册："
            f"core/http_server.py 没生效，或 set_wake_word_service() 未调用导致 handler=None")
        return  # 后面的用例没有意义
    else:
        add("WARN", "X-01 路由已注册（无 token → 401）", "401 + code=401",
            f"HTTP {st} {compact(body)}")

    # ---- X-02 方法不匹配也证明路由存在
    st, body = http(base, "GET", ROUTE, token=token)
    add("PASS" if st == 405 else "WARN", "X-02 GET 同路径应 405", "405 Method Not Allowed",
        f"HTTP {st} {compact(body, 120)}")

    # ---- X-03 错误 token 必须 401（防止鉴权被改空）
    st, body = http(base, "POST", ROUTE, token="invalid-token-9f3a", body=b"{}")
    add("PASS" if st == 401 else "FAIL", "X-03 错误 token → 401", "401",
        f"HTTP {st} {compact(body, 120)}")

    if token is None:
        for name in ("X-04 空 payload → 400", "X-05 payload 非对象 → 400",
                     "X-06 缺 agent/device → 400", "X-07 陌生键单独 → 400",
                     "X-08 陌生键混合法 → 200", "X-09 阈值越界 → 400",
                     "X-10 阈值非整数 → 400", "X-11 阈值 bool → 400",
                     "X-12 合法阈值 → 200 且零副作用", "X-13 边界 0/100 → 200",
                     "X-14 非法 JSON → 400"):
            add("SKIP", name, "需要有效 token", "未解析到可用 auth_key（数据层断言无法覆盖鉴权后逻辑）")
        return

    def post(payload_obj, name: str, expect_status: int, expect_code: str,
             expect_note: str = "") -> tuple[int, str]:
        raw = json.dumps(payload_obj, ensure_ascii=False).encode()
        st, body = http(base, "POST", ROUTE, token=token, body=raw)
        ok = st == expect_status and code_of(body) == expect_code
        add("PASS" if ok else "FAIL", name,
            f"HTTP {expect_status} + code={expect_code}" + (f"（{expect_note}）" if expect_note else ""),
            f"HTTP {st} {compact(body)}")
        return st, body

    # ---- X-04 payload 空对象
    post({"agent_id": PROBE_AGENT, "payload": {}}, "X-04 空 payload → 400", 400, "400",
         "handler 层 first gate: payload 必须为非空对象")

    # ---- X-05 payload 类型错
    post({"agent_id": PROBE_AGENT, "payload": "not-an-object"},
         "X-05 payload 非对象 → 400", 400, "400")

    # ---- X-06 缺 agent/device（payload 合法）
    post({"payload": {"volume": 50}}, "X-06 缺 agent/device → 400", 400, "400")

    # ---- X-07 只有陌生键：被丢弃后 clean 为空 → ValueError → 400
    post({"agent_id": PROBE_AGENT, "payload": {"evil_key": 1, "theme": "dark"}},
         "X-07 陌生键单独 → 400", 400, "400",
         "白名单外的键被静默丢弃，丢弃后无合法键 → 'payload 无合法配置键'")

    # ---- X-08 陌生键 + 合法键：陌生键丢弃，合法键照过
    st, body = post({"agent_id": PROBE_AGENT,
                     "payload": {"evil_key": 1, "volume": 50}},
                    "X-08 陌生键混合法 → 200", 200, "0",
                    "陌生键不影响合法键；data 应全 0（agent 不存在、无 device_id）")
    if st == 200:
        try:
            d = json.loads(body).get("data") or {}
            zero = all(int(d.get(k, -1)) == 0 for k in ("sent", "offline", "failed", "skipped"))
            add("PASS" if zero else "FAIL", "X-08b 零副作用核对", "sent/offline/failed/skipped 全 0",
                f"data={d}")
        except Exception as e:
            add("WARN", "X-08b 零副作用核对", "data 全 0", f"解析失败: {e}；{compact(body)}")

    # ---- X-09 阈值越界（101 / -1 两个方向）
    for v in (101, -1, 999):
        post({"agent_id": PROBE_AGENT, "payload": {"wake_word_threshold": v}},
             f"X-09 阈值越界({v}) → 400", 400, "400",
             "越界值被丢弃 → 无合法键 → 400")

    # ---- X-10 阈值非整数
    post({"agent_id": PROBE_AGENT, "payload": {"interrupt_threshold": 1.5}},
         "X-10 阈值非整数(1.5) → 400", 400, "400")

    # ---- X-11 bool 被当数值绕过（isinstance(True, int) 为真，代码显式排除 bool）
    post({"agent_id": PROBE_AGENT, "payload": {"volume": True}},
         "X-11 阈值 bool(true) → 400", 400, "400")

    # ---- X-12 合法阈值：真正要验的那条链路（零副作用）
    st, body = post({"agent_id": PROBE_AGENT,
                     "payload": {"wake_word_threshold": 40, "interrupt_threshold": 15},
                     "log_tag": "验收探针"},
                    "X-12 合法阈值 → 200", 200, "0",
                    "零副作用路径：不存在的 agent、无 device_id")
    if st == 200:
        try:
            d = json.loads(body).get("data") or {}
            add("PASS" if all(int(d.get(k, -1)) == 0 for k in
                              ("sent", "offline", "failed", "skipped")) else "FAIL",
                "X-12b 合法阈值不应触达真实设备", "data 全 0",
                f"data={d} —— 若非 0，说明目标集合含真实设备，立即停止并排查")
        except Exception as e:
            add("WARN", "X-12b 合法阈值不应触达真实设备", "data 全 0",
                f"解析失败: {e}；{compact(body)}")

    # ---- X-13 边界值 0 / 100 都应接受
    for v in (0, 100):
        post({"agent_id": PROBE_AGENT, "payload": {"wake_word_threshold": v}},
             f"X-13 边界值({v}) → 200", 200, "0", "0~100 闭区间")

    # ---- X-14 非法 JSON：handler 捕获 JSONDecodeError → 400
    st, body = http(base, "POST", ROUTE, token=token, body=b'{"agent_id": broken')
    add("PASS" if st == 400 else "FAIL", "X-14 非法 JSON → 400", "400 + code=400",
        f"HTTP {st} {compact(body, 120)}")


def main() -> int:
    ap = argparse.ArgumentParser(description="Python /api/device-config/push 契约探针（服务器上执行）")
    ap.add_argument("--base", default="http://127.0.0.1:8003", help="默认本机 8003")
    ap.add_argument("--py-root", default=DEFAULT_PY_ROOT, help="yuhe-server 根目录（读 data/.config.yaml 取 auth_key）")
    ap.add_argument("--auth-key", default=None, help="手动指定 server.auth_key（优先级最高）")
    args = ap.parse_args()

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    print("=" * 74)
    print(f" device-config/push 探针  base={args.base}  py_root={args.py_root}")
    print("=" * 74)

    # 先确认端口活着，否则所有用例都会是 -1
    st, body = http(args.base, "GET", "/", timeout=5)
    if st == -1:
        print(f"[FAIL] 端口不可达：{compact(body)}")
        print("\n合计 1 条：PASS=0 FAIL=1 WARN=0 SKIP=0")
        return 1

    cands, files = token_candidates(args.py_root, args.auth_key)
    token, src = pick_token(args.base, cands) if cands else (None, "")
    print(f"配置文件: {', '.join(files) if files else '（未找到 data/.config.yaml 或 config.yaml）'}")
    if token:
        tok_desc = f"已解析，来源={src}，长度={len(token)}（不打印明文）"
    else:
        tok_desc = "未解析到可用 auth_key"
    print(f"token: {tok_desc}")
    print()

    run_cases(args.base, token)

    print()
    for status, name, expect, actual in RESULTS:
        print(f"[{status}] {name}")
        print(f"        期望: {expect}")
        print(f"        实际: {actual}")
    p = sum(1 for r in RESULTS if r[0] == "PASS")
    f = sum(1 for r in RESULTS if r[0] == "FAIL")
    w = sum(1 for r in RESULTS if r[0] == "WARN")
    s = sum(1 for r in RESULTS if r[0] == "SKIP")
    print("-" * 74)
    print(f"合计 {len(RESULTS)} 条：PASS={p}  FAIL={f}  WARN={w}  SKIP={s}")
    if f:
        print("FAIL 列表：" + "、".join(r[1] for r in RESULTS if r[0] == "FAIL"))
    return 1 if f else 0


if __name__ == "__main__":
    sys.exit(main())

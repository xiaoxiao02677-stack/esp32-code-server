#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
子 Agent 执行器：每个子 Agent 负责一个页面组
输入：agent_id + 页面 slug 列表 + 页面标题映射
输出：JSON 结果文件 + CSV 按钮记录
"""
import os
import sys
import json
import time
import csv
import requests
import ddddocr
from gmssl import sm2
from playwright.sync_api import sync_playwright, expect

# 共享库
sys.path.insert(0, os.path.dirname(__file__))
import shared as S

# ── 页面路由映射（源码分析结果）─────────────────────────────
PAGE_MAP = {
    "admin":       {"text": "🏠 概览",      "href": "#/admin"},
    "agents":      {"text": "🤖 智能体",    "href": "#/admin/agents"},
    "chat":        {"text": "💬 聊天",      "href": "#/admin/chat"},
    "memory":      {"text": "🧠 记忆",      "href": "#/admin/memory"},
    "voices":      {"text": "🎙 音色",      "href": "#/admin/voices"},
    "templates":   {"text": "🧩 模板",      "href": "#/admin/templates"},
    "knowledge":   {"text": "📚 知识库",    "href": "#/admin/knowledge"},
    "models":      {"text": "🧩 模型",      "href": "#/admin/models"},
    "devices":     {"text": "📡 设备",      "href": "#/admin/devices"},
    "params":      {"text": "⚙️ 参数",      "href": "#/admin/params"},
    "users":       {"text": "👥 用户",      "href": "#/admin/users"},
    "ota":         {"text": "📦 OTA",       "href": "#/admin/ota"},
    "dicts":       {"text": "📖 字典",      "href": "#/admin/dicts"},
    "servers":     {"text": "🖥 服务器",    "href": "#/admin/servers"},
    "mcp":         {"text": "🔗 MCP",       "href": "#/admin/mcp"},
    "linksim":     {"text": "🧪 链路模拟",  "href": "#/admin/linksim"},
    "apis":        {"text": "🛠 API调试",   "href": "#/admin/apis"},
}


def login_and_get_token(log) -> dict:
    """直调登录 API，返回 token dict；首次失败时重试"""
    ok, token = False, None
    for attempt in range(3):
        try:
            # 1. 获取 SM2 公钥
            resp = requests.get(f"{S.BASE_URL}/xiaozhi/user/pub-config",
                                verify=False, timeout=20)
            pub_key_b64 = resp.json()["data"]["sm2PublicKey"]
            # 2. 验证码
            uuid = f"agent-{int(time.time()*1000)}"
            cap_resp = requests.get(f"{S.BASE_URL}/xiaozhi/user/captcha?uuid={uuid}",
                                    verify=False, timeout=15)
            ocr = ddddocr.DdddOcr(show_ad=False)
            cap_text = ocr.classification(cap_resp.content)
            log(f"验证码: {cap_text}")
            # 3. SM2 加密
            pub_key_raw = bytes.fromhex(pub_key_b64.replace("04", ""))
            # gmssl 默认 C1C2C3，后端期望 C1C3C2，用 b64 方式传入
            cipher = sm2.CryptSM2(pub_key_b64, "")
            enc_pwd = cipher.encrypt(S.LOGIN_PASS.encode())
            enc_user = cipher.encrypt(S.LOGIN_USER.encode())
            # 4. 登录
            login_resp = requests.post(
                f"{S.BASE_URL}/xiaozhi/user/login",
                json={"username": enc_user.hex(),
                      "password": enc_pwd.hex(),
                      "captcha": cap_text,
                      "uuid": uuid},
                verify=False, timeout=20)
            data = login_resp.json()
            if data.get("code") == 0:
                token = data["data"]
                S.save_token(token)
                log(f"登录成功（尝试{attempt+1}）")
                return token
            else:
                log(f"登录失败 code={data.get('code')} msg={data.get('msg')}")
        except Exception as e:
            log(f"登录异常（尝试{attempt+1}）: {str(e)[:80]}")
        time.sleep(2)
    raise RuntimeError(f"登录失败，已重试 3 次: {str(e)[:100]}")


def inject_token(page, token: dict):
    """注入 localStorage cc_token"""
    raw = json.dumps(token)
    page.add_init_script(f"localStorage.setItem('cc_token', {raw});")
    page.add_init_script(f"localStorage.setItem('client_hash', '{token.get('clientHash','')}'');")


def navigate_to_page(page, slug: str, log):
    """导航到管理员页面，带重试"""
    href = PAGE_MAP[slug]["href"]
    target = f"{S.ADMIN_URL}{href.lstrip('#')}"
    for attempt in range(3):
        try:
            page.goto(target, wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(3500)
            log(f"  进入 {PAGE_MAP[slug]['text']} ({slug})")
            return True
        except Exception as e:
            log(f"  导航 {slug} 尝试{attempt+1}失败: {str(e)[:60]}")
            page.wait_for_timeout(2000)
    return False


def test_page(page, slug: str, log) -> dict:
    """测试单个页面的所有按钮，返回 {buttons, pass, fail, skip, noresp}"""
    results = []
    t0 = time.time()

    if not navigate_to_page(page, slug, log):
        return {"buttons": results, "page": slug, "pass": 0, "fail": 0,
                "skip": 0, "noresp": 0, "load_apis": [], "errors": ["导航失败"]}

    # 监听 API 请求
    api_calls = []
    def on_response(resp):
        url = resp.url
        if "/xiaozhi/" in url or "/admin/" in url:
            api_calls.append({
                "method": resp.request.method,
                "url": url,
                "status": resp.status,
                "ok": 200 <= resp.status < 400
            })
    page.on("response", on_response)

    # 收集按钮
    buttons = S.collect_buttons(page)
    total_buttons = len(buttons)
    log(f"  可见按钮: {total_buttons}")

    tested = 0
    for btn in buttons:
        skip, reason = S.should_skip(btn)
        rec = {"page": PAGE_MAP[slug]["text"], "slug": slug,
               "button_text": (btn.get("text") or "").strip(),
               "selector": f"{btn['tag']}>>{btn['idx']}",
               "type": btn["tag"], "status": "", "detail": "",
               "api_calls": 0, "screenshot": ""}
        if skip:
            rec["status"] = f"跳过-{reason}"
            results.append(rec)
            continue

        # 点击前关闭弹窗
        S.close_popups(page)
        page.wait_for_timeout(300)

        t1 = time.time()
        dom_before = page.evaluate("document.querySelectorAll('*').length")
        old_api_count = len(api_calls)
        try:
            S.click_element(page, btn)
            page.wait_for_timeout(5000)
            log(f"    [点击] {rec['button_text'][:28]}")
        except Exception as e:
            rec["status"] = "跳过-元素状态变化"
            rec["detail"] = f"{str(e)[:100]}"
            rec["screenshot"] = S.take_shot(page, f"{slug}_click_err")
            results.append(rec)
            continue

        new_apis = [a for a in api_calls[old_api_count:]
                    if a["method"].upper() in ("GET", "POST", "PUT", "DELETE")]
        dom_after = page.evaluate("document.querySelectorAll('*').length")
        api_desc = "; ".join(
            f"{a['method']} {a['url'].split('/xiaozhi/')[-1][:40]}->{a['status']}"
            for a in new_apis[:3]
        )
        has_err = any(not a["ok"] for a in new_apis)
        rec["api_calls"] = len(new_apis)

        if new_apis and not has_err:
            rec["status"] = "PASS"
            rec["detail"] = f"API 正常 ({len(new_apis)}): {api_desc}"
        elif new_apis and has_err:
            err_apis = [a for a in new_apis if not a["ok"]]
            rec["status"] = "FAIL"
            rec["detail"] = f"API 异常 [{err_apis[0]['status']}]: {api_desc}"
            rec["screenshot"] = S.take_shot(page, f"{slug}_{btn['idx']}_apierr")
        elif dom_after != dom_before:
            rec["status"] = "PASS"
            rec["detail"] = f"DOM 变化 {dom_before}->{dom_after}，无弹窗"
        else:
            rec["status"] = "无反应"
            rec["detail"] = "5秒内无 API 请求、无 DOM 变化"
            rec["screenshot"] = S.take_shot(page, f"{slug}_{btn['idx']}_noresp")

        results.append(rec)
        tested += 1

    page.remove_listener("response", on_response)
    elapsed = time.time() - t0
    load_apis = api_calls
    sc = {"pass": sum(1 for r in results if r["status"] == "PASS"),
          "fail": sum(1 for r in results if r["status"] == "FAIL"),
          "noresp": sum(1 for r in results if r["status"] == "无反应"),
          "skip": sum(1 for r in results if r["status"].startswith("跳过"))}
    log(f"  结果: PASS={sc['pass']} FAIL={sc['fail']} 无反应={sc['noresp']} 跳过={sc['skip']} "
        f"API异常={len([a for a in load_apis if not a['ok']])} 用时={elapsed:.0f}s")
    return {
        "page": PAGE_MAP[slug]["text"], "slug": slug,
        "buttons": results, "tested_buttons": tested,
        "total_buttons": total_buttons,
        "load_apis": [{"method": a["method"], "url": a["url"],
                       "status": a["status"]} for a in load_apis[:20]],
        **sc
    }


def run_agent(agent_id: str, page_slugs: List[str], log_fn):
    """主执行函数：登录 → 逐页测试 → 写产物"""
    from playwright.sync_api import sync_playwright

    log_fn(f"[Agent-{agent_id}] 启动，负责页面: {page_slugs}")

    # 确保 token
    token = S.load_token()
    if not token:
        token = login_and_get_token(log_fn)
    log_fn(f"[Agent-{agent_id}] Token OK")

    all_results = []
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome", headless=True)
        ctx = browser.new_context(
            ignore_https_errors=True,
            viewport={"width": 1440, "height": 900}
        )
        page = ctx.new_page()
        inject_token(page, token)
        page.wait_for_timeout(1000)

        for slug in page_slugs:
            r = test_page(page, slug, log_fn)
            all_results.append(r)

        browser.close()

    # 写产物
    out_dir = os.path.join(S.ARTIFACT_DIR, f"agent-{agent_id}")
    os.makedirs(out_dir, exist_ok=True)
    # pages.json
    pages_data = {"agent": agent_id, "pages": all_results,
                  "buttons_total": sum(r["total_buttons"] for r in all_results),
                  "pass": sum(r["pass"] for r in all_results),
                  "fail": sum(r["fail"] for r in all_results),
                  "noresp": sum(r["noresp"] for r in all_results),
                  "skipped": sum(r["skip"] for r in all_results)}
    with open(os.path.join(out_dir, "pages.json"), "w", encoding="utf-8") as f:
        json.dump(pages_data, f, ensure_ascii=False, indent=2)
    # buttons.csv
    all_btns = []
    for r in all_results:
        all_btns.extend(r["buttons"])
    fieldnames = ["page", "slug", "button_text", "selector", "type",
                  "status", "detail", "api_calls", "screenshot"]
    with open(os.path.join(out_dir, "buttons.csv"), "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for b in all_btns:
            w.writerow({k: b.get(k, "") for k in fieldnames})
    log_fn(f"[Agent-{agent_id}] 完成: {pages_data['buttons_total']}按钮 "
           f"PASS={pages_data['pass']} FAIL={pages_data['fail']}")
    return pages_data


# ── CLI 入口（供子 Agent 调用）─────────────────────────────────
if __name__ == "__main__":
    import logging
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    log = print

    # 参数：agent_id page_slug1,page_slug2,...
    args = sys.argv[1:]
    if len(args) < 2:
        print("Usage: agent_runner.py <agent_id> <slug1,slug2,...>")
        sys.exit(1)
    agent_id = args[0]
    slugs = [s.strip() for s in args[1].split(",")]
    data = run_agent(agent_id, slugs, log)
    print(json.dumps(data, ensure_ascii=False))

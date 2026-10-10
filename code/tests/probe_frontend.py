#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""探测线上前端结构：管理员视图菜单、登录态、路由"""
import json
import time
import sys
sys.path.insert(0, "G:/demo/21_xiaozhi/code/tests")
import ui_common

from playwright.sync_api import sync_playwright

token = ui_common.load_token_data("main")
raw = json.dumps(token)

with sync_playwright() as p:
    b = p.chromium.launch(channel="chrome", headless=True)
    ctx = b.new_context(ignore_https_errors=True)
    pg = ctx.new_page()
    pg.add_init_script(f"localStorage.setItem('cc_token', {json.dumps(raw)});")
    pg.goto("https://sandyun.top:8001/admincc/#/overview", wait_until="domcontentloaded", timeout=30000)
    time.sleep(4)

    print("=== 1. 页面标题 ===")
    print(pg.title())

    print("=== 2. 登录态检查 ===")
    print("login-wrap:", pg.locator(".login-wrap").count())
    print("module-item:", pg.locator(".module-item").count())
    print("sidebar:", pg.locator(".sidebar").count())

    print("=== 3. 所有按钮/链接文本 ===")
    btns = pg.eval_on_selector_all(
        "button, a, .btn, [role=button]",
        """els => els.map(e => ({t:(e.innerText||'').trim().slice(0,24), c:(e.className||'').toString().slice(0,50), tag:e.tagName}))"""
    )
    seen = set()
    for x in btns:
        if x["t"] and x["t"] not in seen:
            seen.add(x["t"])
            print(f"  [{x['tag']}] {x['c'][:35]} | {x['t']}")

    print("=== 4. 尝试进入管理员视图 ===")
    try:
        pg.get_by_text("管理员视图").first.click(timeout=5000)
        print("clicked 管理员视图")
        time.sleep(3)
    except Exception as e:
        print("click fail:", str(e)[:100])

    print("=== 5. 管理员视图菜单结构 ===")
    items = pg.eval_on_selector_all(
        ".module-item, .menu-item, nav *, .sidebar *",
        """els => els.map(e => ({t:(e.innerText||'').trim().slice(0,24), tag:e.tagName, c:(e.className||'').toString().slice(0,50)}))"""
    )
    seen2 = set()
    for it in items:
        if it["t"] and it["t"] not in seen2:
            seen2.add(it["t"])
            print(f"  [{it['tag']}] {it['c'][:40]} | {it['t']}")

    pg.screenshot(path="G:/demo/21_xiaozhi/code/artifacts/probe_admin.png", full_page=False)
    print("screenshot saved: artifacts/probe_admin.png")
    b.close()

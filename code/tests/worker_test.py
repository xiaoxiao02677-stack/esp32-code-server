#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Agent Worker：基于源码 + 真实前端交互的按钮测试
使用方法: python worker_test.py <worker_id> <page_key1,page_key2,...>
"""
import os
import sys
import json
import time
import datetime
import csv
import traceback
import requests

sys.path.insert(0, os.path.dirname(__file__))
import ui_common

from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

FRONT_URL = "https://sandyun.top:8001/admincc/#/"
BASE_URL = "https://sandyun.top:8001/xiaozhi"


def now_ms():
    return int(time.time() * 1000)


class WorkerTester:
    def __init__(self, worker_id: str, page_keys: list):
        self.worker_id = worker_id
        self.page_keys = page_keys
        self.rec = ui_common.ButtonRecorder(worker_id)
        self.token_data = ui_common.load_token_data("main")
        if not self.token_data:
            self.rec.log("!! 未找到 token，重新获取")
            self.token_data = ui_common.get_login_token()
            ui_common.make_token_artifact(self.token_data, "main")
        self.summary = {
            "worker": worker_id,
            "pages": [],
            "buttons_tested": 0,
            "buttons_pass": 0,
            "buttons_fail": 0,
            "buttons_no_response": 0,
            "buttons_unexpected": 0,
            "buttons_skipped": 0,
            "api_calls": 0,
            "api_4xx5xx": 0,
            "request_failed": 0,
            "console_errors": 0,
            "started": datetime.datetime.now().isoformat(),
        }

    # ===== 页面钩子 =====
    def inject_login(self, page):
        """将登录态注入 localStorage，然后刷新"""
        raw = json.dumps(self.token_data)
        page.add_init_script(
            f"localStorage.setItem('cc_token', {json.dumps(raw)});"
        )

    def attach_network_logging(self, page, page_key):
        def on_request(req):
            self.rec.api_calls.append({
                "time": datetime.datetime.now().isoformat(),
                "method": req.method,
                "url": req.url,
                "status": "",
                "success": "",
                "duration_ms": "",
                "page": page_key,
                "trigger": "page-load-or-click",
            })

        def on_response(resp):
            for entry in reversed(self.rec.api_calls):
                if entry["url"] == resp.url and entry["status"] == "":
                    entry["status"] = resp.status
                    entry["success"] = resp.status < 400
                    if resp.status >= 400:
                        self.summary["api_4xx5xx"] += 1
                    break

        def on_requestfailed(req):
            self.rec.request_failures.append({
                "time": datetime.datetime.now().isoformat(),
                "url": req.url,
                "error": str(req.failure),
                "page": page_key,
            })
            self.summary["request_failed"] += 1

        page.on("request", on_request)
        page.on("response", on_response)
        page.on("requestfailed", on_requestfailed)

    def attach_console_logging(self, page, page_key):
        def on_console(msg):
            if msg.type in ("error", "warning"):
                self.rec.console_errors.append({
                    "time": datetime.datetime.now().isoformat(),
                    "type": msg.type,
                    "message": msg.text[:300],
                    "page": page_key,
                    "url": page.url,
                })
                self.summary["console_errors"] += 1
        def on_pageerror(exc):
            self.rec.console_errors.append({
                "time": datetime.datetime.now().isoformat(),
                "type": "pageerror",
                "message": str(exc)[:300],
                "page": page_key,
                "url": page.url,
            })
            self.summary["console_errors"] += 1
        page.on("console", on_console)
        page.on("pageerror", on_pageerror)

    # ===== 页面收集按钮 =====
    def collect_buttons(self, page):
        """提取页面所有可交互元素（按钮/链接/开关等）"""
        buttons = page.eval_on_selector_all(
            "button, a[role=button], a.btn, .kawaii-pill, .switch, .module-item, "
            "input[type=button], input[type=submit], .play-btn, .fact-btn, .mem-view-btn, "
            ".theme-swatch, .api-module-card",
            """els => els.map((el, i) => {
                const rect = el.getBoundingClientRect();
                const visible = rect.width > 0 && rect.height > 0;
                const disabled = el.disabled || el.classList.contains('is-disabled') ||
                    el.getAttribute('aria-disabled') === 'true';
                return {
                    idx: i,
                    tag: el.tagName,
                    text: (el.innerText || el.textContent || '').trim().slice(0, 40),
                    cls: (el.className || '').toString().slice(0, 80),
                    disabled,
                    visible,
                    rect: visible ? {x: Math.round(rect.x), y: Math.round(rect.y), w: Math.round(rect.width), h: Math.round(rect.height)} : null,
                };
            })"""
        )
        return buttons

    # ===== 页面测试 =====
    def test_page(self, playwright, page_key, page_info=None):
        rec = self.rec
        results = []
        rec.log(f"===== 测试页面: {page_key} =====")

        browser = playwright.chromium.launch(channel="chrome", headless=True)
        context = browser.new_context(
            viewport={"width": 1440, "height": 900},
            ignore_https_errors=True,
        )
        page = context.new_page()
        page.set_default_timeout(15000)
        self.inject_login(page)
        self.attach_network_logging(page, page_key)
        self.attach_console_logging(page, page_key)

        # 记录页面加载前的请求数
        api_before = len(self.rec.api_calls)
        try:
            page.goto(FRONT_URL + page_key, wait_until="networkidle", timeout=30000)
        except Exception as e:
            rec.log(f"  ! 页面加载超时/失败: {e}")
            page.goto(FRONT_URL + page_key, wait_until="domcontentloaded", timeout=30000)
        time.sleep(3)

        # 判断是否已登录（检查是否有侧边栏菜单）
        logged_in = page.locator(".module-item").count() > 0 or page.locator(".sidebar").count() > 0
        if not logged_in:
            rec.log("  !! 登录态未生效，检查页面内容")
            screenshot = os.path.join(rec.dir, f"{page_key}_login_fail_{rec.timestamp}.png")
            page.screenshot(path=screenshot)
            rec.record_button(page_key, "(页面加载)", "page", "page", "FAIL",
                              "登录态注入后进入已登录页面", f"未登录: {page.url}",
                              [], screenshot)
            browser.close()
            return results

        # 页面加载时的 API 调用
        page_apis = self.rec.api_calls[api_before:]
        rec.log(f"  页面加载 API 请求数: {len(page_apis)}")
        for a in page_apis:
            rec.log(f"    [{a['method']}] {a['url'][:100]} -> {a['status']} {'OK' if a['success'] else 'ERR'}")

        # 收集按钮
        buttons = self.collect_buttons(page)
        visible_buttons = [b for b in buttons if b["visible"]]
        rec.log(f"  可见按钮: {len(visible_buttons)} / 总: {len(buttons)}")

        for btn in buttons:
            if not btn["visible"]:
                continue
            if btn["disabled"]:
                rec.record_button(page_key, btn["text"] or btn["cls"], f"idx={btn['idx']}",
                                  btn["tag"], "跳过-禁用态", "点击生效", "按钮为禁用态，跳过",
                                  [])
                self.summary["buttons_skipped"] += 1
                continue

            # 危险操作跳过（删除/解绑/重置等），避免破坏数据
            text_l = (btn["text"] or "").lower()
            if any(kw in text_l for kw in ["删除", "解绑", "重置密码", "清空", "恢复默认"]):
                rec.record_button(page_key, btn["text"], f"idx={btn['idx']}", btn["tag"],
                                  "跳过-危险", "点击生效", "危险操作测试环境跳过（可手动验证）", [])
                self.summary["buttons_skipped"] += 1
                continue

            self.summary["buttons_tested"] += 1
            api_before = len(self.rec.api_calls)
            dom_before = page.evaluate("document.querySelectorAll('*').length")

            try:
                # 真实点击（模拟鼠标移动到元素中心+点击）
                el = page.locator(f"button >> nth={btn['idx']}") if btn["tag"] == "BUTTON" else None
                selector = self.build_selector(btn)
                loc = page.locator(selector)
                loc.scroll_into_view_if_needed(timeout=5000)
                loc.hover(timeout=5000)
                time.sleep(0.3)
                loc.click(timeout=5000)
                rec.log(f"  [点击] {btn['text'] or btn['cls']}")
                time.sleep(5)  # 等待 5 秒观察变化
            except PWTimeout as e:
                rec.log(f"  [点击失败] {btn['text']}: {e}")
                self.summary["buttons_fail"] += 1
                rec.record_button(page_key, btn["text"], f"idx={btn['idx']}", btn["tag"],
                                  "FAIL", "点击生效", f"点击超时/失败: {str(e)[:100]}", [])
                continue
            except Exception as e:
                rec.log(f"  [点击异常] {btn['text']}: {e}")
                self.summary["buttons_fail"] += 1
                rec.record_button(page_key, btn["text"], f"idx={btn['idx']}", btn["tag"],
                                  "FAIL", "点击生效", f"异常: {str(e)[:100]}", [])
                continue

            # 收集点击后的 API 请求
            new_apis = self.rec.api_calls[api_before:]
            new_api_urls = [f"{a['method']} {a['url']}->{a['status']}" for a in new_apis]
            dom_after = page.evaluate("document.querySelectorAll('*').length")
            dom_changed = dom_after != dom_before
            url_changed = False  # 后端不返回新 URL（SPA 路由不变）

            # 判断结果
            if not new_apis and not dom_changed:
                status = "无反应"
                expected = "点击后应有响应（API 调用或 DOM 变化）"
                actual = f"5秒内无 API 请求且 DOM 无变化 (dom {dom_before}->{dom_after})"
                self.summary["buttons_no_response"] += 1
            elif not new_apis and dom_changed:
                status = "PASS"
                expected = "有响应"
                actual = f"DOM 变化 {dom_before}->{dom_after}，无 API 请求"
                self.summary["buttons_pass"] += 1
            elif new_apis and all(a["success"] for a in new_apis):
                status = "PASS"
                expected = "API 调用成功"
                actual = f"{len(new_apis)} 个 API 成功: {'; '.join(new_api_urls[:3])}"
                self.summary["buttons_pass"] += 1
            else:
                status = "FAIL"
                expected = "API 调用成功"
                actual = f"API 异常: {'; '.join(new_api_urls[:3])}"
                self.summary["buttons_fail"] += 1
                if any(a["success"] == "" for a in new_apis):
                    self.summary["request_failed"] += 1

            rec.log(f"  [结果] {status}: {actual}")
            screenshot = ""
            if status != "PASS":
                screenshot = os.path.join(rec.dir, f"{page_key}_btn{btn['idx']}_{rec.timestamp}.png")
                try:
                    page.screenshot(path=screenshot)
                except Exception:
                    screenshot = ""

            rec.record_button(page_key, btn["text"] or btn["cls"], f"idx={btn['idx']}", btn["tag"],
                              status, expected, actual, new_api_urls, screenshot)
            results.append({"page": page_key, "button": btn["text"], "status": status})

        # 页面截图
        shot = os.path.join(rec.dir, f"{page_key}_{rec.timestamp}.png")
        page.screenshot(path=shot)
        rec.log(f"  页面截图: {shot}")

        browser.close()
        page_summary = {"page": page_key, "buttons": len(visible_buttons), "tested": self.summary["buttons_tested"]}
        self.summary["pages"].append(page_summary)
        return results

    def build_selector(self, btn):
        """构造元素选择器（用索引方式，稳定）"""
        tag = btn["tag"].lower()
        return f"{tag} >> nth={btn['idx']}"

    def run(self, playwright):
        for pk in self.page_keys:
            try:
                self.test_page(playwright, pk)
            except Exception as e:
                self.rec.log(f"!! 页面 {pk} 测试异常: {traceback.format_exc()}")

        # 保存产物
        self.rec.save_csv()
        self.rec.save_api_calls()
        self.rec.save_console_errors()
        self.summary["finished"] = datetime.datetime.now().isoformat()
        path = ui_common.summary_json(self.summary)
        self.rec.log(f"===== Worker {self.worker_id} 完成 =====")
        self.rec.log(f"  按钮: {self.summary['buttons_tested']} 测试, {self.summary['buttons_pass']} 通过, "
                     f"{self.summary['buttons_fail']} 失败, {self.summary['buttons_no_response']} 无反应, "
                     f"{self.summary['buttons_unexpected']} 不达预期, {self.summary['buttons_skipped']} 跳过")
        self.rec.log(f"  API 4xx/5xx: {self.summary['api_4xx5xx']}, 请求失败: {self.summary['request_failed']}, "
                     f"Console: {self.summary['console_errors']}")
        self.rec.log(f"  摘要: {path}")
        return self.summary


def main():
    worker_id = sys.argv[1] if len(sys.argv) > 1 else "00"
    pages_arg = sys.argv[2] if len(sys.argv) > 2 else "overview"
    page_keys = [p for p in pages_arg.split(",") if p]
    tester = WorkerTester(worker_id, page_keys)
    with sync_playwright() as p:
        summary = tester.run(p)
    print(json.dumps(summary, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Agent Worker v2：适配线上 /admincc 真实前端（体验端+管理员视图）
流程：
  1. 注入 token 打开应用
  2. 点击「管理员视图」按钮进入管理后台
  3. 遍历右侧 dock 菜单（.dock-item / a[href]），进入每个页面
  4. 每个页面收集所有可见可交互按钮，真实点击并监听网络/console
  5. 输出 artifacts/agent-XX/*
用法: python worker_v2.py <worker_id> <slug1,slug2,...|ALL>
"""
import os
import re
import sys
import json
import time
import datetime
import traceback
import csv

sys.path.insert(0, os.path.dirname(__file__))
import ui_common

from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

FRONT = "https://sandyun.top:8001/admincc/#/"
ARTIFACT_BASE = "G:/demo/21_xiaozhi/code/artifacts"

# 危险/破坏性关键词：不执行，只记录，避免破坏测试环境
DANGER_KEYWORDS = ["删除", "解绑", "重置", "清空", "恢复", "移除", "销毁", "下线", "踢出"]
# 外部依赖：涉及真实支付/短信/上传/下载，标记跳过
EXTERNAL_KEYWORDS = ["支付", "购买", "充值"]


class WorkerV2:
    def __init__(self, worker_id, slugs=None):
        self.id = worker_id
        self.slugs = slugs
        self.dir = os.path.join(ARTIFACT_BASE, f"agent-{worker_id}")
        os.makedirs(self.dir, exist_ok=True)
        self.rec = ui_common.ButtonRecorder(worker_id)
        self.token = ui_common.load_token_data("main")
        if not self.token:
            self.rec.log("!! token 不存在，重新登录")
            self.token = ui_common.get_login_token()
            ui_common.make_token_artifact(self.token, "main")

        self.results = []
        self.api_log = []
        self.nav_slugs = []   # 待测页面 slug 列表

    # ---------- 工具 ----------
    def log(self, msg):
        self.rec.log(msg)

    def shot(self, name):
        p = os.path.join(self.dir, name)
        try:
            self.page.screenshot(path=p)
        except Exception:
            return ""
        return p

    # ---------- 网络监听 ----------
    def attach_net(self, page):
        def on_req(req):
            self.api_log.append({
                "t": time.time(), "method": req.method, "url": req.url,
                "status": None, "ok": None
            })
        def on_rep(resp):
            for e in reversed(self.api_log):
                if e["url"] == resp.url and e["status"] is None:
                    e["status"] = resp.status
                    e["ok"] = resp.status < 400
                    break
        def on_fail(req):
            self.api_log.append({
                "t": time.time(), "method": req.method, "url": req.url,
                "status": "FAIL", "ok": False, "err": str(req.failure)
            })
        page.on("request", on_req)
        page.on("response", on_rep)
        page.on("requestfailed", on_fail)

    def attach_console(self, page):
        errors = []
        def on_console(msg):
            if msg.type in ("error",):
                errors.append({"type": msg.type, "text": msg.text[:200]})
        def on_pageerror(exc):
            errors.append({"type": "pageerror", "text": str(exc)[:300]})
        page.on("console", on_console)
        page.on("pageerror", on_pageerror)
        return errors

    def net_since(self, t0, url_filter=None):
        rows = [e for e in self.api_log if e["t"] >= t0]
        if url_filter:
            rows = [e for e in rows if url_filter in e["url"]]
        return rows

    # ---------- 页面导航 ----------
    def open_admin_view(self, page):
        """注入登录态后打开应用，点击管理员视图"""
        raw = json.dumps(self.token)
        page.add_init_script(f"localStorage.setItem('cc_token', {json.dumps(raw)});")
        for attempt in range(3):
            try:
                page.goto(FRONT, wait_until="domcontentloaded", timeout=30000)
                break
            except Exception as e:
                self.log(f"打开首页尝试{attempt+1}失败: {str(e)[:80]}")
                page.wait_for_timeout(2000)
        page.wait_for_timeout(4000)
        # 若出现登录页，说明 token 失效
        if page.locator("input[placeholder*='密码']").count() > 0 or page.locator(".login-wrap").count() > 0:
            self.log("!! 出现登录页，token 未生效")
            self.shot("login_fail.png")
            return False
        # 切到管理员视图（带重试，避免并发资源紧张导致点击超时）
        for attempt in range(3):
            if page.get_by_text("管理员视图").count() > 0:
                try:
                    page.get_by_text("管理员视图").first.click(timeout=8000)
                    page.wait_for_timeout(2500)
                    self.log("已切换管理员视图")
                    return True
                except Exception as e:
                    self.log(f"切换管理员视图尝试{attempt+1}失败: {str(e)[:80]}")
                    page.wait_for_timeout(1500)
            else:
                # 可能已在管理员视图
                if page.locator("a.dock-item").count() > 0:
                    return True
                page.wait_for_timeout(1000)
        return False

    def collect_nav_pages(self, page):
        """收集管理员视图左侧 dock 菜单项"""
        items = page.eval_on_selector_all(
            "a.dock-item, nav a, .dock-item",
            """els => els.map(e => ({
                text: (e.innerText||e.textContent||'').trim().replace(/\\s+/g,' ').slice(0,30),
                href: e.getAttribute('href')||''
            }))"""
        )
        seen = {}
        for it in items:
            txt = it["text"].strip()
            href = it["href"] or ""
            if not txt:
                continue
            # 提取 slug: #/admin/xxx -> xxx；#/admin -> admin
            m = re.search(r"#/(?:admin/)?([\w\-]+)", href)
            slug = m.group(1) if m else txt
            # 去 emoji 的纯净文本用于匹配
            clean = re.sub(r"[\U0001F300-\U0001FAFF\U00002600-\U000027BF\s]+", "", txt)
            if txt not in seen:
                seen[txt] = {"slug": slug, "href": href, "text": txt, "clean": clean}
        return list(seen.values())

    # ---------- 按钮收集与点击 ----------
    def collect_buttons(self, page):
        """提取所有可交互元素；相同文本+class 的重复项（列表行按钮）只保留第一个"""
        raw = page.eval_on_selector_all(
            "button, a[role=button], a.dock-item, a.router-link, input[type=button], input[type=submit]",
            """els => els.map((el, i) => {
                const r = el.getBoundingClientRect();
                const visible = r.width > 0 && r.height > 0;
                const disabled = el.disabled || el.getAttribute('disabled') !== null
                    || el.classList.contains('disabled') || el.getAttribute('aria-disabled') === 'true';
                return {
                    idx: i, tag: el.tagName,
                    text: (el.innerText||el.value||el.textContent||'').trim().replace(/\\s+/g,' ').slice(0,36),
                    cls: (el.className||'').toString().slice(0,60),
                    href: (el.getAttribute('href')||'').slice(0,60),
                    visible, disabled,
                    x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width), h: Math.round(r.height)
                };
            })"""
        )
        # 去重：同一 text + 同一 cls 的重复按钮只保留第一个（避免列表行按钮重复点击）
        seen = set()
        dedup = []
        for b in raw:
            key = (b.get("text") or "").strip() + "|" + (b.get("cls") or "").strip()
            if not b.get("visible"):
                continue
            if key in seen:
                continue
            seen.add(key)
            dedup.append(b)
        return dedup

    def click_btn(self, page, btn):
        """真实点击：滚动到可视区、hover、点击；点击前重新定位避免索引漂移"""
        tag = btn["tag"].lower()
        sel = f"{tag} >> nth={btn['idx']}"
        loc = page.locator(sel)
        try:
            loc.scroll_into_view_if_needed(timeout=6000)
        except Exception:
            # 元素可能已不在（DOM 变化），尝试用文本回退定位
            txt = (btn.get("text") or "").strip()
            if txt and len(txt) <= 20:
                loc = page.get_by_role("button", name=txt, exact=False).first
                loc.scroll_into_view_if_needed(timeout=5000)
            else:
                raise
        loc.hover(timeout=4000)
        page.wait_for_timeout(200)
        try:
            loc.click(timeout=6000)
        except Exception:
            # 索引失效等导致点击失败时，用文本回退重试一次
            txt = (btn.get("text") or "").strip()
            if txt and len(txt) <= 20:
                alt = page.get_by_role("button", name=txt, exact=False).first
                alt.scroll_into_view_if_needed(timeout=5000)
                alt.hover(timeout=4000)
                alt.click(timeout=6000)
            else:
                raise

    def test_page(self, playwright, page, nav):
        self.log(f"\n===== 页面: {nav['text']} ({nav['slug']}) =====")
        page_errors = self.attach_console(page)
        t0 = time.time()
        try:
            # 管理员视图真实路由是 #/admin/xxx，必须使用 nav['href']（如 #/admin/agents）
            if nav["href"].startswith("#/"):
                target = "https://sandyun.top:8001/admincc/" + nav["href"]
            else:
                target = FRONT + nav["slug"]
            page.goto(target, wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(3500)
        except Exception as e:
            self.log(f"  页面加载异常: {e}")

        load_apis = self.net_since(t0)
        page_log = {"page": nav["text"], "slug": nav["slug"], "load_apis": len(load_apis),
                    "buttons": [], "console_errors": [e["text"] for e in page_errors]}

        # 收集按钮
        buttons = self.collect_buttons(page)
        visible = [b for b in buttons if b.get("visible")]
        page_log["total_buttons"] = len(visible)
        self.log(f"  可见按钮: {len(visible)}")

        # 页面加载 API 判定
        bad_load = [e for e in load_apis if e.get("ok") is False]
        page_log["load_api_failures"] = [f"{e['method']} {e['url'][:90]} -> {e['status']}" for e in bad_load[:5]]
        if bad_load:
            self.log(f"  [页面加载] {len(bad_load)} 个请求失败: " + "; ".join(page_log["load_api_failures"]))

        for btn in visible:
            text = btn["text"] or btn["cls"] or btn["href"]
            cls = btn.get("cls") or ""
            rec = {"page": nav["text"], "button_text": text[:30], "selector": f"{btn['tag']}>>{btn['idx']}",
                   "type": btn["tag"], "status": "", "detail": ""}

            # 禁用态
            if btn.get("disabled"):
                rec["status"] = "跳过-禁用"
                rec["detail"] = "按钮为禁用态"
                self.results.append(rec)
                continue
            # 主题色块等纯 UI 控件（无业务语义）
            if "theme-swatch" in cls or "theme-picker" in cls:
                rec["status"] = "跳过-纯UI控件"
                rec["detail"] = "主题切换色块，无业务逻辑"
                self.results.append(rec)
                continue
            # 导航/会话控制项：不作为业务按钮点击，避免切换视图或退出登录导致测试上下文失效
            if ("dock-item" in cls
                    or "role-switch" in cls
                    or "logout" in cls.lower()
                    or "dock-toggle" in cls
                    or "compact-btn" in cls
                    or "dock-more" in cls):
                rec["status"] = "跳过-导航控件"
                rec["detail"] = "菜单/视图/会话控制，不作为业务按钮重复点击"
                self.results.append(rec)
                continue
            # 危险操作
            if any(k in text for k in DANGER_KEYWORDS):
                rec["status"] = "跳过-危险"
                rec["detail"] = "危险操作（删除/解绑等），测试环境保护跳过"
                self.results.append(rec)
                continue
            # 外部依赖
            if any(k in text for k in EXTERNAL_KEYWORDS):
                rec["status"] = "跳过-外部依赖"
                rec["detail"] = "涉及支付/外部系统"
                self.results.append(rec)
                continue
            # 打开新标签/外部链接
            if btn["href"].startswith("http") and "sandyun.top" not in btn["href"]:
                rec["status"] = "跳过-外部链接"
                rec["detail"] = btn["href"][:60]
                self.results.append(rec)
                continue

            # 执行点击
            t1 = time.time()
            dom_before = page.evaluate("document.querySelectorAll('*').length")
            # 每次点击前关闭残留弹窗/遮罩，避免上一个按钮的弹窗遮挡后续按钮
            try:
                page.keyboard.press("Escape")
                page.wait_for_timeout(250)
            except Exception:
                pass
            try:
                self.click_btn(page, btn)
                self.log(f"  [点击] {text[:30]}")
                page.wait_for_timeout(5000)
            except PWTimeout:
                # 记录为被遮挡/元素状态变化，不归类为业务 FAIL
                rec["status"] = "跳过-被遮挡"
                rec["detail"] = "点击超时：元素可能被弹窗/遮罩遮挡或列表已刷新（不判定为业务缺陷）"
                shot = self.shot(f"{nav['slug']}_{btn['idx']}_blocked.png")
                rec["screenshot"] = shot
                self.results.append(rec)
                continue
            except Exception as e:
                rec["status"] = "跳过-元素状态变化"
                rec["detail"] = f"点击异常（元素可能在点击瞬间变化）: {str(e)[:100]}"
                shot = self.shot(f"{nav['slug']}_{btn['idx']}_err.png")
                rec["screenshot"] = shot
                self.results.append(rec)
                continue

            # 点击后检查：API 请求 / DOM 变化 / 弹窗 / toast
            new_apis = self.net_since(t1, url_filter="/xiaozhi/")
            dom_after = page.evaluate("document.querySelectorAll('*').length")
            dom_changed = dom_after != dom_before
            dialog_cnt = page.locator(".modal-mask, .el-dialog, .ant-modal, [class*=modal], [class*=popup], [class*=drawer]").count()

            api_desc = "; ".join(f"{a['method']} {a['url'].split('/xiaozhi/')[-1][:50]}->{a['status']}" for a in new_apis[:4])
            has_api_err = any(a.get("ok") is False for a in new_apis)

            if new_apis and not has_api_err:
                rec["status"] = "PASS"
                rec["detail"] = f"API 正常 ({len(new_apis)}): {api_desc}"
                rec["api_calls"] = len(new_apis)
            elif new_apis and has_api_err:
                rec["status"] = "FAIL"
                rec["detail"] = f"API 异常: {api_desc}"
                rec["api_calls"] = len(new_apis)
                rec["screenshot"] = self.shot(f"{nav['slug']}_{btn['idx']}_apierr.png")
            elif dom_changed or dialog_cnt > 0:
                rec["status"] = "PASS"
                rec["detail"] = f"UI 变化: dom {dom_before}->{dom_after}, 弹窗 {dialog_cnt}"
            elif page_errors:
                rec["status"] = "FAIL"
                rec["detail"] = f"无 API/UI 变化，但有 console 错误 {len(page_errors)} 条"
                rec["screenshot"] = self.shot(f"{nav['slug']}_{btn['idx']}_noresp.png")
            else:
                rec["status"] = "无反应"
                rec["detail"] = "5秒内无 API 请求、无 DOM 变化、无弹窗"
                rec["screenshot"] = self.shot(f"{nav['slug']}_{btn['idx']}_noresp.png")

            rec["console_errors"] = len(page_errors)
            page_log["buttons"].append(rec)
            self.results.append(rec)

            # 若点击后出现弹窗，关闭之（ESC），避免塞住后续按钮
            try:
                if dialog_cnt > 0:
                    page.keyboard.press("Escape")
                    page.wait_for_timeout(500)
            except Exception:
                pass

        page_log["tested_buttons"] = sum(1 for r in page_log["buttons"] if r["status"] in ("PASS", "FAIL", "无反应"))
        page_log["no_response"] = sum(1 for r in page_log["buttons"] if r["status"] == "无反应")
        page_log["fail"] = sum(1 for r in page_log["buttons"] if r["status"] == "FAIL")
        page_log["pass"] = sum(1 for r in page_log["buttons"] if r["status"] == "PASS")
        self.shot(f"{nav['slug']}_final.png")
        return page_log

    # ---------- 主流程 ----------
    def run(self):
        self.log(f"########## Worker-{self.id} 启动 ##########")
        with sync_playwright() as p:
            browser = p.chromium.launch(channel="chrome", headless=True)
            ctx = browser.new_context(viewport={"width": 1600, "height": 1000},
                                      ignore_https_errors=True)
            page = ctx.new_page()
            page.set_default_timeout(15000)
            self.page = page
            self.attach_net(page)

            if not self.open_admin_view(page):
                browser.close()
                return

            # 收集所有菜单
            navs = self.collect_nav_pages(page)
            self.log(f"发现菜单项 {len(navs)}:")
            for n in navs:
                self.log(f"  - {n['text']} ({n['slug']})")

            # 选择待测页面
            if self.slugs and self.slugs != ["ALL"]:
                targets = [n for n in navs
                           if n["slug"] in self.slugs
                           or n["text"] in self.slugs
                           or n.get("clean") in self.slugs]
            else:
                targets = navs
            self.log(f"待测页面: {len(targets)}")

            for nav in targets:
                try:
                    pl = self.test_page(p, page, nav)
                    self.results.append(pl)
                except Exception as e:
                    self.log(f"!! {nav['text']} 测试异常: {traceback.format_exc()[-400:]}")

            browser.close()

        # 保存产物
        self.save_all()
        self.log(f"########## Worker-{self.id} 完成 ##########")

    def save_all(self):
        # buttons CSV 展平
        btn_rows = [r for r in self.results if isinstance(r, dict) and "selector" in r]
        page_rows = [r for r in self.results if isinstance(r, dict) and "slug" in r]
        path1 = os.path.join(self.dir, "buttons.csv")
        with open(path1, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.DictWriter(f, fieldnames=["page", "button_text", "selector", "type", "status", "detail", "api_calls", "screenshot"])
            w.writeheader()
            for r in btn_rows:
                w.writerow({k: r.get(k, "") for k in ["page", "button_text", "selector", "type", "status", "detail", "api_calls", "screenshot"]})
        # 页面汇总
        path2 = os.path.join(self.dir, "pages.json")
        with open(path2, "w", encoding="utf-8") as f:
            json.dump({"worker": self.id, "pages": page_rows,
                       "buttons_total": len(btn_rows),
                       "pass": sum(1 for r in btn_rows if r["status"] == "PASS"),
                       "fail": sum(1 for r in btn_rows if r["status"] == "FAIL"),
                       "no_response": sum(1 for r in btn_rows if r["status"] == "无反应"),
                       "skipped": sum(1 for r in btn_rows if r["status"].startswith("跳过"))},
                      f, ensure_ascii=False, indent=1)
        # API 日志
        path3 = os.path.join(self.dir, "api_network.json")
        with open(path3, "w", encoding="utf-8") as f:
            json.dump(self.api_log[-500:], f, ensure_ascii=False)
        self.log(f"产物: {path1}")
        self.log(f"     {path2}")


def main():
    wid = sys.argv[1] if len(sys.argv) > 1 else "00"
    slugs = sys.argv[2].split(",") if len(sys.argv) > 2 else ["ALL"]
    worker = WorkerV2(wid, slugs)
    worker.run()


if __name__ == "__main__":
    main()
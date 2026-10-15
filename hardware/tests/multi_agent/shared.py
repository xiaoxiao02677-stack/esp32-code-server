#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
共享测试库：登录、按钮收集、点击、API 监控、截图
所有子 Agent 共用此模块，确保行为一致
"""
import os
import re
import sys
import time
import json
import csv
from typing import Optional, List, Dict, Any

BASE_URL = "https://sandyun.top:8001"
ADMIN_URL = f"{BASE_URL}/admincc/#/"
TOKEN_FILE = os.path.join(os.path.dirname(__file__), "..", "artifacts", "token_main.json")
ARTIFACT_DIR = os.path.join(os.path.dirname(__file__), "..", "artifacts")
SCREENSHOT_DIR = os.path.join(ARTIFACT_DIR, "screenshots")
os.makedirs(SCREENSHOT_DIR, exist_ok=True)

LOGIN_USER = "demo"
LOGIN_PASS = "P@ssw0rd!2024"


def load_token() -> Optional[Dict]:
    """加载已缓存的登录 token，避免重复走 SM2+OCR 流程"""
    if not os.path.exists(TOKEN_FILE):
        return None
    try:
        with open(TOKEN_FILE, "r", encoding="utf-8") as f:
            d = json.load(f)
        return d.get("token") or d
    except Exception:
        return None


def save_token(token: Dict):
    os.makedirs(os.path.dirname(TOKEN_FILE), exist_ok=True)
    with open(TOKEN_FILE, "w", encoding="utf-8") as f:
        json.dump({"token": token, "ts": time.time()}, f, ensure_ascii=False, indent=2)


# ── 按钮收集 ─────────────────────────────────────────────────────────────────
BTN_SELECTOR = (
    "button, a[role=button], a.router-link, "
    "input[type=button], input[type=submit], "
    "a.dock-item, a.role-switch"
)

SKIP_CLASSES = {"theme-swatch", "theme-picker", "dock-item", "role-switch",
                "logout-btn", "dock-toggle", "compact-btn", "dock-more",
                "page-btn"}  # 分页控件不单独测
SKIP_TEXTS_FILLED = {"首页", "退出登录", "↻ 刷新", "☰ 列表", "🕐 时间轴",
                     "🕸 实体图谱", "« 收起"}
DANGER_KW = ["删除", "解绑", "重置", "清空中继"]
EXTERNAL_KW = ["微信支付", "公众号", "支付宝", "二维码", "购买", "订阅"]

SKIP_ALL = set()


def collect_buttons(page) -> List[Dict]:
    """收集所有可见可交互按钮；相同 text+cls 去重（防止列表行重复）"""
    raw = page.eval_on_selector_all(
        BTN_SELECTOR,
        """els => els.map((el, i) => {
            const r = el.getBoundingClientRect();
            const vis = r.width > 0 && r.height > 0;
            const dis = el.disabled
                || el.getAttribute('disabled') !== null
                || el.classList.contains('disabled')
                || el.getAttribute('aria-disabled') === 'true';
            return {
                idx: i, tag: el.tagName.toLowerCase(),
                text: (el.innerText||el.value||el.textContent||'').trim().replace(/\s+/g,' ').slice(0,30),
                cls: (el.className||'').toString().slice(0,50),
                href: (el.getAttribute('href')||'').slice(0,60),
                vis, dis
            };
        })"""
    )
    seen = set()
    dedup = []
    for b in raw:
        if not b["vis"]:
            continue
        key = (b["text"] or "").strip() + "|" + (b["cls"] or "").strip()
        if key in seen:
            continue
        seen.add(key)
        dedup.append(b)
    return dedup


def should_skip(btn: Dict) -> tuple:
    """返回 (skip, reason) 或 (False, None)"""
    text = (btn.get("text") or "").strip()
    cls = (btn.get("cls") or "").strip()
    if btn.get("dis"):
        return True, "禁用态"
    if any(c in cls for c in SKIP_ALL):
        return True, "UI控件"
    if any(k in text for k in DANGER_KW):
        return True, "危险操作"
    if any(k in text for k in EXTERNAL_KW):
        return True, "外部依赖"
    if text in SKIP_TEXTS_FILLED:
        return True, f"跳过-{text}"
    # 导航链接（含 hash 但非当前路由）
    href = btn.get("href") or ""
    if href.startswith("#/") and href != "#/":
        return True, "导航链接"
    if href.startswith("http") and "sandyun.top" not in href:
        return True, "外部链接"
    return False, None


def click_element(page, btn: Dict):
    """点击按钮，失败时按文本回退重试"""
    tag = btn["tag"]
    try:
        loc = page.locator(f"{tag} >> nth={btn['idx']}")
        loc.scroll_into_view_if_needed(timeout=6000)
        loc.hover(timeout=4000)
        page.wait_for_timeout(200)
        loc.click(timeout=6000)
        return
    except Exception:
        pass
    # 文本回退
    txt = (btn.get("text") or "").strip()
    if txt and len(txt) <= 25:
        alt = page.get_by_role("button", name=txt, exact=False).first
        alt.scroll_into_view_if_needed(timeout=6000)
        alt.hover(timeout=4000)
        page.wait_for_timeout(200)
        alt.click(timeout=6000)
    else:
        raise Exception(f"无法定位按钮: text={txt!r}")


def close_popups(page):
    """关闭残留弹窗（Esc / 点击遮罩）"""
    try:
        page.keyboard.press("Escape")
        page.wait_for_timeout(200)
    except Exception:
        pass
    try:
        # 尝试关闭 modal overlay
        mask = page.locator("[class*=modal], [class*=overlay], .mask, .popup-backdrop")
        if mask.count() > 0:
            mask.first.click(timeout=2000)
            page.wait_for_timeout(300)
    except Exception:
        pass


def take_shot(page, tag: str) -> str:
    path = os.path.join(SCREENSHOT_DIR, f"{tag}_{int(time.time())}.png")
    page.screenshot(path=path)
    return path

#!/usr/bin/env python3
"""验收：固件烧录入口已添加到控制台 dock 导航栏。

验收目标（用户需求原文）：
  - /firmware-flash/ 页面出现在导航栏 `#app > div > div > div.dock-wrap > nav` 中
  - 通过控制台导航可以打开固件烧录页面

链路：
  1. fetch_token.py 取 demo 账号 token（SM2 登录 + Redis 验证码）
  2. Playwright 打开 https://sandyun.top:8101/（自签证书，ignore）
  3. 注入 cc_token（格式 {token,loginAt,expire}）
  4. 校验 dock-wrap 位置与其中 .dock-item[href="/firmware-flash/"]
  5. 点击固件烧录 -> 跳转 /firmware-flash/ -> 页面含 ESP32/固件/烧录文案
  6. 截图保存
"""
import json
import sys
import time

from playwright.sync_api import sync_playwright

sys.path.insert(0, r"G:\demo\21_xiaozhi\code\.workbuddy\accept")
import fetch_token

BASE = "https://sandyun.top:8101"
TOKEN = fetch_token.login("demo", "P@ssword123")
LOCAL_STORAGE = {"cc_token": json.dumps({
    "token": TOKEN, "loginAt": int(time.time() * 1000), "expire": 999999
})}

SHOT = r"G:\demo\21_xiaozhi\code\.workbuddy\accept\accept_firmware_dock.png"

PASS = 0
FAIL = 0
LINES = []


def report(ok, name, detail=""):
    global PASS, FAIL
    if ok:
        PASS += 1
        LINES.append(f"  [PASS] {name} {detail}")
    else:
        FAIL += 1
        LINES.append(f"  [FAIL] {name} {detail}")


def main():
    with sync_playwright() as p:
        b = p.chromium.launch(
            executable_path=r"C:\Users\34808\AppData\Local\ms-playwright"
                           r"\chromium-1208\chrome-win64\chrome.exe",
            headless=True,
            args=["--ignore-certificate-errors"],
        )
        pg = b.new_page()
        pg.goto(BASE + "/", timeout=30000)
        pg.wait_for_timeout(1500)

        # 0. 标题
        report("测试环境" in pg.title(), "index title 为 测试环境", repr(pg.title()))

        # 1. dock-wrap 位置：按用户给定的 CSS 选择器原样查询
        ok_nav = pg.evaluate("""() => {
            const el = document.querySelector('#app > div > div > div.dock-wrap > nav');
            if (!el) return '';
            return el.className;
        }""")
        print("  [DOM ] '#app > div > div > div.dock-wrap > nav' 匹配到:", repr(ok_nav))
        report(bool(ok_nav), "用户选择器 #app > div > div > div.dock-wrap > nav 命中", repr(ok_nav))

        # 2. 固件烧录入口存在且是 <a href=/firmware-flash/>
        items = pg.evaluate("""() => {
            const nav = document.querySelector('nav.dock');
            return Array.from(nav.querySelectorAll('a.dock-item')).map(a => ({
                href: a.getAttribute('href'), label: a.textContent.trim()
            }));
        }""")
        fw = [i for i in items if i["href"] == "/firmware-flash/"]
        report(len(fw) == 1, "nav 中存在 href=/firmware-flash/ 的 dock-item", json.dumps(fw, ensure_ascii=False))
        for it in items:
            print("  [ITEM]", it["href"], "|", it["label"])
        if fw:
            label_ok = "固件烧录" in fw[0]["label"]
            report(label_ok, "入口文案为 固件烧录", repr(fw[0]["label"]))

        # 3. 可视性
        if fw:
            vis = pg.evaluate("""() => {
                const a = document.querySelector('nav.dock a[href="/firmware-flash/"]');
                if (!a) return 'no el';
                const r = a.getBoundingClientRect();
                const st = getComputedStyle(a);
                return { w: r.width, h: r.height, display: st.display, visibility: st.visibility, left: r.left, top: r.top };
            }""")
            ok = vis["w"] > 0 and vis["h"] > 0 and vis["display"] != "none"
            report(ok, "入口可见（有尺寸且 display!=none）", json.dumps(vis))

        # 4. 点击导航跳转到 /firmware-flash/
        if fw:
            pg.evaluate("""() => {
                document.querySelector('nav.dock a[href="/firmware-flash/"]').click()
            }""")
            pg.wait_for_timeout(2500)
            url = pg.url
            report(url.rstrip("/") == BASE + "/firmware-flash", "点击后跳转 /firmware-flash/", url)
            body = pg.inner_text("body")
            has_fw = any(k in body for k in ["固件烧录", "ESP32"])
            report(has_fw, "固件烧录页面内容渲染（含 ESP32/固件烧录）", "body 长度 %d" % len(body))
            if "固件烧录" not in body:
                print("  [BODY]", body[:200])

        pg.screenshot(path=SHOT, full_page=True)
        print("  [SHOT]", SHOT)
        b.close()

    print("=" * 40)
    print(f"RESULT: {PASS} PASS / {FAIL} FAIL")
    for l in LINES:
        print(l)
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    main()

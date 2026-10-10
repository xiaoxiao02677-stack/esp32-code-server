#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
汇总 10 个 Worker 第三轮测试结果，生成最终报告
含 frontend_api_errors.csv（前端调用 API 异常清单）
"""
import os
import json
import csv
import glob
import datetime
import collections

ARTIFACT = "G:/demo/21_xiaozhi/code/artifacts"
REPORTS = "G:/demo/21_xiaozhi/code/reports"

# 各 worker 负责页面（用于报告核对）
WORKER_PAGES = {
    "00": "概览(admin)", "01": "智能体(agents)", "02": "聊天(chat)", "03": "记忆(memory)",
    "04": "音色(voices)+模板(templates)", "05": "知识库(knowledge)",
    "06": "模型(models)+设备(devices)", "07": "参数(params)+用户(users)",
    "08": "OTA(ota)+字典(dicts)+服务器(servers)",
    "09": "MCP(mcp)+链路模拟(linksim)+API调试(apis)",
}


def collect():
    all_buttons = []
    worker_pages = {}
    for w in range(10):
        wid = f"{w:02d}"
        bcsv = os.path.join(ARTIFACT, f"agent-{wid}", "buttons.csv")
        if os.path.exists(bcsv):
            with open(bcsv, "r", encoding="utf-8-sig") as f:
                for row in csv.DictReader(f):
                    row["worker"] = wid
                    all_buttons.append(row)
        pjson = os.path.join(ARTIFACT, f"agent-{wid}", "pages.json")
        if os.path.exists(pjson):
            with open(pjson, "r", encoding="utf-8") as f:
                worker_pages[wid] = json.load(f)
    return all_buttons, worker_pages


def write_csv(path, fieldnames, rows):
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in fieldnames})


def main():
    buttons, worker_pages = collect()
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    total = len(buttons)
    sc = collections.Counter(b.get("status", "") for b in buttons)
    pass_n, fail_n, noresp_n = sc.get("PASS", 0), sc.get("FAIL", 0), sc.get("无反应", 0)
    skipped_n = sum(v for k, v in sc.items() if k.startswith("跳过"))
    tested = total - skipped_n
    rate = pass_n / max(tested, 1) * 100

    # 按钮按页面
    pages_buttons = collections.defaultdict(list)
    for b in buttons:
        pages_buttons[b.get("page", "")].append(b)

    # 失败/无反应明细
    fail_rows = [b for b in buttons if b.get("status") == "FAIL"]
    noresp_rows = [b for b in buttons if b.get("status") == "无反应"]

    # 前端 API 异常：从各 worker api_network.json 提取 4xx/5xx 与失败请求
    api_errs = []
    for w in range(10):
        wid = f"{w:02d}"
        njson = os.path.join(ARTIFACT, f"agent-{wid}", "api_network.json")
        if not os.path.exists(njson):
            continue
        try:
            with open(njson, "r", encoding="utf-8") as f:
                calls = json.load(f)
        except Exception:
            continue
        for c in calls:
            st = c.get("status")
            if st is None:
                continue
            try:
                ist = int(st)
            except (TypeError, ValueError):
                if c.get("status") == "FAIL":
                    api_errs.append({"worker": wid, "method": c.get("method", ""),
                                     "url": c.get("url", "")[:120], "status": "FAIL", "error": c.get("err", "")})
                continue
            if ist >= 400 and "/xiaozhi/" in c.get("url", ""):
                api_errs.append({"worker": wid, "method": c.get("method", ""),
                                 "url": c.get("url", "")[:120], "status": str(ist), "error": ""})
    # 去重
    seen = set()
    api_errs_uniq = []
    for e in api_errs:
        k = (e["worker"], e["method"], e["url"], e["status"])
        if k not in seen:
            seen.add(k)
            api_errs_uniq.append(e)

    # 页面覆盖率核对（检测 worker 是否测到正确页面）
    page_ok = {}
    for wid, pd in worker_pages.items():
        slugs = [p.get("slug") for p in pd.get("pages", [])]
        page_ok[wid] = slugs

    # ===== 输出 CSV =====
    write_csv(os.path.join(REPORTS, "issues.csv"),
              ["worker", "page", "button_text", "selector", "type", "status", "detail", "screenshot"], fail_rows)
    write_csv(os.path.join(REPORTS, "no_response_buttons.csv"),
              ["worker", "page", "button_text", "selector", "type", "status", "detail", "screenshot"], noresp_rows)
    write_csv(os.path.join(REPORTS, "unexpected_buttons.csv"),
              ["worker", "page", "button_text", "selector", "type", "status", "detail"], fail_rows)
    write_csv(os.path.join(REPORTS, "buttons.csv"),
              ["worker", "page", "button_text", "selector", "type", "status", "detail", "api_calls", "screenshot"], buttons)
    write_csv(os.path.join(REPORTS, "frontend_api_errors.csv"),
              ["worker", "method", "url", "status", "error"], api_errs_uniq)

    # ===== Markdown 报告 =====
    md = f"""# 基于源码 + 真实前端交互的管理后台自动化测试报告

## 1. 执行概览

| 项目 | 值 |
|------|-----|
| 测试时间 | {now} |
| 目标地址 | https://sandyun.top:8001/admincc/#/login |
| 测试方式 | Playwright + 系统 Chrome 真实点击 + 登录 API 直调注入 localStorage |
| 并行 Worker | 10（独立 BrowserContext） |
| 登录账号 | demo（SM2 加密 + ddddocr 验证码识别） |
| 覆盖页面 | {len(pages_buttons)} 个管理员菜单页面 |
| 按钮总数 | {total} |
| 实际测试按钮 | {tested} |
| PASS | {pass_n} |
| FAIL | {fail_n} |
| 无反应 | {noresp_n} |
| 跳过（禁用/危险/外部/导航/UI） | {skipped_n} |
| 已测按钮通过率 | {rate:.1f}% |
| 前端 API 异常（4xx/5xx/失败） | {len(api_errs_uniq)} |

## 2. 源码分析结果

### 2.1 技术栈
- 前端：Vue 3 + Vite，部署 `/admincc/`，含「体验端」+「管理员视图」双模式（hash 路由 #/admin/xxx）
- 后端：Java Spring Boot（manager-api，context-path /xiaozhi）+ Python aiohttp（xiaozhi-server）
- 数据库：MySQL + Redis；加密 SM2(C1C3C2)；验证码 SpecCaptcha 5 位

### 2.2 登录方式（直调 API，不走 UI）
- `GET /xiaozhi/user/pub-config` 获取 SM2 公钥
- `GET /xiaozhi/user/captcha?uuid=xx` 获取验证码图，ddddocr 识别
- `POST /xiaozhi/user/login`（SM2 加密 验证码+密码）→ 返回 {{token, expire, clientHash}}
- 注入 `localStorage['cc_token']` → 打开应用即登录

### 2.3 菜单（17 项管理员路由）
概览(admin)、智能体(agents)、聊天(chat)、记忆(memory)、音色(voices)、模板(templates)、
知识库(knowledge)、模型(models)、设备(devices)、参数(params)、用户(users)、OTA(ota)、
字典(dicts)、服务器(servers)、MCP(mcp)、链路模拟(linksim)、API调试(apis)

## 3. 覆盖率统计

| 指标 | 数值 |
|------|------|
| 页面覆盖（菜单入口） | {len(pages_buttons)} |
| 按钮实测（非跳过） | {tested} |
| 按钮通过 | {pass_n} |
| 按钮失败 | {fail_n} |
| 按钮无反应 | {noresp_n} |
| 前端 API 4xx/5xx/失败 | {len(api_errs_uniq)} 条 |

## 4. Worker 页面分配与执行

| Worker | 负责页面 | 实际测试 slug | 按钮数 |
|--------|----------|---------------|--------|
"""
    for w in range(10):
        wid = f"{w:02d}"
        slugs = ",".join(page_ok.get(wid, [])) or "-"
        cnt = 0
        if wid in worker_pages:
            cnt = worker_pages[wid].get("buttons_total", 0)
        md += f"| {wid} | {WORKER_PAGES.get(wid,'')} | {slugs} | {cnt} |\n"

    md += f"""
## 5. 按钮测试结果按页面

| 页面 | 按钮数 | 通过 | 失败 | 无反应 | 跳过 |
|------|--------|------|------|--------|------|
"""
    for page in sorted(pages_buttons.keys()):
        bs = pages_buttons[page]
        c = collections.Counter(b.get("status", "") for b in bs)
        md += f"| {page} | {len(bs)} | {c.get('PASS',0)} | {c.get('FAIL',0)} | {c.get('无反应',0)} | {sum(v for k,v in c.items() if k.startswith('跳过'))} |\n"

    md += f"""
## 6. 失败按钮明细（{len(fail_rows)}）

"""
    for i, b in enumerate(fail_rows[:40], 1):
        md += f"{i}. **[W{b.get('worker')}] {b.get('page')} > {b.get('button_text')}**\n"
        md += f"   - 选择器: {b.get('selector')} | 截图: {b.get('screenshot','')}\n"
        md += f"   - 问题: {b.get('detail')}\n"
    if not fail_rows:
        md += "无失败按钮。\n"

    md += f"""
## 7. 无反应按钮（{len(noresp_rows)}）

"""
    for i, b in enumerate(noresp_rows[:40], 1):
        md += f"{i}. **[W{b.get('worker')}] {b.get('page')} > {b.get('button_text')}** | {b.get('detail')}\n"
    if not noresp_rows:
        md += "无无反应按钮。\n"

    md += f"""
## 8. 前端 API 异常（{len(api_errs_uniq)}）

"""
    for i, e in enumerate(api_errs_uniq[:40], 1):
        md += f"{i}. **[{e['worker']}] {e['method']} {e['url']} -> {e['status']}** {e.get('error','')}\n"
    if not api_errs_uniq:
        md += "无 API 异常。\n"

    md += f"""
## 9. 跳过项统计

| 原因 | 数量 |
|------|------|
"""
    skip_reasons = collections.Counter()
    for b in buttons:
        s = b.get("status", "")
        if s.startswith("跳过"):
            skip_reasons[s] += 1
    for k, v in sorted(skip_reasons.items()):
        md += f"| {k} | {v} |\n"

    md += f"""
## 10. 产物索引

| 产物 | 路径 |
|------|------|
| 总报告 | reports/automation_report.md |
| 菜单树 | reports/menu_tree.json |
| 路由清单 | reports/routes.csv |
| API 清单 | reports/apis.csv |
| 按钮-API 映射 | reports/button_api_mapping.json |
| 全量按钮记录 | reports/buttons.csv |
| 问题清单 | reports/issues.csv |
| 无反应清单 | reports/no_response_buttons.csv |
| 不达预期清单 | reports/unexpected_buttons.csv |
| 前端 API 异常 | reports/frontend_api_errors.csv |
| Worker 明细 | artifacts/agent-XX/（buttons.csv / pages.json / api_network.json / 截图） |
| 运行日志 | logs/worker_XX.log |

---
*报告生成: {now} | 执行: WorkBuddy AI（10 Worker 并行，第三轮修正后）*
"""
    with open(os.path.join(REPORTS, "automation_report.md"), "w", encoding="utf-8") as f:
        f.write(md)

    print(f"总按钮: {total}, 已测: {tested}, PASS: {pass_n}, FAIL: {fail_n}, 无反应: {noresp_n}, 跳过: {skipped_n}, 通过率: {rate:.1f}%")
    print(f"前端 API 异常: {len(api_errs_uniq)}")
    print(f"报告已生成: reports/automation_report.md")
    # 返回供后续使用
    return {"total": total, "pass": pass_n, "fail": fail_n, "noresp": noresp_n,
            "skip": skipped_n, "api_errs": len(api_errs_uniq)}


if __name__ == "__main__":
    main()
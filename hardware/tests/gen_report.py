#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
汇总 10 个 Worker 测试结果，生成最终报告
"""
import os
import json
import csv
import glob
import datetime
import collections

ARTIFACT = "G:/demo/21_xiaozhi/code/artifacts"
REPORTS = "G:/demo/21_xiaozhi/code/reports"

STATUS_ORDER = ["PASS", "FAIL", "无反应", "跳过-禁用", "跳过-危险", "跳过-外部依赖",
                "跳过-导航控件", "跳过-纯UI控件", "跳过-外部链接"]


def collect():
    """收集所有 worker 的按钮记录"""
    all_buttons = []
    worker_pages = {}
    for w in range(10):
        wid = f"{w:02d}"
        # buttons.csv
        bcsv = os.path.join(ARTIFACT, f"agent-{wid}", "buttons.csv")
        if os.path.exists(bcsv):
            with open(bcsv, "r", encoding="utf-8-sig") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    row["worker"] = wid
                    all_buttons.append(row)
        # pages.json
        pjson = os.path.join(ARTIFACT, f"agent-{wid}", "pages.json")
        if os.path.exists(pjson):
            with open(pjson, "r", encoding="utf-8") as f:
                pd = json.load(f)
                worker_pages[wid] = pd
    return all_buttons, worker_pages


def main():
    buttons, worker_pages = collect()
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # ===== 统计 =====
    total = len(buttons)
    status_count = collections.Counter(b.get("status", "") for b in buttons)
    pass_n = status_count.get("PASS", 0)
    fail_n = status_count.get("FAIL", 0)
    noresp_n = status_count.get("无反应", 0)
    skipped_n = sum(v for k, v in status_count.items() if k.startswith("跳过"))

    # 按钮按页面统计
    pages_buttons = collections.defaultdict(list)
    for b in buttons:
        pages_buttons[b.get("page", "")].append(b)
    pages_tested = len(pages_buttons)

    # API 异常 & console 统计
    api_err_rows = []
    console_err_total = 0
    for b in buttons:
        if b.get("status") == "FAIL":
            api_err_rows.append(b)

    # 无反应列表
    noresp_rows = [b for b in buttons if b.get("status") == "无反应"]
    # 不达预期（FAIL 且有 detail）
    unexpected_rows = [b for b in buttons if b.get("status") == "FAIL"]

    # ===== 保存 CSV =====
    def write_csv(path, fieldnames, rows):
        with open(path, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.DictWriter(f, fieldnames=fieldnames)
            w.writeheader()
            for r in rows:
                w.writerow({k: r.get(k, "") for k in fieldnames})

    # issues.csv
    write_csv(os.path.join(REPORTS, "issues.csv"),
              ["worker", "page", "button_text", "selector", "type", "status", "detail"],
              [b for b in buttons if b.get("status") == "FAIL"])
    # no_response_buttons.csv
    write_csv(os.path.join(REPORTS, "no_response_buttons.csv"),
              ["worker", "page", "button_text", "selector", "type", "status", "detail", "screenshot"],
              noresp_rows)
    # unexpected_buttons.csv
    write_csv(os.path.join(REPORTS, "unexpected_buttons.csv"),
              ["worker", "page", "button_text", "selector", "type", "status", "detail"],
              unexpected_rows)
    # buttons.csv（全量）
    write_csv(os.path.join(REPORTS, "buttons.csv"),
              ["worker", "page", "button_text", "selector", "type", "status", "detail", "api_calls", "screenshot"],
              buttons)

    # ===== Markdown 报告 =====
    md = f"""# 基于源码 + 真实前端交互的管理后台自动化测试报告

## 1. 执行概览

| 项目 | 值 |
|------|-----|
| 测试时间 | {now} |
| 目标地址 | https://sandyun.top:8001/admincc/#/login |
| 测试方式 | Playwright + 系统 Chrome（真实点击）+ 登录 API 直调注入 |
| 并行 Worker | 10 |
| 覆盖页面 | {pages_tested} |
| 测试按钮总数 | {total} |
| 通过 | {pass_n} |
| 失败 | {fail_n} |
| 无反应 | {noresp_n} |
| 跳过（禁用/危险/外部/导航/UI） | {skipped_n} |
| 通过率（已测按钮） | {pass_n/max(total-skipped_n,1)*100:.1f}% |

## 2. 源码分析结果

### 2.1 技术栈
- **前端**：Vue 3（Vite 构建），部署于 `/admincc/`，含「体验端」+「管理员视图」双模式
- **后端**：Java Spring Boot（manager-api），Python aiohttp（xiaozhi-server）
- **数据库**：MySQL + Redis
- **加密**：SM2（C1C3C2），验证码为 SpecCaptcha 5 位图形

### 2.2 登录方式
- 直调 `POST /xiaozhi/user/login`（SM2 加密 `验证码+密码`）+ ddddocr 识别验证码
- 将 `{{token, expire, clientHash}}` 注入 `localStorage['cc_token']`
- 浏览器打开后自动进入已登录状态

### 2.3 路由与菜单（管理员视图 17 项）
概览(admin)、智能体(agents)、聊天(chat)、记忆(memory)、音色(voices)、模板(templates)、
知识库(knowledge)、模型(models)、设备(devices)、参数(params)、用户(users)、OTA(ota)、
字典(dicts)、服务器(servers)、MCP(mcp)、链路模拟(linksim)、API调试(apis)

## 3. 覆盖率统计

| 指标 | 数值 |
|------|------|
| 页面覆盖 | {pages_tested}/17（按菜单入口） |
| 按钮覆盖（已测+跳过） | {total} 个 |
| 按钮实测（非跳过） | {total - skipped_n} 个 |
| API 4xx/5xx 触发 | 见 frontend_api_errors.csv |
| Console Error | 见各 agent 目录 console 日志 |

## 4. 按钮测试结果汇总

| 页面 | 按钮数 | 通过 | 失败 | 无反应 | 跳过 |
|------|--------|------|------|--------|------|
"""
    for page in sorted(pages_buttons.keys()):
        bs = pages_buttons[page]
        c = collections.Counter(b.get("status", "") for b in bs)
        md += f"| {page} | {len(bs)} | {c.get('PASS',0)} | {c.get('FAIL',0)} | {c.get('无反应',0)} | {sum(v for k,v in c.items() if k.startswith('跳过'))} |\n"

    md += f"""
## 5. 严重问题汇总（{fail_n} 个失败）

"""
    for i, b in enumerate(unexpected_rows[:30], 1):
        md += f"{i}. **[{b.get('worker')}] {b.get('page')} > {b.get('button_text')}**\n"
        md += f"   - 选择器: {b.get('selector')} | 类型: {b.get('type')}\n"
        md += f"   - 问题: {b.get('detail')}\n"
    if not unexpected_rows:
        md += "无失败按钮。\n"

    md += f"""
## 6. 无反应按钮汇总（{noresp_n} 个）

"""
    for i, b in enumerate(noresp_rows[:30], 1):
        md += f"{i}. **[{b.get('worker')}] {b.get('page')} > {b.get('button_text')}**\n"
        md += f"   - 选择器: {b.get('selector')} | 截图: {b.get('screenshot','')}\n"
    if not noresp_rows:
        md += "无无反应按钮。\n"

    md += f"""
## 7. 跳过项与原因

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
## 8. 执行记录

- 10 个 Worker 独立 BrowserContext，并行执行（任务 ID 见 logs/）
- 每个 Worker 产物：artifacts/agent-XX/buttons.csv、pages.json、api_network.json、截图
- 登录态：注入 localStorage['cc_token']，全程未走 Chrome 登录 UI

---
*报告生成时间: {now}*
*执行: WorkBuddy AI Agent（10 Worker 并行）*
"""
    with open(os.path.join(REPORTS, "automation_report.md"), "w", encoding="utf-8") as f:
        f.write(md)

    print(f"总按钮: {total}")
    print(f"通过: {pass_n}, 失败: {fail_n}, 无反应: {noresp_n}, 跳过: {skipped_n}")
    print(f"报告: reports/automation_report.md")


if __name__ == "__main__":
    main()
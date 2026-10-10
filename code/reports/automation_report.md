# 基于源码 + 真实前端交互的管理后台自动化测试报告

## 1. 执行概览

| 项目 | 值 |
|------|-----|
| 测试时间 | 2026-10-10 18:48:01 |
| 目标地址 | https://sandyun.top:8001/admincc/#/login |
| 测试方式 | Playwright + 系统 Chrome 真实点击 + 登录 API 直调注入 localStorage |
| 并行 Worker | 10（独立 BrowserContext） |
| 登录账号 | demo（SM2 加密 + ddddocr 验证码识别） |
| 覆盖页面 | 16 个管理员菜单页面 |
| 按钮总数 | 824 |
| 实际测试按钮 | 231 |
| PASS | 16 |
| FAIL | 214 |
| 无反应 | 1 |
| 跳过（禁用/危险/外部/导航/UI） | 593 |
| 已测按钮通过率 | 6.9% |
| 前端 API 异常（4xx/5xx/失败） | 0 |

## 2. 源码分析结果

### 2.1 技术栈
- 前端：Vue 3 + Vite，部署 `/admincc/`，含「体验端」+「管理员视图」双模式（hash 路由 #/admin/xxx）
- 后端：Java Spring Boot（manager-api，context-path /xiaozhi）+ Python aiohttp（xiaozhi-server）
- 数据库：MySQL + Redis；加密 SM2(C1C3C2)；验证码 SpecCaptcha 5 位

### 2.2 登录方式（直调 API，不走 UI）
- `GET /xiaozhi/user/pub-config` 获取 SM2 公钥
- `GET /xiaozhi/user/captcha?uuid=xx` 获取验证码图，ddddocr 识别
- `POST /xiaozhi/user/login`（SM2 加密 验证码+密码）→ 返回 {token, expire, clientHash}
- 注入 `localStorage['cc_token']` → 打开应用即登录

### 2.3 菜单（17 项管理员路由）
概览(admin)、智能体(agents)、聊天(chat)、记忆(memory)、音色(voices)、模板(templates)、
知识库(knowledge)、模型(models)、设备(devices)、参数(params)、用户(users)、OTA(ota)、
字典(dicts)、服务器(servers)、MCP(mcp)、链路模拟(linksim)、API调试(apis)

## 3. 覆盖率统计

| 指标 | 数值 |
|------|------|
| 页面覆盖（菜单入口） | 16 |
| 按钮实测（非跳过） | 231 |
| 按钮通过 | 16 |
| 按钮失败 | 214 |
| 按钮无反应 | 1 |
| 前端 API 4xx/5xx/失败 | 0 条 |

## 4. Worker 页面分配与执行

| Worker | 负责页面 | 实际测试 slug | 按钮数 |
|--------|----------|---------------|--------|
| 00 | 概览(admin) | admin | 41 |
| 01 | 智能体(agents) | agents | 43 |
| 02 | 聊天(chat) | chat | 29 |
| 03 | 记忆(memory) | memory | 34 |
| 04 | 音色(voices)+模板(templates) | voices,templates | 217 |
| 05 | 知识库(knowledge) | knowledge | 30 |
| 06 | 模型(models)+设备(devices) | models,devices | 105 |
| 07 | 参数(params)+用户(users) | users | 41 |
| 08 | OTA(ota)+字典(dicts)+服务器(servers) | ota,dicts,servers | 198 |
| 09 | MCP(mcp)+链路模拟(linksim)+API调试(apis) | mcp,linksim,apis | 86 |

## 5. 按钮测试结果按页面

| 页面 | 按钮数 | 通过 | 失败 | 无反应 | 跳过 |
|------|--------|------|------|--------|------|
| 🎙 音色 | 174 | 1 | 97 | 0 | 76 |
| 🏠 概览 | 41 | 2 | 6 | 1 | 32 |
| 👥 用户 | 41 | 3 | 2 | 0 | 36 |
| 💬 聊天 | 29 | 1 | 0 | 0 | 28 |
| 📖 字典 | 138 | 1 | 55 | 0 | 82 |
| 📚 知识库 | 30 | 1 | 1 | 0 | 28 |
| 📡 设备 | 41 | 1 | 6 | 0 | 34 |
| 📦 OTA | 29 | 1 | 0 | 0 | 28 |
| 🔗 MCP | 28 | 0 | 0 | 0 | 28 |
| 🖥 服务器 | 31 | 1 | 2 | 0 | 28 |
| 🛠 API调试 | 28 | 0 | 0 | 0 | 28 |
| 🤖 智能体 | 43 | 1 | 8 | 0 | 34 |
| 🧠 记忆 | 34 | 1 | 5 | 0 | 28 |
| 🧩 模型 | 64 | 1 | 24 | 0 | 39 |
| 🧩 模板 | 43 | 1 | 8 | 0 | 34 |
| 🧪 链路模拟 | 30 | 0 | 0 | 0 | 30 |

## 6. 失败按钮明细（214）

1. **[W00] 🏠 概览 > 设备**
   - 选择器: BUTTON>>5 | 截图: G:/demo/21_xiaozhi/code/artifacts\agent-00\admin_5_timeout.png
   - 问题: 点击超时（元素可能被遮挡或不可点击）
2. **[W00] 🏠 概览 > 聊天记录**
   - 选择器: BUTTON>>6 | 截图: G:/demo/21_xiaozhi/code/artifacts\agent-00\admin_6_timeout.png
   - 问题: 点击超时（元素可能被遮挡或不可点击）
3. **[W00] 🏠 概览 > 模板**
   - 选择器: BUTTON>>7 | 截图: G:/demo/21_xiaozhi/code/artifacts\agent-00\admin_7_timeout.png
   - 问题: 点击超时（元素可能被遮挡或不可点击）
4. **[W00] 🏠 概览 > ↻ 刷新**
   - 选择器: BUTTON>>8 | 截图: G:/demo/21_xiaozhi/code/artifacts\agent-00\admin_8_timeout.png
   - 问题: 点击超时（元素可能被遮挡或不可点击）
5. **[W00] 🏠 概览 > 1**
   - 选择器: BUTTON>>11 | 截图: G:/demo/21_xiaozhi/code/artifacts\agent-00\admin_11_timeout.png
   - 问题: 点击超时（元素可能被遮挡或不可点击）
6. **[W00] 🏠 概览 > 查看全部**
   - 选择器: BUTTON>>14 | 截图: G:/demo/21_xiaozhi/code/artifacts\agent-00\admin_14_timeout.png
   - 问题: 点击超时（元素可能被遮挡或不可点击）
7. **[W01] 🤖 智能体 > ↻ 刷新**
   - 选择器: BUTTON>>3 | 截图: G:/demo/21_xiaozhi/code/artifacts\agent-01\agents_3_timeout.png
   - 问题: 点击超时（元素可能被遮挡或不可点击）
8. **[W01] 🤖 智能体 > 会话**
   - 选择器: BUTTON>>4 | 截图: G:/demo/21_xiaozhi/code/artifacts\agent-01\agents_4_timeout.png
   - 问题: 点击超时（元素可能被遮挡或不可点击）
9. **[W01] 🤖 智能体 > MCP**
   - 选择器: BUTTON>>5 | 截图: G:/demo/21_xiaozhi/code/artifacts\agent-01\agents_5_timeout.png
   - 问题: 点击超时（元素可能被遮挡或不可点击）
10. **[W01] 🤖 智能体 > 编辑**
   - 选择器: BUTTON>>6 | 截图: G:/demo/21_xiaozhi/code/artifacts\agent-01\agents_6_timeout.png
   - 问题: 点击超时（元素可能被遮挡或不可点击）
11. **[W01] 🤖 智能体 > 会话**
   - 选择器: BUTTON>>8 | 截图: G:/demo/21_xiaozhi/code/artifacts\agent-01\agents_8_timeout.png
   - 问题: 点击超时（元素可能被遮挡或不可点击）
12. **[W01] 🤖 智能体 > MCP**
   - 选择器: BUTTON>>9 | 截图: G:/demo/21_xiaozhi/code/artifacts\agent-01\agents_9_timeout.png
   - 问题: 点击超时（元素可能被遮挡或不可点击）
13. **[W01] 🤖 智能体 > 编辑**
   - 选择器: BUTTON>>10 | 截图: G:/demo/21_xiaozhi/code/artifacts\agent-01\agents_10_timeout.png
   - 问题: 点击超时（元素可能被遮挡或不可点击）
14. **[W01] 🤖 智能体 > 1**
   - 选择器: BUTTON>>14 | 截图: G:/demo/21_xiaozhi/code/artifacts\agent-01\agents_14_timeout.png
   - 问题: 点击超时（元素可能被遮挡或不可点击）
15. **[W03] 🧠 记忆 > ⚡ 快速总结**
   - 选择器: BUTTON>>3 | 截图: G:/demo/21_xiaozhi/code/artifacts\agent-03\memory_3_timeout.png
   - 问题: 点击超时（元素可能被遮挡或不可点击）
16. **[W03] 🧠 记忆 > ↻ 刷新**
   - 选择器: BUTTON>>4 | 截图: G:/demo/21_xiaozhi/code/artifacts\agent-03\memory_4_timeout.png
   - 问题: 点击超时（元素可能被遮挡或不可点击）
17. **[W03] 🧠 记忆 > ☰ 列表**
   - 选择器: BUTTON>>5 | 截图: G:/demo/21_xiaozhi/code/artifacts\agent-03\memory_5_timeout.png
   - 问题: 点击超时（元素可能被遮挡或不可点击）
18. **[W03] 🧠 记忆 > 🕐 时间轴**
   - 选择器: BUTTON>>6 | 截图: G:/demo/21_xiaozhi/code/artifacts\agent-03\memory_6_timeout.png
   - 问题: 点击超时（元素可能被遮挡或不可点击）
19. **[W03] 🧠 记忆 > 🕸 实体图谱**
   - 选择器: BUTTON>>7 | 截图: G:/demo/21_xiaozhi/code/artifacts\agent-03\memory_7_timeout.png
   - 问题: 点击超时（元素可能被遮挡或不可点击）
20. **[W04] 🎙 音色 > ↻ 刷新**
   - 选择器: BUTTON>>3 | 截图: G:/demo/21_xiaozhi/code/artifacts\agent-04\voices_3_timeout.png
   - 问题: 点击超时（元素可能被遮挡或不可点击）
21. **[W04] 🎙 音色 > ▶ 试听**
   - 选择器: BUTTON>>4 | 截图: G:/demo/21_xiaozhi/code/artifacts\agent-04\voices_4_timeout.png
   - 问题: 点击超时（元素可能被遮挡或不可点击）
22. **[W04] 🎙 音色 > 编辑**
   - 选择器: BUTTON>>5 | 截图: G:/demo/21_xiaozhi/code/artifacts\agent-04\voices_5_timeout.png
   - 问题: 点击超时（元素可能被遮挡或不可点击）
23. **[W04] 🎙 音色 > ▶ 试听**
   - 选择器: BUTTON>>7 | 截图: G:/demo/21_xiaozhi/code/artifacts\agent-04\voices_7_timeout.png
   - 问题: 点击超时（元素可能被遮挡或不可点击）
24. **[W04] 🎙 音色 > 编辑**
   - 选择器: BUTTON>>8 | 截图: G:/demo/21_xiaozhi/code/artifacts\agent-04\voices_8_timeout.png
   - 问题: 点击超时（元素可能被遮挡或不可点击）
25. **[W04] 🎙 音色 > ▶ 试听**
   - 选择器: BUTTON>>10 | 截图: G:/demo/21_xiaozhi/code/artifacts\agent-04\voices_10_timeout.png
   - 问题: 点击超时（元素可能被遮挡或不可点击）
26. **[W04] 🎙 音色 > 编辑**
   - 选择器: BUTTON>>11 | 截图: G:/demo/21_xiaozhi/code/artifacts\agent-04\voices_11_timeout.png
   - 问题: 点击超时（元素可能被遮挡或不可点击）
27. **[W04] 🎙 音色 > ▶ 试听**
   - 选择器: BUTTON>>13 | 截图: G:/demo/21_xiaozhi/code/artifacts\agent-04\voices_13_timeout.png
   - 问题: 点击超时（元素可能被遮挡或不可点击）
28. **[W04] 🎙 音色 > 编辑**
   - 选择器: BUTTON>>14 | 截图: G:/demo/21_xiaozhi/code/artifacts\agent-04\voices_14_timeout.png
   - 问题: 点击超时（元素可能被遮挡或不可点击）
29. **[W04] 🎙 音色 > ▶ 试听**
   - 选择器: BUTTON>>16 | 截图: G:/demo/21_xiaozhi/code/artifacts\agent-04\voices_16_timeout.png
   - 问题: 点击超时（元素可能被遮挡或不可点击）
30. **[W04] 🎙 音色 > 编辑**
   - 选择器: BUTTON>>17 | 截图: G:/demo/21_xiaozhi/code/artifacts\agent-04\voices_17_timeout.png
   - 问题: 点击超时（元素可能被遮挡或不可点击）
31. **[W04] 🎙 音色 > ▶ 试听**
   - 选择器: BUTTON>>19 | 截图: G:/demo/21_xiaozhi/code/artifacts\agent-04\voices_19_timeout.png
   - 问题: 点击超时（元素可能被遮挡或不可点击）
32. **[W04] 🎙 音色 > 编辑**
   - 选择器: BUTTON>>20 | 截图: G:/demo/21_xiaozhi/code/artifacts\agent-04\voices_20_timeout.png
   - 问题: 点击超时（元素可能被遮挡或不可点击）
33. **[W04] 🎙 音色 > ▶ 试听**
   - 选择器: BUTTON>>22 | 截图: G:/demo/21_xiaozhi/code/artifacts\agent-04\voices_22_timeout.png
   - 问题: 点击超时（元素可能被遮挡或不可点击）
34. **[W04] 🎙 音色 > 编辑**
   - 选择器: BUTTON>>23 | 截图: G:/demo/21_xiaozhi/code/artifacts\agent-04\voices_23_timeout.png
   - 问题: 点击超时（元素可能被遮挡或不可点击）
35. **[W04] 🎙 音色 > ▶ 试听**
   - 选择器: BUTTON>>25 | 截图: G:/demo/21_xiaozhi/code/artifacts\agent-04\voices_25_timeout.png
   - 问题: 点击超时（元素可能被遮挡或不可点击）
36. **[W04] 🎙 音色 > 编辑**
   - 选择器: BUTTON>>26 | 截图: G:/demo/21_xiaozhi/code/artifacts\agent-04\voices_26_timeout.png
   - 问题: 点击超时（元素可能被遮挡或不可点击）
37. **[W04] 🎙 音色 > ▶ 试听**
   - 选择器: BUTTON>>28 | 截图: G:/demo/21_xiaozhi/code/artifacts\agent-04\voices_28_timeout.png
   - 问题: 点击超时（元素可能被遮挡或不可点击）
38. **[W04] 🎙 音色 > 编辑**
   - 选择器: BUTTON>>29 | 截图: G:/demo/21_xiaozhi/code/artifacts\agent-04\voices_29_timeout.png
   - 问题: 点击超时（元素可能被遮挡或不可点击）
39. **[W04] 🎙 音色 > ▶ 试听**
   - 选择器: BUTTON>>31 | 截图: G:/demo/21_xiaozhi/code/artifacts\agent-04\voices_31_timeout.png
   - 问题: 点击超时（元素可能被遮挡或不可点击）
40. **[W04] 🎙 音色 > 编辑**
   - 选择器: BUTTON>>32 | 截图: G:/demo/21_xiaozhi/code/artifacts\agent-04\voices_32_timeout.png
   - 问题: 点击超时（元素可能被遮挡或不可点击）

## 7. 无反应按钮（1）

1. **[W00] 🏠 概览 > ⬇ 导出报表** | 5秒内无 API 请求、无 DOM 变化、无弹窗

## 8. 前端 API 异常（0）

无 API 异常。

## 9. 跳过项统计

| 原因 | 数量 |
|------|------|
| 跳过-危险 | 119 |
| 跳过-导航控件 | 352 |
| 跳过-禁用 | 26 |
| 跳过-纯UI控件 | 96 |

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
*报告生成: 2026-10-10 18:48:01 | 执行: WorkBuddy AI（10 Worker 并行，第三轮修正后）*

# 基于源码 + 真实前端交互的管理后台自动化测试报告

## 1. 执行概览

| 项目 | 值 |
|------|-----|
| 测试时间 | 2026-10-10 19:22:34 |
| 目标地址 | https://sandyun.top:8001/admincc/#/login |
| 测试方式 | Playwright + 系统 Chrome 真实点击 + 登录 API 直调注入 localStorage |
| 并行 Worker | 10（独立 BrowserContext） |
| 登录账号 | demo（SM2 加密 + ddddocr 验证码识别） |
| 覆盖页面 | 16 个管理员菜单页面 |
| 按钮总数 | 476 |
| 实际测试按钮 | 58 |
| PASS | 16 |
| FAIL | 41 |
| 无反应 | 1 |
| 跳过（禁用/危险/外部/导航/UI） | 418 |
| 已测按钮通过率 | 27.6% |
| 前端 API 异常（4xx/5xx/失败） | 0 |

## 2. 源码分析结果

### 2.1 技术栈
- 前端：Vue 3 + Vite，部署 `/admincc/`，含「体验端」+「管理员视图」双模式（hash 路由 #/admin/xxx）
- 后端：Java Spring Boot（manager-api，context-path /yuhe）+ Python aiohttp（yuhe-server）
- 数据库：MySQL + Redis；加密 SM2(C1C3C2)；验证码 SpecCaptcha 5 位

### 2.2 登录方式（直调 API，不走 UI）
- `GET /yuhe/user/pub-config` 获取 SM2 公钥
- `GET /yuhe/user/captcha?uuid=xx` 获取验证码图，ddddocr 识别
- `POST /yuhe/user/login`（SM2 加密 验证码+密码）→ 返回 {token, expire, clientHash}
- 注入 `localStorage['cc_token']` → 打开应用即登录

### 2.3 菜单（17 项管理员路由）
概览(admin)、智能体(agents)、聊天(chat)、记忆(memory)、音色(voices)、模板(templates)、
知识库(knowledge)、模型(models)、设备(devices)、参数(params)、用户(users)、OTA(ota)、
字典(dicts)、服务器(servers)、MCP(mcp)、链路模拟(linksim)、API调试(apis)

## 3. 覆盖率统计

| 指标 | 数值 |
|------|------|
| 页面覆盖（菜单入口） | 16 |
| 按钮实测（非跳过） | 58 |
| 按钮通过 | 16 |
| 按钮失败 | 41 |
| 按钮无反应 | 1 |
| 前端 API 4xx/5xx/失败 | 0 条 |

## 4. Worker 页面分配与执行

| Worker | 负责页面 | 实际测试 slug | 按钮数 |
|--------|----------|---------------|--------|
| 00 | 概览(admin) | admin | 37 |
| 01 | 智能体(agents) | agents | 35 |
| 02 | 聊天(chat) | chat | 25 |
| 03 | 记忆(memory) | memory | 30 |
| 04 | 音色(voices)+模板(templates) | voices,templates | 64 |
| 05 | 知识库(knowledge) | knowledge | 26 |
| 06 | 模型(models)+设备(devices) | models,devices | 71 |
| 07 | 参数(params)+用户(users) | users | 34 |
| 08 | OTA(ota)+字典(dicts)+服务器(servers) | ota,dicts,servers | 80 |
| 09 | MCP(mcp)+链路模拟(linksim)+API调试(apis) | mcp,linksim,apis | 74 |

## 5. 按钮测试结果按页面

| 页面 | 按钮数 | 通过 | 失败 | 无反应 | 跳过 |
|------|--------|------|------|--------|------|
| 🎙 音色 | 29 | 1 | 3 | 0 | 25 |
| 🏠 概览 | 37 | 2 | 6 | 1 | 28 |
| 👥 用户 | 34 | 3 | 1 | 0 | 30 |
| 💬 聊天 | 25 | 1 | 0 | 0 | 24 |
| 📖 字典 | 28 | 1 | 2 | 0 | 25 |
| 📚 知识库 | 26 | 1 | 1 | 0 | 24 |
| 📡 设备 | 34 | 1 | 4 | 0 | 29 |
| 📦 OTA | 25 | 1 | 0 | 0 | 24 |
| 🔗 MCP | 24 | 0 | 0 | 0 | 24 |
| 🖥 服务器 | 27 | 1 | 2 | 0 | 24 |
| 🛠 API调试 | 24 | 0 | 0 | 0 | 24 |
| 🤖 智能体 | 35 | 1 | 5 | 0 | 29 |
| 🧠 记忆 | 30 | 1 | 5 | 0 | 24 |
| 🧩 模型 | 37 | 1 | 7 | 0 | 29 |
| 🧩 模板 | 35 | 1 | 5 | 0 | 29 |
| 🧪 链路模拟 | 26 | 0 | 0 | 0 | 26 |

## 6. 失败按钮明细（41）

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
11. **[W01] 🤖 智能体 > 1**
   - 选择器: BUTTON>>14 | 截图: G:/demo/21_xiaozhi/code/artifacts\agent-01\agents_14_timeout.png
   - 问题: 点击超时（元素可能被遮挡或不可点击）
12. **[W03] 🧠 记忆 > ⚡ 快速总结**
   - 选择器: BUTTON>>3 | 截图: G:/demo/21_xiaozhi/code/artifacts\agent-03\memory_3_timeout.png
   - 问题: 点击超时（元素可能被遮挡或不可点击）
13. **[W03] 🧠 记忆 > ↻ 刷新**
   - 选择器: BUTTON>>4 | 截图: G:/demo/21_xiaozhi/code/artifacts\agent-03\memory_4_timeout.png
   - 问题: 点击超时（元素可能被遮挡或不可点击）
14. **[W03] 🧠 记忆 > ☰ 列表**
   - 选择器: BUTTON>>5 | 截图: G:/demo/21_xiaozhi/code/artifacts\agent-03\memory_5_timeout.png
   - 问题: 点击超时（元素可能被遮挡或不可点击）
15. **[W03] 🧠 记忆 > 🕐 时间轴**
   - 选择器: BUTTON>>6 | 截图: G:/demo/21_xiaozhi/code/artifacts\agent-03\memory_6_timeout.png
   - 问题: 点击超时（元素可能被遮挡或不可点击）
16. **[W03] 🧠 记忆 > 🕸 实体图谱**
   - 选择器: BUTTON>>7 | 截图: G:/demo/21_xiaozhi/code/artifacts\agent-03\memory_7_timeout.png
   - 问题: 点击超时（元素可能被遮挡或不可点击）
17. **[W04] 🎙 音色 > ↻ 刷新**
   - 选择器: BUTTON>>3 | 截图: G:/demo/21_xiaozhi/code/artifacts\agent-04\voices_3_timeout.png
   - 问题: 点击超时（元素可能被遮挡或不可点击）
18. **[W04] 🎙 音色 > ▶ 试听**
   - 选择器: BUTTON>>4 | 截图: G:/demo/21_xiaozhi/code/artifacts\agent-04\voices_4_timeout.png
   - 问题: 点击超时（元素可能被遮挡或不可点击）
19. **[W04] 🎙 音色 > 编辑**
   - 选择器: BUTTON>>5 | 截图: G:/demo/21_xiaozhi/code/artifacts\agent-04\voices_5_timeout.png
   - 问题: 点击超时（元素可能被遮挡或不可点击）
20. **[W04] 🧩 模板 > ↻ 刷新模板**
   - 选择器: BUTTON>>3 | 截图: G:/demo/21_xiaozhi/code/artifacts\agent-04\templates_3_timeout.png
   - 问题: 点击超时（元素可能被遮挡或不可点击）
21. **[W04] 🧩 模板 > ⚡ 用模板创建**
   - 选择器: BUTTON>>4 | 截图: G:/demo/21_xiaozhi/code/artifacts\agent-04\templates_4_timeout.png
   - 问题: 点击超时（元素可能被遮挡或不可点击）
22. **[W04] 🧩 模板 > 编辑**
   - 选择器: BUTTON>>5 | 截图: G:/demo/21_xiaozhi/code/artifacts\agent-04\templates_5_timeout.png
   - 问题: 点击超时（元素可能被遮挡或不可点击）
23. **[W04] 🧩 模板 > 预览**
   - 选择器: BUTTON>>6 | 截图: G:/demo/21_xiaozhi/code/artifacts\agent-04\templates_6_timeout.png
   - 问题: 点击超时（元素可能被遮挡或不可点击）
24. **[W04] 🧩 模板 > 1**
   - 选择器: BUTTON>>14 | 截图: G:/demo/21_xiaozhi/code/artifacts\agent-04\templates_14_timeout.png
   - 问题: 点击超时（元素可能被遮挡或不可点击）
25. **[W05] 📚 知识库 > ↻ 刷新列表**
   - 选择器: BUTTON>>3 | 截图: G:/demo/21_xiaozhi/code/artifacts\agent-05\knowledge_3_timeout.png
   - 问题: 点击超时（元素可能被遮挡或不可点击）
26. **[W06] 🧩 模型 > ↻ 刷新**
   - 选择器: BUTTON>>3 | 截图: G:/demo/21_xiaozhi/code/artifacts\agent-06\models_3_timeout.png
   - 问题: 点击超时（元素可能被遮挡或不可点击）
27. **[W06] 🧩 模型 > ↻ 刷新**
   - 选择器: BUTTON>>4 | 截图: G:/demo/21_xiaozhi/code/artifacts\agent-06\models_4_timeout.png
   - 问题: 点击超时（元素可能被遮挡或不可点击）
28. **[W06] 🧩 模型 > 测试**
   - 选择器: BUTTON>>5 | 截图: G:/demo/21_xiaozhi/code/artifacts\agent-06\models_5_timeout.png
   - 问题: 点击超时（元素可能被遮挡或不可点击）
29. **[W06] 🧩 模型 > 停用**
   - 选择器: BUTTON>>6 | 截图: G:/demo/21_xiaozhi/code/artifacts\agent-06\models_6_timeout.png
   - 问题: 点击超时（元素可能被遮挡或不可点击）
30. **[W06] 🧩 模型 > 编辑**
   - 选择器: BUTTON>>7 | 截图: G:/demo/21_xiaozhi/code/artifacts\agent-06\models_7_timeout.png
   - 问题: 点击超时（元素可能被遮挡或不可点击）
31. **[W06] 🧩 模型 > 启用**
   - 选择器: BUTTON>>18 | 截图: G:/demo/21_xiaozhi/code/artifacts\agent-06\models_18_timeout.png
   - 问题: 点击超时（元素可能被遮挡或不可点击）
32. **[W06] 🧩 模型 > 1**
   - 选择器: BUTTON>>35 | 截图: G:/demo/21_xiaozhi/code/artifacts\agent-06\models_35_timeout.png
   - 问题: 点击超时（元素可能被遮挡或不可点击）
33. **[W06] 📡 设备 > ↻ 刷新**
   - 选择器: BUTTON>>3 | 截图: G:/demo/21_xiaozhi/code/artifacts\agent-06\devices_3_timeout.png
   - 问题: 点击超时（元素可能被遮挡或不可点击）
34. **[W06] 📡 设备 > ✎ 改名**
   - 选择器: BUTTON>>4 | 截图: G:/demo/21_xiaozhi/code/artifacts\agent-06\devices_4_timeout.png
   - 问题: 点击超时（元素可能被遮挡或不可点击）
35. **[W06] 📡 设备 > ⇄ 绑定**
   - 选择器: BUTTON>>5 | 截图: G:/demo/21_xiaozhi/code/artifacts\agent-06\devices_5_timeout.png
   - 问题: 点击超时（元素可能被遮挡或不可点击）
36. **[W06] 📡 设备 > 1**
   - 选择器: BUTTON>>12 | 截图: G:/demo/21_xiaozhi/code/artifacts\agent-06\devices_12_timeout.png
   - 问题: 点击超时（元素可能被遮挡或不可点击）
37. **[W07] 👥 用户 > 1**
   - 选择器: BUTTON>>12 | 截图: G:/demo/21_xiaozhi/code/artifacts\agent-07\users_12_timeout.png
   - 问题: 点击超时（元素可能被遮挡或不可点击）
38. **[W08] 📖 字典 > ↻ 刷新**
   - 选择器: BUTTON>>3 | 截图: G:/demo/21_xiaozhi/code/artifacts\agent-08\dicts_3_timeout.png
   - 问题: 点击超时（元素可能被遮挡或不可点击）
39. **[W08] 📖 字典 > 编辑**
   - 选择器: BUTTON>>4 | 截图: G:/demo/21_xiaozhi/code/artifacts\agent-08\dicts_4_timeout.png
   - 问题: 点击超时（元素可能被遮挡或不可点击）
40. **[W08] 🖥 服务器 > ♻️ 重启管理服务**
   - 选择器: BUTTON>>3 | 截图: G:/demo/21_xiaozhi/code/artifacts\agent-08\servers_3_timeout.png
   - 问题: 点击超时（元素可能被遮挡或不可点击）

## 7. 无反应按钮（1）

1. **[W00] 🏠 概览 > ⬇ 导出报表** | 5秒内无 API 请求、无 DOM 变化、无弹窗

## 8. 前端 API 异常（0）

无 API 异常。

## 9. 跳过项统计

| 原因 | 数量 |
|------|------|
| 跳过-危险 | 8 |
| 跳过-导航控件 | 352 |
| 跳过-禁用 | 26 |
| 跳过-纯UI控件 | 32 |

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
*报告生成: 2026-10-10 19:22:34 | 执行: WorkBuddy AI（10 Worker 并行，第三轮修正后）*

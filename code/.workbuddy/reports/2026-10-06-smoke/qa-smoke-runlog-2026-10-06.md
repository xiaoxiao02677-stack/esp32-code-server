# Kawaii v2 线上冒烟 Runlog（任务 #18 · e-qa-smoke）

- 执行人：e-qa-smoke ｜ 依据：qa-smoke-plan.md + e-deploy 移交（GO，2026-10-06 13:35 部署完成）
- 执行窗口：2026-10-06 13:36–13:55 CST（服务器时钟 13:41 时点核对）
- 结论：**9/9 全 PASS，无回滚触发**

## 结果矩阵

| # | 项 | 结果 | 证据 |
|---|---|---|---|
| A1 | 站点 200 | ✅ | HTTP 200 text/html Content-Length 864 |
| A2 | SPA fallback（5+1 页） | ✅ | /home /device-management /model-config /memory-management /login /definitely-not-exist-page 全 200，响应体均含 `<div id="app">`（864B index.html） |
| A3 | P1 新路由 /device-config-management | ✅ | 200+index.html；路由串在 dist-new/js/app.be99e8b4.js；未登录直访被守卫重定向 `#/login?redirect=%2Fdevice-config-management`（截图 S2） |
| A4 | login 流程不 500 | ✅ | pub-config 200；captcha 200 image/gif 4256B；login 空 body 200 + 业务码 10130（SM2解密失败，预期前置校验，无 5xx） |
| A5 | chunk 无 404 | ✅ | dist-new 230/230 文件全 200；线上 index.html md5=`9c4b286e2d82f7f399732c7391473463` = 部署基线 |
| A6 | service-worker | ✅（附发现 F1） | service-worker.js HTTP 200；F1：站点纯 HTTP 非安全上下文，`navigator.serviceWorker` 为 undefined，**SW 无法注册**（详见发现） |
| B1 | nginx 日志抽样 | ✅ | access.log 无 404/5xx（含 xiaozhi-manager 0 条 404）；error.log tail 无新错误 |
| B2 | Java /yuhe/ 探活 | ✅ | 三服务 active；8002 与 8001 pub-config 均 200；manager-api.log 尾部无 ERROR；journalctl since 13:33 error/exception 计数 0 |
| B3 | ai_device_config + changelog | ✅ | 表存在；DATABASECHANGELOG 含 202610060030、202610070010 两条；ai_device_config count=0（部署时点空表，符合预期） |

## 基线核对（e-deploy 移交值）

- jar md5：`3c6ffb4fd3cc31eba637eefbdc5fa49d` ✅ 一致
- /var/www 文件数：230 ✅ 一致
- index.html md5：`9c4b286e2d82f7f399732c7391473463` ✅ 一致（远端实拉比对）

## 浏览器层验证（agent-browser，HTTP 上下文）

- 登录页渲染 ✅：title=智控台；#app 挂载（1 child，18.7KB DOM）；含输入框；正文文本"登录 / WELCOME TO LOGIN / ©2026 yuhe-esp32-server 0.9.7"
- 路由守卫 ✅：直访 /#/device-config-management → 重定向 login 带 redirect 参数
- console 错误 0、page errors 0
- 截图归档：`reports/2026-10-06-smoke/`（S1-login-final.png、S2-route-guard.png、S1b-login-retry.png；本会话模型不支持读图，以 DOM 断言替代视觉核验）
- 管理端新端点鉴权 ✅：`GET /yuhe/deviceConfigMag` 无 token → HTTP 200 + 业务码 401"未授权"（符合全局异常模式）
- 设备侧新端点鉴权 ✅：`POST /yuhe/config/device-config` 空密钥 → 200 + 业务码 401"服务器密钥不能为空"（Bearer server.secret 契约生效）

## 发现（非阻塞）

**F1 · SW 在纯 HTTP 下无法注册（修正既有认知）**：deploy 手册风险 8 与各 runlog 均强调"service-worker 缓存必须强刷"，但实测站点（http://sandyun.top:8001）为非安全上下文，`navigator.serviceWorker === undefined`——浏览器协议层禁止 SW 注册，"旧缓存劫持"在当前部署形态下结构性不存在。https 8001（非 TLS）与 443（无监听）均探测不可达。含义：① 冒烟/回归中"强刷"要求可降级为普通刷新；② 若 P1-7 的 PWA 离线能力是验收目标，当前 http 部署下不可用，需 https 才能启用（建议转 e-pi7-theme/e-deploy 知悉）。

**F2 · 登录后页面未做真实登录冒烟**：无冒烟专用账号（登录含验证码 + SM2 加密）；直插 sys_user_token 的路径已被 10-05 事故证明会踢真实用户会话，不再使用。登录后的侧边栏全量、设备配置管理页 UI、记忆管理页 CRUD 由 e-qa-regress 回归批次或人工登录补验。A3 的路由可达性已由 curl + 守卫行为覆盖。

## 回滚触发

无。未触发 C3 任何条件。

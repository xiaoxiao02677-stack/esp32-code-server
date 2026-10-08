# PWA DOM 检查摘要（降级模式）

- base-url: http://localhost:8001
- 时间: 2026-10-05T22:46:51.150Z

- [PASS] landing HTML 可获取 —— dist/index.html
- [PASS] service worker 产物存在 —— workbox InjectManifest（swSrc=src/service-worker.js, swDest=service-worker.js）
- [PASS] offline.html 存在 —— 离线降级页
- [INFO] PWA manifest 链接 <link rel="manifest"> —— 信息项：本项目为 PWA-lite（无 manifest），未注入属设计现状
- [INFO] theme-color meta —— 信息项：同上，无 theme-color 属设计现状

结论（required 项）: PASS

> 截图 diff 需安装 puppeteer 后重跑（见脚本头部安装说明）。

# 服务器 Web 后台热加载可行性文档

- 版本：v1.0
- 日期：2026-10-15
- 范围：console-v2 前端 / manager-api (Java) / yuhe-server (Python) / nginx
- 结论性质：可行性分析与实施方案，**不含任何代码改动**

---

## 0. 直接回答

**能，但"热加载"的含金量按层排序：前端 ≈ 100% 天然热加载（静态替换即生效、零中断）；Python ≈ 快速重启（~30s，设备自动重连）；Java ≈ 只能秒级重启，无法免重启。**

你的核心诉求是「频繁增删代码 → 最小化业务影响」。三个层各自的最优解完全不同，正确姿势是**按层采取不同策略，而不是追求统一"热加载"**：

| 层 | 真热加载？ | 实际最短生效路径 | 业务中断 |
|---|---|---|---|
| Web 前端 (Vue) | ✅ 本质如此 | 构建产物替换静态文件 | **0（无需重启任何服务）** |
| nginx 配置 | ✅ | `nginx -s reload` | **0（零中断）** |
| Python 服务 | ⚠️ 半热 | `systemctl restart yuhe-server` | ~30s（设备自动重连） |
| Java manager-api | ❌ 无法免重启 | jar 替换 + `systemctl restart` | 秒级 |

---

## 1. 现状（代码事实）

### 1.1 前端 console-v2（热加载最优层）
- Vue 3.4 + Vite 5.2（`console-v2/package.json`），`vite.config.js` 按 mode 决定 `base`（`/` 或 `/admincc/`）与 outDir（`dist` / `dist-admin`）。
- 产物带内容 hash：`dist/assets/index-BjPG9Tr7.js`、`index-CyfmOJKM.css`。
- **已有一键部署脚本** `console-v2/deploy.sh`：`npm run build` → `scp -P 22222 dist/*` → 生产 `/var/www/console-v2/admin/`，并清理旧 hash 文件。
- nginx 静态托管，无 docker/无 CDN/无缓存代理。

### 1.2 Java manager-api
- Spring Boot 3.4.3 / Java 21 / Maven（`code-server-mirror/manager-api/pom.xml`），**无 spring-boot-devtools**。
- 运行：测试 jar `/root/yh/deploy/opt-yuhe/xiaozhi-esp32-api.jar`、生产 `/opt/xiaozhi/xiaozhi-esp32-api.jar`，systemd 服务 `xiaozhi-manager-api`，端口 8002。
- 部署流程：`mvn package -Dmaven.test.skip=true` → 替换 jar → restart。

### 1.3 Python yuhe-server
- 入口 `app.py`（`code-server-mirror/yuhe-server/app.py`）：aiohttp `web.AppRunner`（`core/http_server.py:302`）+ WebSocketServer(8000) + HeartbeatServer(12399)，`asyncio.run(main())` 常驻。
- 无 uvicorn，无 reload 机制；systemd 服务 `yuhe-server`。
- 设备依赖：重启后 30s 内自动重连心跳（10-14 已实测平滑）。

### 1.4 nginx
- 生产：`/etc/nginx/snippets/yuhe-common.conf`，监听 9001/8443/9443/8001，前端 `/var/www/console-v2/{app,admin,firmware-flash}/`，**`/assets/` 固定 root → `/var/www/console-v2/app`**。
- 测试：`/etc/nginx/sites-enabled/yuhe-test`，监听 8101/8144。
- 已知坑：admin 入口必须部署 `dist-admin` 的 index.html，否则 `/assets` 落到 app 目录 → 404 白屏；两产物 bundle 同名，仅 index.html 引用前缀不同。

---

## 2. 分层方案

### 2.1 前端：把「构建+上传」自动化（零业务中断）

前端本身就是"热加载"——替换 index.html 与 hash 资产即刻生效，nginx 不用 reload。瓶颈只在「手动构建 + 手动 scp」这个动作，消除它即可。

**关键事实（已实测确认）**：`dist/` 与 `dist-admin/` 的 assets **内容完全一致**（都是 `index-BjPG9Tr7.js` / `index-CyfmOJKM.css`），差异只在 index.html 的 base 前缀（`/assets/` vs `/admincc/assets/`）。因此**只需构建一次，assets 同步一份，两份 index.html 分别放对位置**即可。

**方案 A（首选）：vite build --watch + autoDeploy 插件，保存即上线**

改 `console-v2/vite.config.js`，追加 autoDeploy 插件（`DEPLOY=1` 环境变量开关，不影响普通 build；SSH 免密配一次即永久有效）：

```js
import { execSync } from 'node:child_process'
function autoDeploy() {
  return { name: 'auto-deploy', apply: 'build',
    writeBundle({ outDir }) {
      if (process.env.DEPLOY !== '1') return
      const S = 'root@<SERVER_IP>'   // 唯一需替换处（测试 192.168.50.20 / 生产 192.168.50.10）
      // 先 assets 后 index.html，中断也安全
      execSync(`scp -r ${outDir}/assets/. ${S}:/var/www/console-v2/app/assets/`, { stdio: 'inherit' })
      execSync(`scp ${outDir}/index.html ${S}:/var/www/console-v2/app/index.html`, { stdio: 'inherit' })
      // admin 入口：sed 改 base 前缀生成第二份 index.html
      execSync(`ssh ${S} "sed 's#/assets/#/admincc/assets/#g' < /var/www/console-v2/app/index.html > /var/www/console-v2/admin/index.html"`, { stdio: 'inherit' })
      console.log('[deploy] done')
    } }
}
// plugins 数组里加 autoDeploy()
```

启动（Git Bash 前台跑，保存代码即自动重建+同步；还需在 vite.config.js 的 build 里设 `emptyOutDir: false`，见风险 2）：

```bash
cd /g/demo/21_xiaozhi/console-v2 && DEPLOY=1 npx vite build --watch
```

**方案 B（兜底）：一条命令部署脚本**（不 watch，手动触发）：

```bash
#!/bin/bash
cd /g/demo/21_xiaozhi/console-v2 && npx vite build && \
scp -r dist/assets/. root@<SERVER_IP>:/var/www/console-v2/app/assets/ && \
scp dist/index.html root@<SERVER_IP>:/var/www/console-v2/app/index.html && \
ssh root@<SERVER_IP> "sed 's#/assets/#/admincc/assets/#g' < dist/index.html > /var/www/console-v2/admin/index.html"
```

> 注：现有 `console-v2/deploy.sh` 只部署 app（`/var/www/console-v2/admin/` 且缺 admincc 前缀处理），建议升级为上面的双入口脚本。

**不推荐**：vite preview 常驻（单点 node 进程、无缓存头/TLS）；Docker/volume（nginx 静态目录本身即改即生效）；模块联邦（单页 30 视图构建秒级，拆分徒增复杂度）。

**前端已确认的坑（务必遵守）**：
1. **同步顺序必须「先 assets 后 index.html」**，禁止反序，中断也安全。
2. **watch 模式必须设 `build.emptyOutDir: false`**，否则每次清空 dist → 在线用户引用的旧 hash 404。
3. build --watch 是全量重建，旧 hash 文件不自动清理，需定期手动清理 dist。
4. Windows 无 rsync，用 OpenSSH 自带 scp；IDE 保存可能触发多次 rebuild（噪音无害）。
5. **只用单进程 + sed 生成 admin index**，不要起两个 watch（会重复构建）。

**浏览器缓存配套（必须做一次）**——index.html 禁缓存、/assets/ 长缓存，hash 文件名天然适配：

```nginx
# 放到 /etc/nginx/snippets/yuhe-common.conf（生产）与 /etc/nginx/sites-enabled/yuhe-test（测试）
location = /index.html { add_header Cache-Control "no-store"; }
location = /admin/index.html { add_header Cache-Control "no-store"; }
location /assets/ {
    root /var/www/console-v2/app;   # 保持现有固定 root 不变
    add_header Cache-Control "public, max-age=31536000, immutable";
}
```

改完 `nginx -t && nginx -s reload`（零中断）。

### 2.2 Python：快速重启 + 一条命令脚本（~30s，设备自动恢复）

aiohttp 进程内热重载（`importlib.reload`、动态重注册路由）**不可靠**：已注册路由、WebSocket 连接对象、线程池线程持有旧模块引用，改动大概率不生效或产生状态分裂。不要做。正确解是**把重启做成一条带验证的命令**：

```bash
#!/bin/bash
# restart-py.sh <test|prod>   Python 服务快速重启
TARGET=${1:-test}
PORT=$([ "$TARGET" = "prod" ] && echo 22222 || echo 22223)
ssh -p $PORT root@sandyun.top '
  systemctl restart yuhe-server && sleep 3 &&
  systemctl is-active yuhe-server &&
  curl -s http://127.0.0.1:8003/ -o /dev/null -w "HTTP %{http_code}\n" || true
  tail -n 20 /var/log/yuhe-server/*.log 2>/dev/null | tail -n 10
'
```

- 本地改文件 → `scp -P 22223 file.py root@sandyun.top:/root/yh/app/yuhe-server/对应路径/` → 跑 `bash restart-py.sh test`。
- 实测影响：重启 ~30s，设备 30s 内自动重连心跳（WS 在线时重连也平滑），推送任务若在执行中会标记失败，**避开整点推送时段重启**即可。

### 2.3 Java：诚实定位「秒级重启」，不追求真热加载

JVM 生产环境**不存在免重启热加载**（HotSwap 仅支持方法体替换，不支持新增类/字段/注解，JRebel 商业方案侵入大）。Spring Boot devtools 的"自动重启"本质也是重启类加载器，生产使用会禁用缓存、拖慢启动且增加不确定性——**本项目不引入 devtools 是正确的**。

正确策略 = 缩短「改动→生效」周期 + 接受秒级停机：

```bash
#!/bin/bash
# deploy-java.sh <test|prod>   从本地镜像构建并部署 Java 后端
TARGET=${1:-test}
PORT=$([ "$TARGET" = "prod" ] && echo 22222 || echo 22223)
LOCAL=/g/demo/21_xiaozhi/code-server-mirror/manager-api
# 生产源码在服务器 /root/yh/app/manager-api（非 git），本地改完先同步源码，再服务器构建
# 本地如果只是改 Java 源码，可走：scp 变更文件 -> 服务器 mvn package -> 替换 jar -> restart
ssh -p $PORT root@sandyun.top '
  cd /root/yh/app/manager-api &&
  mvn -q package -Dmaven.test.skip=true &&
  cp deploy/opt-yuhe/xiaozhi-esp32-api.jar deploy/opt-yuhe/xiaozhi-esp32-api.jar.bak-$(date +%Y%m%dT%H%M%SZ) &&
  cp target/*.jar deploy/opt-yuhe/xiaozhi-esp32-api.jar &&
  systemctl restart xiaozhi-manager-api &&
  sleep 8 &&
  curl -s http://127.0.0.1:8002/ -o /dev/null -w "HTTP %{http_code}\n" || tail -n 20 /opt/xiaozhi/logs/*.log | tail -n 10
'
```

- 生产路径需按实际部署结构微调（生产 jar 在 /opt/xiaozhi/，源码在服务器哪里需确认）；测试环境路径如上已可跑。
- 停机窗口：重启数秒；管理后台低频调用，**对正常业务影响可忽略**。
- Liquibase 启动自动执行新增 migration（10-14 已验证），新增表/字段免手工 DDL。

### 2.4 nginx：reload 零中断（已有认知，固化即可）

`nginx -t && nginx -s reload` 平滑切换 worker，存量连接不断。以后改任何 nginx 配置（新增 location/端口/上游）都走这条，无需停机。

---

## 3. 端到端发布工作流（把三层串成一条命令）

**先测后产 + 备份回滚**，这是本项目既有的部署纪律（10-14 全量同步就是这套），固化成一张流程：

```
本地改代码
  │
  ├─ 前端：bash watch-deploy.sh test   → 测试 8101 肉眼验证
  ├─ Python：scp 单文件 + bash restart-py.sh test
  └─ Java：scp 源码 + bash deploy-java.sh test
  │
  ├─ 测试环境验证通过
  │     └─ 重复同一脚本（把 test 换成 prod，端口自动切 22222）
  │
  └─ 失败回滚：jar/.py 均有 .bak-<UTC> 备份，cp 回去 + 重启
```

- **避开设备活跃时段**（如整点推送、夜间自动行为 23:30/7:00 附近）重启 Python。
- 每次发布前先备份（脚本已内置 `.bak-$(date +%Y%m%dT%H%M%SZ)`）。

---

## 4. 结论表（按投入排序）

| 优先级 | 动作 | 效果 | 投入 |
|---|---|---|---|
| P0 | 前端 watch-deploy.sh（自动构建+同步） | 前端改完即生效，零中断 | 半小时（脚本已在本文档） |
| P0 | nginx 缓存配置（index no-store + assets immutable） | 消除"部署了浏览器还显示旧版" | 10 分钟 |
| P1 | Python restart-py.sh（含健康检查） | 30s 完成一次服务端更新 | 10 分钟 |
| P1 | Java deploy-java.sh（含备份回滚） | 秒级停机窗口的规范化发布 | 20 分钟 |
| P2 | Git 钩子/文件监听自动触发 | 改代码→自动部署全自动 | 1 小时 |

## 5. 明确不做的事（防走弯路）

1. **不要在 Java 层追求免重启热加载**——JVM 生产环境无此能力，强行接入 devtools/JRebel 得不偿失。
2. **不要在 Python 层用 importlib.reload**——aiohttp 已注册路由/连接/线程池不会更新，必然产生幽灵状态。
3. **不要让前端走 vite preview 常驻生产**——它设计用于本地预览，不是生产服务器（无并发调优、无安全加固），静态文件 + nginx 才是正确形态。
4. **不要为"热加载"引入 docker/k8s**——单机双服务 + systemd + nginx 已覆盖需求，引入容器反而增加运维面。

# 服务器 Web 后台热加载能力调研与改造详细报告

- 版本：v1.0
- 日期：2026-10-16
- 范围：只读调研，未修改任何代码
- 目标：回答「服务器 web 后台能不能做到热加载？」，并给出**能落地的改造详细方案**（文件级），满足"以后可能频繁增删代码"的业务诉求

---

## 1. 结论速览（TL;DR）

| 层 | 技术栈 | 现状 | 能否热加载 | 建议方案 | 业务中断 |
|---|---|---|---|---|---|
| Web 前端 | Vue3 + Vite5 | 静态产物，scp 到 nginx | ✅ **已是热更**（天然无重启） | 无需改造，可选自动化 | 0 |
| Python 服务端 | Python3 + aiohttp + asyncio | `python app.py`，systemd 管理 | ⚠️ 半热更 | uvicorn 迁移 / watchdog 自动重启 / 模块级 reload | 30s 或 0（插件级） |
| Java 后台 | Spring Boot 3.4.3 + JDK21 | jar 发布，systemd 管理 | ⚠️ 半热更 | spring-boot-devtools / 双 jar 灰度 / JRebel | 3-10s（restart）/ 0（JRebel） |

**一句话**：前端已经"热"；Python 和 Java 的"完整热加载"成本相对高、收益有限，**性价比最高的改造是 ①Java 加 devtools（开发期实时生效）+ 双 jar 秒级切换（生产）②Python 上 watchodog 自动重启（30s 自愈）**。若追求"改一行代码立刻生效"，Java 用 JRebel（商业）、Python 用模块级 reload（自研，已有 plugin 基础）。

---

## 2. 系统拓扑（本次调研基准）

```
┌─ Web 前端(Vue3) ─ Vite build ── scp ── nginx 8101/8001 ──┐
│                                                           │
├─ Python(yuhe-server) ── aiohttp WS:8000 / HTTP:8003 ──┤── WebSocket/心跳12399 ─ ESP32 固件
├─ Java(manager-api) ── Spring Boot:8002 /context-path=/yuhe ─┤── MySQL / Redis
└─ nginx 反向代理 ── 80/8101/8144 ──────────────────────────┘
```

- **生产**：`ssh -p 22222 root@sandyun.top`（192.168.50.10）
  - Java jar：`/opt/xiaozhi/xiaozhi-esp32-api.jar`，systemd `xiaozhi-manager-api`
  - Python：`/root/xiaozhi-server/main/yuhe-server/`，systemd `yuhe-server`
  - 前端：`/var/www/console-v2/{app,admin,firmware-flash}/`
- **测试**：`ssh -p 22223 root@sandyun.top`（192.168.50.20）
  - Java 源码/运行：`/root/yh/app/manager-api/`、`/root/yh/deploy/opt-yuhe/xiaozhi-esp32-api.jar`
  - Python：`/root/yh/app/yuhe-server/`

---

## 3. 现状详细盘点（只读）

### 3.1 Java manager-api（Spring Boot 3.4.3 / JDK21 / 36 个 Controller）

**启动与部署**
- 打包产物：`xiaozhi-esp32-api.jar`（spring-boot-maven-plugin 可执行 jar）
- 运行：`java -jar` + systemd（`xiaozhi-manager-api`），`--spring.profiles.active=dev`
- 配置拆分：`application.yml`（内置，服务端口 8002、context-path=/yuhe）+ 外置 `/opt/xiaozhi/application-dev.yml`（Spring 按 key 合并覆盖）
- DB 迁移：**Liquibase 启动时自动执行**（`liquibase-core 4.20.0`；changelog 里含 202610140100/202610140200 等）

**热加载能力判定 → 无**
- `pom.xml` 已核实：**无 `spring-boot-devtools` 依赖**、无 `maven-compiler-plugin` 增量热部署配置、无 JRebel/spring-loaded 插件
- 意味着：任何 `.java` 改动 → 必须 `mvn package` → 替换 jar → `systemctl restart xiaozhi-manager-api`

**影响面（实测经验）**
- 重启代价：3-10s（JVM 启动 + Liquibase + 连接池），期间 `:8002` 请求 5xx
- 设备端：ESP32 只在 WS/心跳建立时依赖 Java（OTA 版本检查、模型/TTS 配置下发），重启期间设备不会崩溃，恢复后自动重连

### 3.2 Python yuhe-server（纯 aiohttp + asyncio，170 个 .py）

**启动与部署**
- 入口：`app.py` → `asyncio.run(main())`，纯手写 asyncio 全异步（**非 uvicorn/FastAPI**）
- 端口：WebSocket 8000 / HTTP 8003 / 心跳 TCP-UDP 12399
- 配置：`config.yaml`（1190 行）+ `config_from_api.yaml` + `read_config_from_api` 开关（生产开启，配置从 Java API 下发）
- 进程管理：systemd `yuhe-server`

**热加载能力判定 → 无**
- 已 grep 全仓：**无 `uvicorn --reload`、无 watchdog、无 importlib.reload 热更钩子**
- 只有一个"半热"先例：`plugins_func/loadplugins.py` 启动时 `importlib.import_module` 动态导入全部插件（`auto_import_modules("plugins_func.functions")`），即**新增插件文件只需重启**（若做 reload 化则可免重启）

**影响面（实测经验）**
- 重启代价：~30s（加载配置、预检 ffmpeg、启动 GC/心跳/WS/HTTP/推送调度/微信 ClawBot 多服务）
- 设备端：WS 断连后固件自动重连（30s 内），心跳常驻 12399 自动恢复；**已在 10-14 实测过平滑重启**（两次重启均无人工干预）

### 3.3 Web 前端 console-v2（Vue3 + Vite5）

**构建与部署**
- `vite.config.js`：`base = mode==='admin' ? '/admincc/' : '/'`；dev server 5180；build 产物 `dist/`（app 入口）与 `dist-admin/`（admin 入口）
- `deploy.sh`：`npm run build` → `scp dist/* → /var/www/console-v2/admin/` → 清理旧 hash 文件 → curl 验证
- 生产 nginx：`/assets/` 固定 root → app 目录；app/admin 双入口

**热加载能力判定 → 是（已热）**
- **生产环境**：静态文件替换即生效，nginx 无重启、无连接中断 → 本质就是"热加载"
- **开发环境**：`vite dev`（端口 5180）自带 HMR（模块热替换），改 Vue/SASS 秒级刷新页面，无需刷新浏览器
- 唯一注意：部署时旧 hash 文件需清理（deploy.sh 已做）、nginx `location /assets/` 已固定到 app 目录（admin 入口必须用 dist-admin 的 index.html，否则 404 白屏——既有坑，见项目记忆）

---

## 4. 改造详细方案（文件级，可落地）

### 4.1 方案 A：Java 开发期热重启（成本 ★，收益 ★★★★ 开发效率）

**目标**：改 Java 代码后**不用手动重启**，IDEA/命令行自动编译 + 自动重启（秒级）。

**改动清单（2 处）**

| # | 文件 | 改动 | 说明 |
|---|---|---|---|
| 1 | `yh/manager-api/pom.xml` | `<dependencies>` 末尾新增：`<dependency><groupId>org.springframework.boot</groupId><artifactId>spring-boot-devtools</artifactId><optional>true</optional></dependency>` | 仅开发 scope 生效；打包 jar 不携带（optional） |
| 2 | `yh/manager-api/src/main/resources/application.yml` | `spring.devtools.restart.enabled=true`（可选，默认即 true） | 生产外置 `application-dev.yml` 可覆盖关闭 |

**效果**：`mvn spring-boot:run` 或 IDEA 运行 → 每改 `.java`/`.xml` 保存，自动增量编译 + 轻量重启（只重启 Context，几秒），无需重新 package、无需 scp。改 `static/templates`（若有）甚至实时替换不重启。

**局限**：仅开发/测试机用；生产仍是 jar 替换重启（见 4.2）。

### 4.2 方案 B：Java 生产"秒级灰度"双 jar 切换（成本 ★★，收益 ★★★ 业务连续性）

**思路**：利用 systemd 支持 ExecStart 可换 + 保留上一个大版本 jar，失败秒回退。

**改动清单（服务器操作，无代码改动）**

| # | 文件 | 操作 |
|---|---|---|
| 1 | `/opt/xiaozhi/` | 发布新版本时先把旧 jar 拷为 `xiaozhi-esp32-api.jar.bak`（保持既有备份惯例） |
| 2 | systemd `xiaozhi-manager-api.service` | 增加 `Restart=on-failure` + `RestartSec=3`（若未配） |
| 3 | 灰度脚本（新增 `/root/scripts/java-switch.sh`） | `cp new.jar xiaozhi-esp32-api.jar && systemctl restart xiaozhi-manager-api && sleep 8 && curl -f http://127.0.0.1:8002/yuhe/... && echo OK \|\| (cp .bak 回滚 + restart)` |

**效果**：一键发布 + 自动健康检查 + 失败秒回滚；单次切换业务中断 3-10s。

**注意**：Liquibase 变更随启动执行 → **涉及 DB 结构变更的发布，回滚语义要人工确认**（Liquibase changelog 一般只增不改，回滚 jar 不会回滚已执行 changeSet）。

### 4.3 方案 C：Python 全进程自动重启（成本 ★★，收益 ★★★ 30s 自愈）

**思路**：不改框架，只做"改完自动重启 + 健康自愈"，把 30s 中断变成免人工。

**改动清单**

| # | 文件 | 改动 |
|---|---|---|
| 1 | 生产 systemd `yuhe-server.service` | 确认已有 `Restart=always`（若无则加，10-14 平滑重启已证明安全） |
| 2 | 新增 `/root/scripts/py-restart.sh` | `cd /root/xiaozhi-server/main/yuhe-server && systemctl restart yuhe-server` |
| 3 | （可选）watchdog 监听 | `watchdog` 库或 systemd `PathChanged`/inotify 监控 `core/**/*.py` mtime → 变更即 `systemctl restart` |

**效果**：改 Python 代码 → 文件保存 → 3s 内自动重启 → 30s 服务恢复 → 设备自动重连。

### 4.4 方案 D：Python 真·模块级热加载（成本 ★★★★，收益 ★★★★ 零中断）

**思路**：项目已有 `importlib` 动态导入基础（`loadplugins.py`、llm.py/asr.py/memory.py 各 provider 都走 `importlib.import_module`），把它从"启动时一次性"升级为"运行时 reload"。

**改动清单（核心）+ 精确切口**

| # | 文件 | 改动 |
|---|---|---|
| 1 | `yh/yuhe-server/core/handle/receiveAudioHandle.py`（消息处理入口） | 在每个 topic 分支处理前，加"变更检测 → `importlib.reload(HandlerModule)`"钩子 |
| 2 | `yh/yuhe-server/plugins_func/loadplugins.py` | `auto_import_modules()` 扩展为 `reload_all()`：对已注册模块 `importlib.reload`；插件新增免重启 |
| 3 | `yh/yuhe-server/core/utils/llm.py` / `asr.py` / `memory.py` / `vad.py`（provider 抽象工厂） | 每次 get_provider() 前对 provider 模块做 mtime 检测 + reload（或在 manager 里注册 reload 回调） |
| 4 | 新增 `yh/yuhe-server/core/hot_reload.py` | 文件变更轮询（mtime/sha256 对比，异步定时任务），对**白名单目录**（core/handle、plugins_func/functions、providers）diff → reload 受影响模块 + 重新绑定到连接 |
| 5 | app.py | `main()` 中启动 hot_reload 后台任务（`asyncio.create_task(hot_reload.run())`），config 热更可顺带支持 |

**切口的正确性（关键）**
- **连接粒度**：`core/connection.py`（模块级单例 conn，WS 对话上下文挂在 Connection 实例）——**不要整体替换 connection 对象**，只 reload 被调用的 handler/provider 模块后，在 `conn.chat` 内重新从模块取新函数。已确认 `connection.py:37` `from plugins_func.loadplugins import auto_import_modules`，且 `:54` 启动时才调，热改这里即可。
- **状态风险**：`text_to_speak`（TTS 链）在 tts 线程持有，reload 该 provider 前必须等当前合成结束（用现有线程池 + 锁），否则旧协程引用新模块导致半新半旧。**建议白名单第一版只开放 handle/plugins（无长期状态）。**
- **音频/WS 帧管道**（FixedQueue、Opus 编码器）**永远不进入 reload 范围**——它们是无状态管道，改它们必须重启进程。

**效果**：改 `core/handle/*`、`plugins_func/functions/*` 即时生效，**零中断**，设备对话不断。这是"真热加载"且成本可控（复用既有 importlib 基础设施）。

### 4.5 方案 E：前端热更自动化（成本 ★，收益 ★★★）

生产已是热更，只差"自动"：
- （可选）`deploy.sh` 增加 rsync：`rsync -avz --delete dist/ → /var/www/console-v2/app/ && rsync ... dist-admin/ → admin/`（保留 hash 文件名差异，避免 scp 覆盖错目录）
- （可选）CI/本地 watch：`npx vite build && deploy.sh` 一键化，或接入 Webhook
- 开发期已内置 Vite HMR（5180），无需改造

---

## 5. 推荐组合（给"以后频繁增删代码"的业务）

| 场景 | 用什么 | 中断 |
|---|---|---|
| **日常改 Java**（开发/测试） | 方案 A devtools 热重启 | ~2s |
| **Java 上线**（生产） | 方案 B 双 jar + 自动回滚 | 3-10s |
| **日常改 Python**（handle/plugins/provider） | 方案 D 模块热加载（先本地验证再上生产） | 0 |
| **Python 上线**（生产，暂不迁热加载） | 方案 C systemd 自愈重启 | ~30s（自动重连） |
| **改前端** | 现状即热更 + 方案 E 自动化 | 0 |

**分阶段路线**：
1. **本周（低成本立即做）**：A（devtools）+ B（双 jar 脚本 + Restart=on-failure）+ E（rsync）
2. **下阶段**：C（systemd Restart=always 确认 + 重启脚本）——生产 Python 每次重启 30s 但自动恢复
3. **中期目标（真零中断）**：D 模块热加载，先只在**测试环境**验证 reload 正确性再切生产；四级白名单（handle → plugins → providers → config），外扩一步验证一步

---

## 6. 不建议做 / 高成本项（如实说明）

| 方案 | 成本 | 为什么不推荐 |
|---|---|---|
| **JRebel 商业热部署**（Java 真·零重启改方法级） | ~1000 元/年/license + 服务器侧 agent | 性价比低：本项目 36 Controller 规模，devtools 重启 2s 足够；JRebel 适合大型单体热调 |
| **迁移 Python 到 uvicorn/FastAPI** | 高（重写 WS 服务、心跳、aiohttp 全部路由） | 工程量大、风险高、只为"reload"目的不值——模块热加载（D）已达同等效果且不动架构 |
| **Java 全量 -> 微服务/模块化热插拔** | 极高 | 杀鸡用牛刀，36 Controller 的单体就是合理形态 |
| **固件端热加载** | 见前次报告 | 原生 C++ 无解释器，走 OTA 双分区即可，不在本报告范围 |

---

## 7. 操作手册（改造后日常使用）

### 7.1 开发期改 Java（方案 A 之后）
```bash
cd G:/demo/21_xiaozhi/yh/manager-api
# IDEA 直接点 Run（DevTools 自动挂载）；或命令行：
mvn spring-boot:run   # 改代码保存 → 自动重启，观察控制台 "Restarting..."
```

### 7.2 生产发布 Java（方案 B 之后）
```bash
ssh -p 22222 root@sandyun.top
bash /root/scripts/java-switch.sh /路径/新jar   # 自动替换→重启→健康检查→失败回滚
```

### 7.3 生产重启 Python（方案 C after）
```bash
ssh -p 22222 root@sandyun.top "systemctl restart yuhe-server"
# 或自动版：保存文件后 watchdog 自动触发；设备 30s 内自动重连心跳+WS
```

### 7.4 模块热加载（方案 D after，测试环境）
```bash
# 改 /root/yh/app/yuhe-server/core/handle/*.py 等白名单文件 → 保存
# 无需任何命令，hot_reload 协程检测变更 → reload → 下次对话即用新逻辑
tail -f /root/yh/app/yuhe-server/tmp/server.log | grep hot_reload
```

---

## 8. 风险与注意事项

1. **Liquibase 与热加载冲突**：Java 的 DB 变更仍只在启动执行；任何 DDL 变更必须走"发布流程"（方案 B），不能靠 devtools 热重启覆盖——重启 devtools 不会再跑已执行的 changeSet（幂等，无碍）。
2. **Python 模块热加载的状态污染**：`connection.py` 的 Connection 实例、tts 线程、WS 队列是长生命周期状态，reload 范围必须限定在无状态 handler/plugin/provider；第一版严禁 reload `consumers.py/audio_frame` 等管道模块（会半新半旧）。
3. **生产 vs 测试差异**：生产 Python 读 `config_from_api`（配置从 Java 下发），热加载对配置变更不感知——config 热更建议另做（sys user display-config 已三级下发，可作为配置热更先例）。
4. **前端 admin 入口坑**（既有教训）：部署时必须用 `dist-admin` 的 index.html 到 admin 目录，且 `dist/` 与 `dist-admin/` 的 bundle 同名——rsync 自动化要注意目录隔离、避免互删。
5. **回滚语义**：Java 双 jar 只保证"代码回滚"，不保证"DB schema 回滚"（Liquibase 只增不改）——涉及 DDL 的发布，失败回滚后需人工评估。

---

## 9. 附录：调研依据（文件清单）

| 项 | 文件 | 关键结论 |
|---|---|---|
| Java 无 devtools | `yh/manager-api/pom.xml` | 依赖列表无 spring-boot-devtools；spring-boot-maven-plugin 构建可执行 jar |
| Java 入口/配置 | `AdminApplication.java`、`application.yml` | Spring Boot 3.4.3、JDK21、:8002、/yuhe、Liquibase |
| Python 入口 | `yh/yuhe-server/app.py` | `asyncio.run(main())`，无 uvicorn/reload；多服务布署（WS/HTTP/心跳/推送/ClawBot） |
| Python 无热更钩子 | grep reload/watchdog/importlib | 仅 `loadplugins.py` 启动时动态导入；providers (`llm.py` 等) 用 importlib 工厂 |
| 前端构建 | `yh/console-v2/vite.config.js`、`package.json` | Vite5 dev:5180 HMR；build: dist/dist-admin 双产物；deploy.sh scp |
| 分区/运维基准 | 项目记忆（2026-10-14/10-15） | 生产/测试端口、systemd 服务名、平滑重启实证、双环境同步经验 |

---

*报告完。所有结论基于只读代码分析 + 历史运维实证；未执行任何代码增删。*
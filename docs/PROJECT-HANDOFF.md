# 小智语音助手项目 · 交接手册（PROJECT HANDOFF）

> 更新：2026-10-07 18:40 CST ｜ 用途：给接手的 Agent / 开发者一读即懂全局
> 纪律：生产服务器所有操作走 `.workbuddy` 现成工具；改动前先备份；重要操作写 runlog

---

## 1. 服务器连接信息（生产 sandyun.top）

| 项 | 值 |
|---|---|
| SSH | `sandyun.top:22222`，用户 `root`，密码 `Ymm6088.`（仅密码认证，key 被拒） |
| SSH 工具 | `python G:/demo/21_xiaozhi/code/.workbuddy/ssh_run.py "CMD"` |
| SFTP 上传 | `MSYS_NO_PATHCONV=1 python .workbuddy/sftp_push.py LOCAL REMOTE` |
| SFTP 下载 | `MSYS_NO_PATHCONV=1 python .workbuddy/sftp_pull.py REMOTE LOCAL` |
| MySQL | 服务器本机 `root/123456`，库 `xiaozhi_esp32_server`（服务器无远程，经 ssh_run 执行 mysql） |
| Redis | 127.0.0.1:6379 无密码（同样经 ssh） |

**端口与服务（systemd）**：

| 端口 | 服务 | systemd 单元 | 说明 |
|---|---|---|---|
| 8000 | Python WebSocket | `xiaozhi-server` | 设备语音通道 `/xiaozhi/v1/` |
| 8001 | nginx | `nginx` | 静态站 + 反代：`/xiaozhi/`→8002、`/xiaozhi/v1/`→8000、`/cc/`→新控制台 |
| 8002 | Java manager-api | `xiaozhi-manager-api` | jar 在 `/opt/xiaozhi/xiaozhi-esp32-api.jar`，`--spring.profiles.active=dev` |
| 8003 | Python HTTP | （随 xiaozhi-server） | OTA/vision/记忆内部API/TTS试听；`/api/**` 仅回环+Bearer secret |

**关键路径（服务器）**：
- Python 源码：`/root/xiaozhi-server/main/xiaozhi-server/`（venv 在 `.venv`，带点）
- Java 源码：`/root/xiaozhi-server/main/manager-api/`（mvn 3.8.7 + JDK 21，m2 缓存热）
- 原控制台（renren 系，**有版权纠纷待停用**）：`/var/www/xiaozhi-manager/`
- 新控制台（cc-console）：`/var/www/cc-console/`，访问 `http://sandyun.top:8001/cc/`
- 备份目录：`/root/backup/2026-10-08-doubao-v3/`（jar/DB表/nginx配置/web js 全套）
- Python 日志：`/root/xiaozhi-server/main/xiaozhi-server/data/app.log`
- 服务密钥 `server.secret`：`sys_params` 表 param_code=`server.secret`（Java↔Python 互调 Bearer）

**操作坑（必读）**：
1. Git Bash 会把 `/root/...` 转成 `C:/...`——**所有含绝对路径参数必须前缀 `MSYS_NO_PATHCONV=1`**
2. ssh_run.py 命令含括号/嵌套引号会崩——**复杂脚本一律 base64**：`echo <B64> | base64 -d > /tmp/x.sh && bash /tmp/x.sh`
3. Java 接口业务错误 HTTP 仍是 200（`{"code":401}` 包体），判断成败看响应体
4. 本地无 rsync：传输走 tar → sftp_push → 服务器解包 → rsync（服务器内有 rsync）
5. 服务器构建 Java 用 `-Dmaven.test.skip=true`（测试类有历史遗留编译错误）

---

## 2. 目录结构与镜像说明（本地 G:/demo/21_xiaozhi/）

```
G:/demo/21_xiaozhi/
├── code-server-mirror/     ← ★生产服务器三仓的本地镜像（Java/Python/Web 源码与服务器逐字节对齐）
│   ├── manager-api/           Java 后端（Spring Boot + Shiro + MyBatis-Plus + Liquibase）
│   ├── manager-web/           原控制台前端（Vue2 + element-ui，renren 脚手架，待停用）
│   └── xiaozhi-server/        Python 语音服务（连接调度/TTS/ASR/LLM/记忆 provider）
├── cc-console/             ← ★全新独立控制台（Vue3+Vite+sm-crypto，无版权问题，部署在 /cc/）
├── code/                   工作区（.workbuddy 工具与 runlog 都在这里）
│   ├── .workbuddy/            ★所有部署工具、runlog、memory、生成脚本
│   ├── xiaozhi-esp32/         固件仓镜像（见 §3）
│   └── hermes-agent-main/     hermes 项目源码（mem_holographic 的上游）
└── stylekit/               动画主题库克隆（github.com/AnxForever/stylekit，MIT，/cc/ 动效来源）
```

**镜像纪律**：
- `code-server-mirror` 与生产 md5 对齐（deploy_memory_v1.md 有基线漂移核对方法）；**rsync 排除清单**：`.venv/ data/ config.yaml config_from_api.yaml __pycache__ models/ music/ tmp/`——误删 `data/`（记忆库+.config.yaml）和 `models/`（904M SenseVoice 权重）是历史事故
- Python 每连接从 Java 拉私有配置，`config.yaml` 不随连接生效，**不同步也不改**
- Web 构建产物目录 `dist-*` 多套（dist-qtts/dist-cc/dist-viz...）是历次构建留档，非部署物

---

## 3. 固件信息

| 项 | 值 |
|---|---|
| 固件仓 | `G:/demo/21_xiaozhi/code/xiaozhi-esp32/`（ESP-IDF 工程） |
| 真机设备 | MAC `14:c1:9f:d1:33:48`，板型 `my-s3-tft`，固件版本 2.5.1 |
| 构建 | `idf.py build` EXIT=0（约19分钟，产物 `xiaozhi.bin` ~2.7MB），构建日志 `.workbuddy/fw_build.log` |
| 连接 | 设备经 `ws://sandyun.top:8001/xiaozhi/v1/`（nginx 转 8000）接入 |
| 配置下发 | 设备每次连接从 Java 拉差异化配置（agent 音色/模型/记忆在改库+重连后生效，无 agent 级缓存残留） |
| 设备云端配置 | `ai_device_config` 表（一设备一行 JSON_MERGE_PATCH 原子 upsert，键白名单 volume/brightness） |
| 真机联调手册 | `.workbuddy/firmware-build-verify.md` §2 + `mqtt-gateway-verify.md`（烧录/透传验证待人工执行） |

---

## 4. 新控制台 cc-console（当前主力开发对象）

- **技术栈**：Vue3 + Vite5 + sm-crypto（仅此三个依赖），`base: '/cc/'`
- **本地**：`G:/demo/21_xiaozhi/cc-console/`；npm 安装必须 `--ignore-scripts` 再手动 `node node_modules/esbuild/install.js`（postinstall 网络坑）
- **构建**：`node_modules/.bin/vite build` → dist → tar → sftp → 解包到 `/var/www/cc-console/`
- **功能（16 页）**：总览/智能体(可视化编辑器：LLM/TTS/音色联动/记忆/ASR/语速/人设提示词)/音色试听(实时合成)/聊天记录(气泡+语音回放)/记忆管理(信任分/反馈/审核/手动添加)/知识库/模型管理(开关)/设备管理/系统参数/用户管理/智能体模板/OTA/数据字典/替换词/服务器节点/API调试(142接口台账)
- **登录**：SM2 加密「验证码+密码」拼接串，字段名 `captchaId`（不是 uuid！），公钥从 `/user/pub-config` 拉
- **API 台账数据**：`src/lib/apiCatalog.js`（15 模块 142 接口，由 `.workbuddy/api_catalog.json` 生成）
- **动效**：stylekit 6 动画（fade-in-up/slide-in-left/border-trace/hover-glow/progress-bar 0.3s/cursor-aura）+ stagger 交错，全部带 prefers-reduced-motion 降级

---

## 5. TTS 现状（两套已上线）

| 引擎 | 配置ID | 端点 | 音色 | 备注 |
|---|---|---|---|---|
| 豆包 v3 | `TTS_DoubaoV3`（默认） | POST `https://openspeech.bytedance.com/api/v3/tts/unidirectional` | 11 个（用户账号实际清单，含3个ICL复刻） | resource_id=`seed-tts-2.0`；chunked JSON 流分片 base64 拼接；`voice_instruction` 已预填豆包调调+去台湾腔 |
| 千问 TTS | `TTS_QwenTTS_Flash/Instruct/Audio_*` | maas.qianwenaiapi.com 原生端点 | 98 个预置 | base_url 仅展示参考；平台 /models 拉列表经 Java 代理 `/models/qwenTtsModels` |

- 试听链路：前端 `/models/ttsPreview` (Java, Shiro) → `127.0.0.1:8003/api/tts/preview`（Bearer secret+回环）→ Python `core/api/tts_preview_handler.py` 实时合成
- 凭据都在 `ai_model_config.config_json`（豆包 appid=2717008086；key 见 changelog 202610061700.sql）
- **音色教训**：预置音色必须先实测（曾因混入 moon 系音色导致 55000000 resource mismatch）；豆包 2.0 音色 ID 规律 `_uranus_` 后缀

---

## 6. 记忆系统

- **默认引擎**：`Memory_mem_holographic`（Hermes 移植：SQLite+FTS5+信任分+实体消解+HRR检索，每 agent 一个 `data/memory/{agent_id}.db`）
- 全部模板 `mem_model_id=Memory_mem_holographic`，`chat_history_conf=2`（文字+Opus音频上报）
- 管理 API：`/memory/agents`、`/memory/facts`（增删改查/feedback 信任反馈/review 审核）——新控制台记忆页全可视化
- 其他模式：mem_local_short(LLM总结)/mem0ai(云)/powermem/nomem/mem_report_only
- 用户 agent 当前为「星际游子」（id `a1a8b109945d4dfb9f4da5c303016d3a`，曾用「女友1」已换绑）

---

## 7. 数据库要点（xiaozhi_esp32_server）

| 表 | 用途 |
|---|---|
| `ai_model_config` | 全部 AI 模型配置（config_json 含凭据；改后清 Redis `model:data:{id}`） |
| `ai_model_provider` | 供应器表单定义（fields JSON 驱动前端动态表单；启动时种子会覆盖，自定义注意） |
| `ai_tts_voice` | 音色表（按 tts_model_id 关联；改后设备重连生效） |
| `ai_agent` / `ai_agent_template` | 智能体及模板（chat_history_conf: 0不上报/1文字/2文字+音频） |
| `ai_device_config` | 设备云端配置（JSON_MERGE_PATCH upsert） |
| `sys_params` | 系统参数（server.secret/server.http_port 等） |
| `DATABASECHANGELOG` | Liquibase 执行记录（**已执行的 changelog checksum 锁定不可改，改动需新编号增量文件**） |

**changelog 惯例**：新增 `manager-api/src/main/resources/db/changelog/YYYYMMDDHHMM.sql` + 注册 `db.changelog-master.yaml`；jar 重启时自动执行；紧急可直导 SQL（幂等写法）+ 事后同步源码树。

---

## 8. 部署速查（改了什么→怎么上线）

| 改动 | 流程 |
|---|---|
| Python（provider/api） | 改 mirror → sftp_push 单文件 → 服务器 py_compile → `systemctl restart xiaozhi-server`（provider 动态加载，非 provider 改动才需重启） |
| Java | 改 mirror → tar 上传源文件到服务器源码树 → 服务器 `mvn package -Dmaven.test.skip=true` → 备份旧 jar → cp 到 /opt → `systemctl restart xiaozhi-manager-api`（Liquibase 随启动执行） |
| Web 原控制台 | mirror `npm run build` → tar → rsync `/var/www/xiaozhi-manager/`（注意 service-worker，验收需强刷） |
| 新控制台 | cc-console `vite build` → tar → 解包 `/var/www/cc-console/` |
| DB | 幂等 SQL 直导 + 同步 mirror changelog + 清对应 Redis key |

**runlog 纪律**：每次上线在 `.workbuddy/` 写 `release-<主题>_runlog.md`（含根因/改动/验证/回滚剧本），当日 memory 写 `memory/YYYY-MM-DD.md`。

---

## 9. AOCI 仓库认知（mirror 仓）

- mirror 根有 `aoci.txt`（认知索引 600 条）+ `.aoci/`（基线 1124 文件）
- 现状：**69 个受管文件已漂移、275 个新文件未索引**（本周 TTS/记忆/控制台大量改动所致）
- CLI `D:/INSTALL/aoci/aoci.exe`；Volumes v1 正式认知被治理锁保护（`observe_change_policy` 已从 review_required 调整为 informational、approval-mode=auto，`scope plan` 显示 `人工复核7` 待走 scope apply 审批流）
- 接手提示：大规模改动后跑 `aoci check` / `status`；索引更新走 `baseline scope plan→preview→apply` 治理链，不要手改 `aoci.txt`

---

## 10. 遗留与待办

| 项 | 状态 | 说明 |
|---|---|---|
| 原控制台停用 | **待用户验收后执行** | 版权纠纷；方案：nginx 根路径 `/` 切到 `/var/www/cc-console/` 或下线 `xiaozhi-manager`；备份齐全 |
| 新控制台长尾功能 | 部分 | 声纹注册/音色克隆训练/固件上传/知识库文档上传等走「API调试」页兜底，可视化待补 |
| 三栈真机联调 | 待人工 | 验收清单 v2 场景 0-4 判据未落盘（需真机烧录+观测） |
| secret 轮换 | 受限完成 | 操作包在 `.workbuddy/secret-rotation/`，轮换待部署窗口 |
| PWA 离线 | 受限 | 纯 HTTP 非安全上下文 SW 无法注册，需 https |
| Qwen TTS changelog 登记 | 注意 | `202610071100/1200` 生产已直导，Liquibase 登记依赖下次 jar 重启补跑（幂等安全） |

---

## 11. 常用凭据速查（均已在本文件与 .workbuddy runlog 中存在）

- 生产 SSH：`root@sandyun.top:22222` / `Ymm6088.`
- MySQL：`root/123456`（服务器本机）
- 管理台账号：`demo`（superAdmin；登录需 SM2，密码验证流程见 cc-console `doLogin`）
- 火山豆包：appid `2717008086`，access_token/SecretKey 见 `TTS_DoubaoV3` config_json
- 千问 API key：见 `TTS_QwenTTS_*` config_json（202610061700.sql）

> 涉密提醒：以上凭据仅限本项目运维使用；对外分享文档时先脱敏。

---

*本手册由主理人 Agent 生成；执行细节以 `.workbuddy/` 各 runlog 与 `memory/` 日志为准（2026-10-04 起全量在案）。*

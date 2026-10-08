# 小智项目 · 前后端功能可用性审计报告

> 审计日期：2026-10-09
> 审计方式：20 个只读 Agent 并行排查（Python WS 链路 / ASR / TTS / LLM / 记忆 / 内部 API / MCP / 配置层 / 音频 VAD / OTA / Java Controller / Java 鉴权 / DB schema / Java Service / Java→Python 客户端 / cc-console / admincc 契约 / admincc 页面 / 构建部署 / 端到端契约）
> **本次审计未修改任何代码文件**
> 代码树口径：后端 `G:/demo/21_xiaozhi/code-server-mirror/`（xiaozhi-server / manager-api / manager-web）；前端原控制台 `cc-console`→`/cc/`，新控制台 `console-v2`→`/admincc/`

---

## 一、总体结论

| 层 | 判定 | 说明 |
|---|---|---|
| Java `manager-api` Controller 层 | ✅ 可用 | 173 个端点全部有实现，无空壳 `@xxxMapping` |
| Java Service / 鉴权层 | ⚠️ 部分可用 | 权限注解齐全，但事务与缓存失效缺失较普遍 |
| Python `xiaozhi-server` 主链路（ASR→LLM→TTS→音频） | ✅ 可用 | 依赖真实密钥；默认占位配置下不可用 |
| Python 内部 HTTP API | ❌ 大面积不可用 | **Java↔Python 密钥不同源，默认 5 组内部调用全量 401** |
| 端到端契约（前端↔后端） | ⚠️ 82/84 对齐（≈98%） | 2 个硬断链（405）+ 4 处参数偏差 |
| `/cc/` 原控制台 | ✅ 页面可用 | 少量装饰件 |
| `/admincc/` 新控制台 | ⚠️ 部分可用 | 顾客端 3 个页面为硬编码假数据（纸老虎） |
| 记忆引擎 | ❌ 默认不生效 | `config.yaml:245` `Memory: nomem` |
| 音色「动态语气指令」 | ❌ 未实现 | Java 已下发开关，**无任何 Python 消费方** |
| 构建部署 | ❌ dev 环境阻断 | `vite.config.js` 缺 `/xiaozhi` 代理 |

**一句话结论：后端骨架完整、Controller 层无空实现；真正的阻断集中在「Java↔Python 服务间鉴权不通」「2 个方法不匹配的 405 断链」「记忆与动态指令两个新功能默认/实际未生效」三处，前端则是顾客端 3 页为纸老虎 + 若干死 UI。**

---

## 二、P0 阻断项（必须先修，否则功能直接不可用）

| # | 问题 | 证据（file:line） | 影响 |
|---|---|---|---|
| P0-1 | **Java↔Python 服务间密钥不同源** | Java 侧密钥取自 DB/配置的 UUID；Python `xiaozhi-server/core/...` 在未取到配置时退化为随机 UUID 兜底（`app.py:53-62`），`manage_api_client.py:45-51` 若含「你」字直接抛异常 | 记忆管理 / TTS 试听 / LLM 试聊 / 模型测试 / 配置同步 **5 组内部调用全部 401** |
| P0-2 | **`TimbreEntity` 声明了不存在的 DB 列** | `manager-api/.../timbre/entity/TimbreEntity.java:48,51` 声明 `dynamicInstruction` / `instructionLlmId`，但 `ai_tts_voice` 表只在 `202610070300.sql:12` 加了 `voice_instruction` 列 | MyBatis SELECT 会抛 `Unknown column 'dynamic_instruction'` → **音色列表/详情接口直接报错** |
| P0-3 | **`vision_handler` 硬编码后门** | `xiaozhi-server/core/api/vision_handler.py:37` `if client_id == "web_test_client":` 跳过鉴权 | 任意外部请求带 `client_id=web_test_client` 即可免鉴权调用视觉接口 |
| P0-4 | **`/xiaozhi` 双前缀透传（全局单点）** | Java `application.yml:10` `context-path: /xiaozhi`；前端 `API_BASE='/xiaozhi'` | nginx **必须透传而非剥离** `/xiaozhi` 前缀；一旦配置成 `proxy_pass http://127.0.0.1:8002/;`（带尾斜杠剥离），全站 404 |
| P0-5 | **dev 环境无法联调** | `console-v2/vite.config.js:9` `server: { port: 5180, host: true }` —— 无 `/xiaozhi` → 8002 的 proxy | 本地 `npm run dev` 下所有接口跨域/404，无法开发验证 |

---

## 三、P1 缺陷（功能能跑但有明确正确性/稳定性问题）

### 3.1 Python 连接生命周期

| 问题 | 证据 | 后果 |
|---|---|---|
| **超时任务自等/自取消** | `_check_timeout()`（`connection.py:1789`）在超时分支调用 `await self.close(self.websocket)`（`:1807`）；而 `close()`（`:1612`）内含 `if self.timeout_task and not self.timeout_task.done(): self.timeout_task.cancel(); await self.timeout_task`（`:1635-1638`） | 超时这条关闭路径上，任务 **await 了它自己**。行为未定义（递归取消 / 永久挂起），异常被 `:1808` 的 `except Exception` 吞掉 → **超时后 WebSocket 与 VAD/opus 资源不释放，连接泄漏** |
| 修复建议 | 在 `close()` 中加 `if self.timeout_task is not asyncio.current_task():` 再 await，或改为 `await asyncio.gather(..., return_exceptions=True)` 并屏蔽自身 | |

| 问题 | 证据 | 后果 |
|---|---|---|
| `executor=None` 竞态 | `receiveAudioHandle.py:103`、`intentHandler.py:133,225` | 任务在 executor 初始化完成前被调度 → `TypeError: 'NoneType' object is not callable` |

### 3.2 ASR

- 14 个 provider 文件齐备，但 `models/SenseVoiceSmall` 本地模型缺失，云侧密钥在 DB 初始化脚本中全为 `你的secret_key` 之类占位（`202504112044.sql:13` 等）。
- 真实调用路由是 `/api/asr/recognize`，**不是** `/models/asrRecognize`。
- `asr_recognize_handler.py:118-120` 只把 `temp_path` 传给 provider → 多数 provider 拿不到采样率/格式参数，返回空结果。

### 3.3 TTS（音色指令链路）

| 环节 | 状态 | 证据 |
|---|---|---|
| 运行时音色级指令下发 | ✅ | `ConfigServiceImpl.java:555-557` 把 `voice_instruction` 注入 `config["TTS"][id]`；`doubao_v3.py:66,101-102` 读取；`202610070300.sql:12` 已加列 |
| **音色试听** | ❌ | `TtsPreviewController.java:75,109` 用的是**模型级原始 config**，未注入音色级 `voice_instruction` → 试听与实听效果不一致（这正是"填入音色提示词没更新"的根因之一） |
| **动态语气指令** | ❌ | Java 已下发 `dynamic_instruction=true` / `instruction_llm_id`（`ConfigServiceImpl.java:559-563`），但**Python 侧无任何读取方** → 开关形同虚设 |

### 3.4 LLM

- `fastgpt.py:65-68`、`homeassistant.py:61-64` 的 function_call 分支是残桩（`return None`）→ `connection.py:1229` 处解包时 `TypeError`。
- gemini / dify / coze / AliBL 的 systemPrompt 存在降级路径，未按统一契约注入。

### 3.5 记忆

- `config.yaml:245` `Memory: nomem` → `mem_holographic` 全息记忆引擎**开箱不生效**，需手动改配置才启用。

### 3.6 OTA / 设备下发

- `ota_handler.py:285-290` 白名单判断逻辑**反转**（应为「命中白名单才放行」，现状相反）。
- `/api/asr/` 路由漏配回环防护中间件（对比其它 handler 均有 `_LOOPBACK_ADDRS` 校验）。

### 3.7 Java Service 层

- 多个 Service 的多表写入缺 `@Transactional`。
- 缓存更新后未失效（`ai_model_config` 等热配置改了但 Python 侧仍拿旧值）。

---

## 四、端到端契约：2 个硬断链 + 4 处偏差

### 4.1 硬断链（必然 405）

| 前端调用 | 后端实际方法 | 证据 |
|---|---|---|
| `POST /admin/dict/data/update` | `@PutMapping("/update")` | 前端 `console-v2/src/lib/api.js:222`、注释见 `views/admin/Dicts.vue:47`；后端 `SysDictDataController.java:79` |
| `POST /voiceClone/play/{uuid}` | `@GetMapping("/play/{uuid}")` | 前端 `console-v2/src/lib/api.js:150` `voiceClonePlay`；后端 `VoiceCloneController.java:148` |
| 备注 | 主播放走的是 `api.js:132` 的 `playAudioBlob`（GET，正确，`Chat.vue:130` 使用）→ 该断链只在调用 `voiceClonePlay` 时触发，属**死代码路径**，危害等级 P2 | |

> 另注意：契约文件 `apiCatalog.js:161` 自己写的是 `h:"PUT"`，是**前端实现与自家契约不一致**，不是契约写错。

### 4.2 参数偏差

| 接口 | 前端传 | 后端要 | 证据 |
|---|---|---|---|
| `/datasets` | `limit` | `page_size` | — |
| `/memory/facts` | `limit` | `size` | — |
| `/models/list` | page 从 1 开始 | page 从 0 开始 | — |
| ASR 配置头 | — | `X-Asr-Config-B64` 头名与 Java 发送方不一致 | Java→Python 客户端 |

---

## 五、前端「纸老虎」清单（UI 存在但不控数据）

| 位置 | 问题 |
|---|---|
| `console-v2/src/views/customer/Devices.vue` / `Voices.vue` / `Points.vue` | **硬编码假数据**，未接任何接口；含 17 个无 handler 的按钮 |
| `components/DataTable.vue:10-17` | 分页器是死 UI，翻页不触发请求 |
| `components/TopBar.vue:12` | 搜索框为纯装饰，无绑定 |
| `views/.../Knowledge.vue:194-196` | "检索测试"按钮假实现 |
| `views/.../Params.vue:58` | `_dirty` 恒为 0 → 保存按钮永远不可点/不判定变更 |
| `views/.../Users.vue:86` | 封禁数量统计逻辑反向 |
| `views/.../Templates.vue:26-27` | StatCard 数值硬编码 |

---

## 六、部署侧风险

| 项 | 证据 | 风险 |
|---|---|---|
| nginx `location = /` | `deploy.py:88-91` | 精确匹配根路径，**可能劫持原控制台 `/cc/` 的入口** |
| 端口校验不一致 | `deploy.py:115-117` 打 9443，文档写 8001 | 部署后健康检查对不上 |
| `/xiaozhi` 前缀 | 见 P0-4 | 全局单点，见上 |

---

## 七、建议修复顺序（给执行 Agent 的优先级队列）

1. **P0-2**（音色表缺 2 列）→ 补 migration `ALTER TABLE ai_tts_voice ADD COLUMN dynamic_instruction / instruction_llm_id`，否则音色页直接报错。
2. **P0-1**（密钥同源于一处）→ 统一由 `sys_params` 下发，Python 去掉随机 UUID 兜底，改成启动失败。
3. **P0-5**（vite proxy）→ 加 `/xiaozhi` → `http://<host>:8002` 代理，恢复本地联调。
4. **405 ×2**（改 POST→PUT / 删死代码）+ **4 处参数偏差**。
5. **P0-3** 删 `web_test_client` 后门；**P0-4** 核查 nginx 透传。
6. `connection.py:1635-1638` 自等任务；`executor=None` 竞态；`ota_handler` 白名单反转。
7. TTS 试听注入音色级指令；实现 Python 侧 `dynamic_instruction` 消费方（读短期+长期聊天记录生成口语化指令）。
8. `config.yaml` Memory 默认改为 `mem_holographic`（或明确文档化需手动开启）。
9. 顾客端 3 页接真实接口；DataTable 分页、TopBar 搜索、Params `_dirty`、Users 统计、Templates StatCard。
10. `deploy.py` `location = /` 与端口校验。

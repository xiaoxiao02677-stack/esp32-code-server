# Release Runlog: cc-control 五问题修复（用户反馈第 2 轮）

日期：2026-10-07 22:10 CST ｜ 操作者：hermes-agent
主题：设备绑定补全 / 容器滚动适配 / 模型管理 9 类型+一键测试 / 记忆时间轴+图谱 / MCP 一键测试

## 问题对照与解法

### 问题1：创建智能体要绑定设备（抄原控制台逻辑）
- 原控制台调研结论：设备绑定是 6 位验证码模式（设备屏幕显示 code → 输入 → `POST /device/bind/{agentId}/{deviceCode}`），辅以手动添加（板型+固件版本+MAC → `POST /device/manual-add`）
- 实现：智能体编辑器内嵌「📱 设备绑定」区块：6 位码绑定 + 手动 MAC 添加（details 折叠）+ 已绑设备列表（可解绑）
- 新建智能体保存后自动回填 id，绑定区立即可用（无需重开编辑器）

### 问题2：容器适配屏幕比例（内部滚动）
- 改为"应用窗口"布局：`html/body` 锁 `100vh` 不滚动；`.shell` 全高 flex；`.sidebar`（module-list 内部滚动）与 `.main`（整页内部滚动）各自 `overflow-y: auto`
- modal 已有 `max-height: 86vh` 滚动；细滚动条样式（粉色圆角 8px）；`.page` 底部留白
- 移动端侧栏 fixed 抽屉保持独立滚动

### 问题3：模型管理全类型 + 一键测试
- 原控制台 9 种模型类型：TTS/LLM/ASR/VLLM/Intent/Memory/VAD/Plugin/RAG（来源 ProviderManagement.vue modelTypes）
- 前端：模型管理页重写为 9 类型 tab（带数量徽标），每卡片「⚡ 一键测试」+ 启停开关
- 后端新增：
  - Python `core/api/model_test_handler.py`：`POST /api/model/test?type={modelType}`（Bearer+回环；TTS=真实合成"模型测试。"、LLM=真实对话"请只回复两个字：正常"、ASR/VAD/Memory/Intent/VLLM=工厂实例化校验、Plugin/RAG=配置校验）
  - Java `ModelTestController`：`GET /models/modelTest?modelId&modelType`（Shiro→读 raw config→代理转发，凭据不回传）

### 问题4：记忆管理时间图
- 原控制台有 列表/时间轴/实体图谱 三视图（MemoryTimeline.vue / MemoryGraph.vue，ECharts）
- cc-console 实现：三视图切换（☰ 列表 / 🕐 时间轴 / 🕸 实体图谱）
  - 时间轴：纯 CSS 移植（日期分组倒序 + 类别色标左边框 + 信任分着色 + 检索次数徽标），无新依赖
  - 图谱：Canvas 2D 手绘（实体节点环形布局 + 大小随频次 + 高频发光 + 记忆小点连线 + 图例），免 ECharts

### 问题5：MCP 一键测试
- Java `AgentMcpAccessPointController` 新增 `GET /agent/mcp/test/{agentId}`：
  三重验证 = 接入点地址存在 → HTTP 连通探测（8s 超时，2xx/4xx/405 都算可达）→ 工具列表非空
- 前端 MCP 页加「⚡ 一键测试」按钮 + 结果面板（✅/❌ + 耗时 + 地址 + 明细）

## 部署
- Python：model_test_handler.py + http_server.py（py_compile OK → restart）
- Java：ModelTestController.java + AgentMcpAccessPointController.java（mvn 23s → cp jar → restart）
- Web：vite build（192KB js）→ tar → /var/www/cc-console/（bundle index-DRGJ6lP6.js）

## 验证（e2e_cc_verify2.py，7/7 PASS）
- /api/model/test：401 无 token / 400 缺 body（Python 鉴权+校验生效）
- /models/modelTest、/agent/mcp/test、/device/bind、/device/manual-add：未登录 {"code":401}（路由+Shiro 生效）
- web bundle 本地=线上；xiaozhi-server/manager-api/nginx 三服务 active

## 遗留
- 模型新增/编辑表单（原控制台有 provider 动态表单）未移植——当前模型 CRUD 走「API 调试」页；如需可视化表单是下一轮工作
- MCP 工具"自定义运行"（选工具+填参数+执行）需后端 MCP 客户端执行端点，本轮先交付一键测试（连通+工具列表）

## 回滚
- Python：sftp_push 上一版两文件 → restart
- Java：/root/backup/2026-10-08-doubao-v3/xiaozhi-esp32-api.jar.bak-20261007-ccconsole（第一轮备份）或 git 上一 commit 源码重打
- Web：.workbuddy/cc_dist_new.tar.gz（第一轮）重推

---

## 第三轮追加（2026-10-07 22:40）：LLM 测试报错修复 + 模型 CRUD + 自定义接口

### 根因（链路模拟器报 LLM 问题 = 模型测试全部报错 = 同一 bug）
`'async for' requires an object with __aiter__ method, got generator`：
LLM provider 的 `response()` 是**同步生成器**（`def` + `yield`，主链路 connection.py 用同步 for 消费），
我在 model_test_handler / llm_preview_handler 里误写成 `async for` → 永远 TypeError。
修复：改为同步 for 迭代 + 兼容 chunk 的 tuple/dict/content 形态（与 connection.py 消费方式一致）。

### 模型 CRUD + 自定义接口（前端，模型管理页）
- 每类型「＋ 新增」/「✎ 编辑」/「🗑 删除」（后端端点已存在：POST /models/{type}/{provider}、PUT .../{id}、DELETE /models/{id}）
- 供应器下拉（GET /models/{type}/provideTypes）驱动动态表单字段（fields JSON：key/label/type 密码识别）
- **⭐ 自定义接口（OpenAI 兼容）**：选「自定义接口」→ 预置 api_key/base_url/model_name 三字段 + 任意加字段/删字段 → configJson.type 指定 provider type（默认 openai）

### 验证（服务器实测，真实 token）
- LLM 测试：ok=true「模型响应：正常」2374ms（真实模型对话）
- TTS 测试：ok=true「合成成功 57644 字节」742ms
- Java llmPreview 代理：{"reply":"你好！","elapsed_ms":1418}
- 部署：Python 2 文件 restart + Web bundle index-BrcAZl5R.js

### QA 模拟用户测试
派出 QA agent（deleg_fb7422e2）按 10 项清单用真实会话 token 全链路测试，报告待出（.workbuddy/qa-report-20261007.md）

---

## 第四轮（2026-10-07 22:45）：模板提示词污染修复

### 根因
一键创建的智能体 system_prompt 全是巫医：Java 后端 `AgentCreateDTO` 只有 agentName 字段（前端传的
systemPrompt/modelId 全被 Jackson 丢弃），`createAgent()` 无条件用 getDefaultTemplate()
（sort 最小=巫医）覆盖所有字段 → 无论用哪个模板创建，出来的都是巫医人设。
（voice_instruction 表字段经查全库无污染；用户看到的是被污染的智能体人设。）

### 修复
1. `AgentCreateDTO` 增加 `templateId` 字段（可选）
2. `AgentServiceImpl.createAgent()`：优先 getById(dto.templateId)，找不到才退回默认模板
3. 前端 createAgentFromTemplate 只传 agentName + templateId（服务端按所选模板复制全部字段）
4. 存量修复：被污染的「豆包小何-副本」用豆包小何模板数据回填（system_prompt/tts_*），
   并补 tts_voice_id（TTS_QwenTTS_Flash_V01/Cherry）与 tts_language
5. 部署：服务器 mvn package -Dmaven.test.skip=true（本机无 mvn；testCompile 有预存失败，
   与本次改动无关）→ cp jar → systemctl restart xiaozhi-manager-api；前端 bundle index-C-pkMVOO.js

### 验证（真实 API 全链路）
- 用「好奇男孩」模板一键创建 → system_prompt = 好奇男孩人设 ✓（非巫医）
- 创建后删除测试智能体 ✓
- 模板列表 7 个模板提示词各不相同（DB/API 双确认）✓

---

## 第五轮（2026-10-07 23:10）：链路模拟器 TTS「createObjectURL」崩溃修复

### 症状
浏览器报 `TTS 异常: Failed to execute 'createObjectURL' on 'URL': Overload resolution failed.`

### 根因（两层叠加）
1. **前端**：api() 对二进制端点失败时（Content-Type 变 JSON）返回 JSON 对象，
   模拟器把它当 Blob 传给 URL.createObjectURL → 浏览器崩溃。
   服务端失败原因是 QwenTTS 上游偶发 >25s，Java 代理 TIMEOUT_SECONDS=25 超时抛
   「试听服务不可用」{code:500} JSON。
2. **数据**：智能体音色被配成克隆音色 S_HfQF5xwg2（ai_tts_voice id=2107718544252874754），
   与 TTS_DoubaoV3 的 resource(seed-tts-2.0) 不匹配；矩阵实测 6 种 resource×鉴权组合全部
   被火山上游拒绝（403/55000000）——该克隆音色在此账号下不可用（账号级归属问题，非代码 bug）。

### 修复
1. 前端 api()：JSON 错误体（code!==0 且路径为 ttsPreview/llmPreview/modelTest/api）→ 抛 Error(msg)，
   各调用方 catch 后在阶段错误框显示中文原因（不再 createObjectURL 崩溃）
2. Java TtsPreviewController：TIMEOUT 25s→60s，失败自动重试 1 次
3. Python tts_preview_handler：asyncio.wait_for 55s 超时兜底（504 合成超时，防拖垮事件循环）
4. 数据修复：智能体音色切回可用音色 TTS_DoubaoV3_V01（zh_female_xiaohe_uranus_bigtts 小何）
5. 部署：Python+Java(重新打包)+前端 index-DTaWtWA9.js 全部上线，三服务 active

### 验证
- nginx 全路径 TTS 连测 3 次：audio/wav 115244/111404/134444 字节全 PASS
- 模拟器 E2E（豆包链路）：LLM 538ms 回复 → 音色转换 → TTS 316834 字节 → ALL PASS ✓
- 豆包模型一键测试：合成成功 95050 字节（815ms）✓
- 克隆音色问题已定性为火山账号归属问题，用户如需用克隆音色需在火山控制台核对音色归属 appid

---

## 第六轮（2026-10-07 23:40）：音量控制修复 + 自定义音色

### 问题A：对 LLM 说"调音量"，设备音量不变
**根因**（connection.py 三处堵点，全部与 nointent 模式相关）：
1. `_initialize_intent()`：nointent 分支提前 return → `func_handler`（UnifiedToolHandler）
   永远是 None，工具体系根本没初始化
2. `chat()`：`functions` 只在 `intent_type == "function_call"` 才组装 → nointent 智能体
   调 LLM 时不带任何工具（日志实证：22:29 用户说"把音量调到100%"，LLM 纯文字回绝）
3. 云端配置加载：`Intent_nointent` 跳过插件配置 → 即使传工具，天气/新闻等也无凭据
4. few-shot 工具调用示例注入也仅 function_call

当前智能体（豆包小何-副本）是 Intent_nointent —— 10-05 之前用的是 function_call 所以能用。

**修复**（core/connection.py 4 处）：
- nointent 分支也初始化 UnifiedToolHandler（async 初始化走 event loop）
- chat() 工具组装与 response_with_functions 判定放宽为 `("function_call", "nointent")`
- 插件配置加载去掉 Intent_nointent 跳过（nointent 配置块无 functions 字段时兜底空 dict）
- few-shot 注入同样放宽
- 部署：sftp connection.py → systemctl restart xiaozhi-server（active 无报错）
- 生效条件：设备重连后（工具在 MCP 握手时注册）

### 问题B：自定义添加音色
**实现**（后端接口已存在：POST /ttsVoice、PUT /ttsVoice/{id}、POST /ttsVoice/delete）：
- 音色页升级「音色管理」：每音色 ✎ 编辑 / 🗑 删除 + 顶部「＋ 新增音色」
- 模态字段：名称*、音色代码 tts_voice*（speaker code）、语言、排序、语气指令、试听链接
- 前端 bundle index-Dh_d5ghH.js 已上线

**验证**（真实 API 全链路）：
- 新增 → DB 落库（id=2107854015092224001）✓
- 用新音色试听 → audio/wav 47794 字节真实合成 ✓
- 更新（改名+voice_instruction）→ DB 确认 ✓
- 删除 → DB count=0 ✓

---

## 第七轮（2026-10-08 00:05）：音色页修复 + 意图配置 + 记忆补全 + 设备绑定提示 + 5 主题

### 1. 音色管理点击无反应
根因：loadVoices 的 `if (!this.voiceTtsModel) return;` 静默守卫——voiceTtsModel 未初始化
（loadTtsModels 没跑过）时点击菜单什么都不发生。
修复：loadVoices 自动先拉 TTS 模型列表选默认，再加载音色。

### 2. 智能体编辑器增强
- 新增「意图配置」下拉（Intent 3 项：函数调用/意图LLM/无意图）+ 每项说明 hint
- 编辑/保存链路带 intentModelId（AgentUpdateDTO 已有该字段，PUT 实测落库 ✓）
- 记忆下拉补全：DB 启用 mem_local_short / mem_report_only / nomem（内置免凭据），
  mem0ai/powermem 保留禁用（需用户在模型管理填 key 后启用）+ 每项说明 hint
- Memory 4 选项 / Intent 3 选项（models/names API 实测返回 ✓）

### 3. 设备绑定区
- 未绑定：原位置黄色提示「⚠️ 还没有绑定任何设备…输入 6 位验证码完成绑定」
- 已绑定：原位置显示「✅ 已绑定设备（N）」清单（型号 · 固件版本 · MAC + 解绑按钮）
- 按钮未保存智能体时显示「先保存智能体再绑定」并禁用

### 4. 主题系统（styles/kawaii.css）
- html[data-theme]：kawaii（默认）/ blue蓝白 / dark深色 / purple紫色 / green绿色 / morandi莫兰迪
- 侧栏底部 6 色圆点选择器，localStorage(cc_theme) 持久化，登录页也生效
- 色板按用户提供的规范逐一套用（primary/secondary/accent/bg/surface/text 等）

### 部署
- 前端 bundle index-DkTcOCsv.js 上线（data-theme/theme-swatch/bind-empty-tip/intentModelId 均在）
- 事故与恢复：PUT 验证时误将 systemPrompt 覆盖为 "keep"，已立即用豆包小何模板回滚 ✓

---

## 第八轮（2026-10-08 00:20）：音色模态无法弹出修复

根因：上一轮把「音色新增/编辑模态」错放在了 active==='models' 的 section 内部——
音色页（voices）与模型页是 v-if/v-else-if 互斥分支，切到音色页时模型 section
根本不渲染，模态 DOM 不存在 → 点「＋新增音色」「✎」设了 state 却无模态可见。
修复：模态移到所有 section 之外（main 直属子节点，fixed 定位 z-9000），
音色页/任意页均可弹出。bundle index-CBcOGo0o.js 已上线。

---

## 第九轮（2026-10-08 00:45）：豆包小何-副本测试失败诊断（用户新增音色 S_N8pC5xwg2）

### 诊断结论
用户把智能体音色切到自定义音色「测试」（tts_voice=S_N8pC5xwg2，火山声音复刻/S_ 前缀）。
TTS 合成被火山上游拒绝：code=55000000 resource ID is mismatched with speaker。
矩阵实测（6 组合）：seed-tts-2.0 / volc.megatts.default / seed-icl-1.0 × api_key/双头鉴权
全部失败（资源不匹配 + 403/45000030 无权限）→ 账号级归属问题，非代码 bug。
对照组：官方预置音色（zh_female_xiaohe_uranus_bigtts）和官方 ICL 复刻音色全部合成正常。

### 改进（已部署）
1. Python doubao_v3._friendly_error：火山 55000000/45000030 错误翻译成可操作中文提示
2. tts_preview_handler 错误截断 120→480 字符（保留完整提示）
3. Java TtsPreviewController 500 时透传 Python 详细 msg（不再只报状态码）
→ 现在前端试听/链路模拟器能直接看到「该音色是声音复刻音色，与 resource 不匹配…」的完整指引

### 用户注意事项（已答复）
S_ 前缀 = 声音复刻音色，必须配套：①复刻服务归属的 appid 凭据 ②resource_id=volc.megatts.default
的模型配置；在 cc-console 正确做法是"模型管理→TTS→新增"建一个复刻专用模型。

---

## 第十轮（2026-10-08 00:15）：声音复刻 TTS 全链路打通

### 用户脚本带来的关键情报
用户提供可运行的复刻脚本，resource_id = seed-icl-2.0（声音复刻 2.0）——
此前矩阵测试只试过 seed-icl-1.0 / volc.megatts.default / 10029，均失败。
实测：seed-icl-2.0 + 现有 api_key + S_N8pC5xwg2 → 200 OK 24429 字节 MP3 ✓

### 按步骤操作后的新问题：「请求体缺少 type 字段」
根因：cc-console 模型表单保存时只在「自定义接口」模式才写 configJson.type；
常规供应器（doubao_v3）不写 → Python 端按 type 路由 provider 失败。
修复：
1. saveModelConfig 始终注入 config.type = providerCode（doubao_v3 等）
2. DB 修复用户已建的「豆包声音复刻」模型：json_set $.type=doubao_v3
3. manager-api restart 清缓存；前端 bundle index-sCPWfagP.js 上线

### 最终验证（真实 API 全链路）
- 试听（新模型 3248df0b + S_N8pC5xwg2）：HTTP 200 audio/mpeg 9837 字节 ✓
- 模型一键测试：ok=true 合成成功 13101 字节（551ms）✓
- 用户后续操作：智能体 TTS 引擎切「豆包声音复刻」+ 音色「测试」→ 链路模拟器验证

---

## 第十一轮（2026-10-08 00:30）：自签 HTTPS 证书上线

- 生成自签证书 /etc/nginx/ssl/sandyun.top.{crt,key}（10 年，SAN: sandyun.top /
  www.sandyun.top / 223.247.29.147 / 192.168.50.4）
- nginx server 块新增 listen 8443 ssl（TLS1.2/1.3），原 8001 HTTP 保留不动
  （备份 sites-available/xiaozhi-manager.bak-ssl）
- 验证：8443 监听 ✓ TLS 握手 subject=sandyun.top ✓ API 200 ✓ 原 8001 不受影响 ✓
- 注意：外网访问需在路由器把 8443 映射到服务器 8443（同 22222→22 的方式）

---

## 第十二轮（2026-10-08 00:35）：8001 同端口双协议（HTTPS + 设备 WS 共存）

### 需求
浏览器访问 cc-console 需要 HTTPS（getUserMedia 麦克风 API 要求安全上下文），
但 8001 同时承载设备 WebSocket（ws://sandyun.top:8001/xiaozhi/v1/，有活跃外网设备连接）
——不能简单转 SSL。

### 方案（stream 层 TLS 探测分流）
安装 libnginx-mod-stream；nginx.conf 顶层追加 stream 块：
- 8001 收到 TLS ClientHello → 转内部 9443（SSL web/cc/API）
- 8001 收到明文（http/ws）     → 转内部 9001（原 HTTP server，含设备 WS 反代）
sites-available 的 server 改为 listen 9001 + 8443 ssl + 9443 ssl。
8443（纯 HTTPS）保留。备份：/tmp/xiaozhi-manager.pre-dual。

### 验证（全过）
- https://sandyun.top:8001/cc/ → 200（TLS 握手 subject=sandyun.top）✓
- http://sandyun.top:8001/cc/ → 200（旧书签/设备不受影响）✓
- 设备 WS 升级握手 /xiaozhi/v1/ → 101 Switching Protocols ✓
- https API 代理 /xiaozhi/agent/list → 200 ✓
- 外网设备既有连接（117.67.194.234×3）保持 ESTABLISHED，未断线 ✓

注意：麦克风功能要求页面用 https:// 打开（http 下浏览器禁用 getUserMedia，
本方案 http 仍可用，只是没有麦克风）。

---

## 第十三轮（2026-10-08 00:50）：真机 ASR 失效 + ASR 一键测试报错

### 问题1：ESP32 真机语音无反应（模拟链路正常）
根因链：智能体切到自建复刻模型（3248df0b）→ 该模型 configJson 原本缺 type →
Java getModelByIdFromCache 从 Redis 拿旧缓存（无 type）下发 → Python 组件初始化
「不支持的TTS类型」→ 初始化链在 TTS 中断 → ASR 组件也没初始化 → 语音进来无人处理。
（00:24/00:31/00:33 日志连续三次实例化组件失败）
修复：redis-cli 清 model:data:* 缓存（10 个 key）→ 重验 agent-models 接口
TTS type=doubao_v3 / resource=seed-icl-2.0 / private_voice=S_N8pC5xwg2 全部正确。
设备下次重连即恢复。

### 问题2：ASR 一键测试「missing delete_audio_file」
根因：model_test_handler._test_generic 调 ASR 工厂漏传 delete_audio_file。
修复：factory(provider_type, provider_config, delete_audio_file=True)。
部署后实测 ASR_FunASR：ok=true「ASR 实例化成功」✓

### 附带发现（未改，记录）
ConfigServiceImpl:555-561 当 type=huoshan_double_stream 且音色 S_ 开头时强制
resource_id=seed-icl-1.0 —— 与用户实测可用的 seed-icl-2.0 不一致；
若未来用 huoshan_double_stream 克隆类型+自定义 S_ 音色，需把这里改为 seed-icl-2.0。

---

## 第十四轮（2026-10-08 01:05）：硬件开机显示"连接错误"排查

### 服务器端证据（全部正常）
- 00:55:11 设备完整握手成功：WS 升级 → hello → 配置下发（TTS doubao_v3/seed-icl-2.0 ✓
  ASR_Qwen3Flash ✓ Memory/Intent ✓）→ 组件全初始化 → TTS上报线程启动
  ——上一轮的 Redis 缓存问题已确认修复，设备链路是通的
- 00:57:55 设备主动断开，随后 3 次快速重连全部秒断（"no close frame received or sent"
  = 对端无握手直接断，典型 WiFi/网络层断连或设备重启）
- 90 秒观察无新连接、无新 hello；残留 1 条 TCP（117.67.194.234:19139）疑为半开
- nginx 层无错误（error.log 只有 00:35 双服务重启时的 connection refused，已恢复）

### 结论
服务器/WS 链路正常，设备 00:55 曾成功连上并完整工作过一次；
"开机连接错误"发生在设备侧——重启瞬间的断连+重连失败（WiFi 未就绪/路由器 DHCP/
信号弱），而非服务器拒绝。设备日志（串口）可最终确认。

---

## 第十五轮（2026-10-08 01:25）：链路模拟器接入真实服务端 ASR（用户投诉"断网也能ASR"）

### 用户投诉核实（属实）
链路模拟器 ASR 用的是浏览器 Web Speech API（Chrome 内置识别），断网也能出文字
——因为走的是浏览器/OS 本地服务，与服务器 ASR 引擎无关。UI 日志打印"ASR: xxx"
造成真实链路的假象，误导用户，已道歉并立即补全真实链路。

### 实现（三端）
- Python：新增 core/api/asr_recognize_handler.py（POST /api/asr/recognize）
  webm/opus → ffmpeg 转 16k WAV → 复用主链路 qwen3_asr_flash.speech_to_text
  （60s 超时兜底；回环 + server.secret 鉴权，与 tts_preview 同模型）
- Java：新增 AsrRecognizeController（POST /models/asrRecognize）
  读 ASR 模型 rawConfig 经 X-Asr-Config 头转发（含非 ASCII 时 Base64 降级）
  首次编译两处错（多余的 RequirePermissionsCustom import、RequiresPermissions
  包路径应为 org.apache.shiro.authz.annotation），修复后编译通过
- 前端：toggleSimListen 重写为 MediaRecorder 录音 → 上传 /models/asrRecognize
  （自动拉智能体详情取 asrModelId；按钮文案改"录音（服务端真实 ASR）"；
  日志显示"ASR（服务端 xxx ms）"；断网/无麦克风/未配 ASR 均有明确报错）

### 验证（真实音频端到端）
合成语音"你好呀，今天天气怎么样？"→ WAV→webm/opus（8565B，模拟浏览器
MediaRecorder 输出）→ POST asrRecognize → 识别结果：
"你好呀，今天天气怎么样？"（578ms）✓ 全链路真实。

注意：真实 ASR 需在 https://sandyun.top:8001/cc/ 下使用（麦克风 getUserMedia
要求安全上下文）。

---

## 第十六轮（2026-10-08 01:45）：前后端 API 契约一致性工程（P0-P2 全量落地）

### 交付物（cc-console/contract/ + scripts/）
1. **契约唯一来源（FR-01）**：contract/openapi.json —— springdoc 从生产 jar 导出，
   141 端点/173 方法，随 git 入库可追溯
2. **CI 校验脚本（FR-13）**：scripts/check_contract.py —— 扫描 App.vue 全部 api() 调用
   与直连 fetch，比对契约（方法+路径，模板参数归一化，query 剥离）；PASS/FAIL 退出码
   可直接接 CI；npm run check:contract；报告落 contract/check-report.json
3. **例外登记（FR-15）**：contract/exceptions.json —— OTA multipart 上传（FormData
   无法走统一封装）已登记原因/替代方案/负责人；ASR 二进制上传已通过给 api() 增加
   contentType+rawBody 能力后**收编为统一封装**，例外从 2 减为 1
4. **统一封装加固（FR-06/07/08）**：api() 新增 401（清 token+提示重登）/403（权限提示）
   /5xx（服务器异常）统一拦截——页面不再各自处理；二进制上传支持
5. **文档（FR-14）与流程（FR-12）**：contract/README.md —— 校验用法、契约重导出命令、
   变更流程（先改契约→校验→前端同步→提交）、baseURL/版本策略说明

### 校验结果（首次运行即抓到真 bug）
- 首跑：70 调用，67 匹配，3 违规：
  ① /device/list 契约中不存在（后端 404！）——设备页"全量列表"从未生效，一直静默
    回退到绑定视角。修正为契约端点 /admin/device/all（实测 200，返回全量分页数据，
    含 board/appVersion/绑定人/最近聊天时间）——验收标准 6"禁止假兜底"的活案例
  ② /admin/dict/data/ 字符串拼接路径 → 改显式分支（可静态校验）
  ③ /memory/facts${qs} 校验器误报 → 修 normalize（模板 query 剥离）
- 终态：**70 匹配 + 1 例外（已登记）+ 0 违规 = PASS ✓**
- 前端 index-BjToZk4I.js 已上线（含设备页全量列表修复 + ASR 收编统一封装）

### 后续接入 CI 建议
git hook / CI 流水线加 `cd cc-console && npm run check:contract`（FAIL 即阻断）。
后端接口变更后重导出契约：curl http://127.0.0.1:8002/xiaozhi/v3/api-docs -o contract/openapi.json

---

## 第十七轮（2026-10-08 14:25）：mem_hybrid 混合记忆引擎上线

### 需求
用户要求"短期记忆 + Holographic 长期记忆 + LLM 总结"三者兼得，且记忆管理模块可选 LLM。

### 实现（三端）
- Python 新引擎 core/providers/memory/mem_hybrid/：
  ① 正则抽取（与 mem_holographic 同规则，零成本）② LLM 滚动总结（复用
  mem_local_short 时空档案 prompt）③ LLM 沉淀（新 prompt：从总结+对话提取
  preference/habit/profile/event 写入 Holographic 库，≤5 条/次，内容 UNIQUE 幂等）
  LLM 缺失时静默退化（只剩正则层）。
- connection._initialize_memory 加 mem_hybrid 分支（可选专用总结 LLM，同
  mem_local_short 机制）；Java ConfigServiceImpl 加 mem_hybrid 的 llm 引用注入
  + db_dir 注入；DB 新增 Memory_mem_hybrid 模型（默认 LLM_DeepSeek，已启用）
- 前端记忆管理页新增「🧠 记忆引擎」配置区：引擎下拉（含 hybrid ⭐推荐 + 说明）+
  总结 LLM 下拉（跟随主LLM/独立选择）+ 应用到智能体（PUT agent + 更新模型 config）
- 排错记录：get_store 实际在 mem_holographic.py 非 store.py；跨类 staticmethod
  调用形态错误 → 改为本地纯函数实现；测试脚本需用 .venv python + DB 真实 key

### E2E 验证（服务器真实 LLM 全链路）
模拟对话（搬家深圳/南山通勤/粤语歌/夜跑/花生过敏）→ save_memory：
- 正则抽取 1 条 + LLM 沉淀 5 条 = 6 条事实入库（花生过敏等隐式信息被 LLM 捕获 ✓）
- 短期总结 922 字符结构化时空档案 ✓
- 检索"过敏"/"住哪"命中 ✓ RESULT: PASS
- 智能体「豆包小何-副本」已切到 Memory_mem_hybrid（设备重连后生效）
- 前端 index-CYE35WOj.js 上线

## 2026-10-08 18:00 设备 WS 连接失败修复（服务器侧）
- 现象: ESP32 待机/按键时弹「无法连接服务 ws://sandyun.top:8001/xiaozhi/v1/」+ TCP receive failed: -1，33 秒即复现；服务器日志见 17:46:38 一秒内设备 3 连 3 断（重连风暴）
- 根因 1: xiaozhi-server core/connection.py 竞态——close() 先把 self.executor 置 None，而 _background_initialize 协程仍在跑，回头 executor.submit() 抛 'NoneType' object has no attribute 'submit'，连接初始化失败被关闭
- 根因 2: close_connection_no_voice_time=120(空闲 180s 踢线) 与圆屏桌宠常驻在线冲突，制造高频断连，反复触发上述竞态
- 修复: connection.py 对 executor 取 snapshot+判空；config.yaml 120→3600
- 生效: 已在服务器打补丁并重启（PID 401933, :8000 LISTEN）；公网 E2E 验证 HANDSHAKE_OK → SERVER_HELLO(device_config)；重启后新日志 0 处『后台初始化失败』
- 镜像同步: code-server-mirror/xiaozhi-server 同步打补丁，防止下次部署回滚

## 2026-10-08 20:10 设备掉线双修复（服务器根因 + 固件兜底）
- 现象: 设备 36 秒即掉线弹『无法连接服务』；服务器日志显示 20:00:14 连接 → 20:03:14 超时关闭（精确 180s）
- 根因: 配置三层覆盖——config.yaml(3600) 被 read_config_from_api 机制覆盖，真实生效的是 MySQL sys_params.close_connection_no_voice_time=120（180s=120+60 二道关闭）
- 修复 1（根治）: UPDATE sys_params SET param_value='3600'（DB 层），重启 python 服务（20:07），公网 E2E 握手+hello 验证通过
- 修复 2（固件兜底，fw_build11）: application.cc/h 新增 StartAutoReconnect/StopAutoReconnect——任何网络错误后静默指数退避重连（2s 起 x1.5 封顶 60s 无限次），连接成功即停；MAIN_EVENT_ERROR 不再弹阻塞 Alert（cancel 图标+警告音），改为气泡轻提示
- 用户需烧录: idf.py -p COM6 flash（fw_build11 产物 0x2b15f0）

## 2026-10-08 23:00 /admincc/ 管理端全按钮接真实 API 完成报告
- 范围: 概览/模板/知识库/用户 4 页全部交互元素对接 manager-api 真实接口
- 基础设施: 全局 Toast 反馈组件 + 全局确认弹窗（删除/封禁等危险操作）+ loading 禁用态
- 实测通过的按钮:
  * 概览: 导出报表(CSV下载+toast)/刷新/模板管理跳转/知识库跳转/查看用户跳转; 统计卡真实数据(用户1/模板7/设备1=my-s3-tft/记忆智能体1)
  * 模板: 新建(POST 实测创建'测试模板-E2E'成功+列表刷新)/编辑(弹窗预填)/预览(完整人设渲染)/删除(确认弹窗+DELETE 实测 8→7)/刷新/搜索过滤
  * 用户: 分页(page=1 契约)/手机号搜索/重置密码/封禁解封/删除; 实测 changeStatus 接口真实生效
  * 知识库: 列表/新建弹窗(RAG模型下拉真实加载 RAGFlow)/文档列表/删除; POST 实测到达服务器(返回业务码 10186=RAGFlow 适配器未配置，前端正确 toast)
- 重大发现与修复:
  * BUG1: sm-crypto 版本差异——0.5.7 的 doEncrypt 与 manager-api SM2 解密不兼容，锁 0.3.14(与 cc-console 一致)后登录恢复正常
  * BUG2: 用户状态语义反转——manager-api Oauth2Realm:100 定义 status=0=锁定/1=正常(与直觉相反)，前端已按真实语义修正; 期间误封 demo 已恢复(status=1)
  * 服务器侧: token 会话在 changeStatus 后吊销属正常安全机制
- 遗留(非前端): RAGFlow 适配器未配置导致知识库创建业务失败(code=10186), 需服务器侧配置 RAG 服务
- 部署: v2_deploy12 (root/admincc/cc 三端点 200)

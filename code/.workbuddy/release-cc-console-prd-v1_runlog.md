# Release Runlog: cc-console 功能补全（PRD v1.0 全量）

日期：2026-10-07 19:50 CST ｜ 操作者：hermes-agent（接手自 PROJECT-HANDOFF.md）
主题：CC 控制台 PRD v1.0 —— R1 MCP 页 + R2 链路模拟器 + R3 去纸老虎 + R4 响应式布局

## 需求范围（对照 PRD §8 验收总表）

| 编号 | 验收点 | 状态 |
|---|---|---|
| R1.1 | MCP 接入点页显示地址+工具列表 | ✅ 上线（只读展示 + 复制 + 空态） |
| R2 | 链路模拟器浏览器播放出声 | ✅ 上线（浏览器 ASR MVP + LLM + TTS 三阶段） |
| R3.1 | 设备可改名/解绑/删除 | ✅ 改名+解绑+绑定（改名 PUT /device/update/{id}；解绑 POST /device/unbind；无设备删除端点——后端设计如此，设备由 MAC 自注册） |
| R3.2 | 聊天会话可删除 | ✅ 上线（新增后端 DELETE /agent/{id}/chat-history/{sessionId}） |
| R3.3 | 记忆事实可编辑 | ✅ 上线（PUT /memory/facts/{id} 已存在，前端补编辑模态） |
| R3.4 | OTA 可上传固件 | ✅ 上线（POST /otaMag/upload multipart + 删除 DELETE /otaMag/{id} + 下载） |
| R3.5 | 字典项可新增 | ✅ 上线（save/update/delete 端点已存在，前端补 CRUD UI） |
| R3.6 | 模板一键创建智能体 | ✅ 上线（复用 POST /agent） |
| R4.1 | 三档视口无横滚 | ✅（900px 以下抽屉侧栏+汉堡；900-1199 两栏；卡片流） |
| R4.3 | 侧栏分组清晰 | ✅（6 组：概览/智能体/内容/音视/系统/调试） |

## 后端改动（code-server-mirror）

### Python（yuhe-server）——R2 LLM 阶段支撑
- **新增** `core/api/llm_preview_handler.py`：POST /api/llm/preview（Bearer server.secret + 回环中间件，同 tts_preview 安全模型；text≤500 字；调 core.utils.llm.create_instance 聚合流式回复，返回 {reply, elapsed_ms}）
- **修改** `core/http_server.py`：注册 handler + /api/llm/ 路径纳入回环+鉴权中间件

### Java（manager-api）
- **新增** `modules/model/controller/LlmPreviewController.java`：GET /yuhe/models/llmPreview?modelId&text&systemPrompt（Shiro 登录态 → 读模型 raw config → 代理转发 Python，凭据不回传）
- **新增** `AgentController.deleteAgentChatSession`：DELETE /agent/{id}/chat-history/{sessionId}（权限校验 + 音频引用清理 + 会话记录删除）
- **新增** `AgentChatHistoryService.deleteBySessionId` + Impl（LambdaQueryWrapper 按 agentId+sessionId 删记录，先清 audioId 引用）

### 前端（cc-console/src/App.vue，单文件扩展）
- 侧栏 6 分组 + 汉堡菜单 + 紧凑模式开关 + 面包屑
- 新页：MCP 接入点（R1）、链路模拟器（R2：Web Speech API 录音→文本可编辑→llmPreview→ttsPreview→<audio> 播放+下载，三阶段状态色 + 链路日志）
- 设备页：改名/绑定/解绑（R3.1）
- 聊天页：智能体选择器 + 会话删除（R3.2）
- 记忆页：编辑模态（内容+分类，R3.3）
- OTA 页：.bin/.apk 上传 + 删除 + 下载（R3.4）
- 字典页：新增/编辑/删除模态（R3.5）
- 模板页：一键创建智能体（R3.6）

## 部署过程（按 PROJECT-HANDOFF §8 速查）
1. Python：sftp_push 两个文件 → 服务器 py_compile OK → restart yuhe-server（45s，FunASR 加载）
2. Java：sftp_push 4 个文件（注意：中途一次目标文件名笔误 AgentChatHistoryServiceImpl.py.java，已删并重传正确名）→ mvn package 23s → 备份旧 jar 至 /root/backup/2026-10-08-doubao-v3/xiaozhi-esp32-api.jar.bak-20261007-ccconsole → cp /opt → restart
3. Web：vite build（1.02s，32 modules）→ tar → sftp → 解包 /var/www/cc-console/ → 200

## 验证（.workbuddy/e2e_cc_verify.py，8/8 PASS）
- Python /api/llm/preview：401 无 token / 400 缺 text（鉴权+校验生效）
- Java llmPreview / chat-history DELETE / device update / ota upload：未登录均 {"code":401}（路由+Shiro 生效；注意 Java 业务错误 HTTP 仍 200，判据看包体）
- Web bundle：index-DLKqhhwi.js 本地=线上
- 数据库/Redis：无 schema 变更，无需清缓存

## 遗留与风险
1. **MCP 写接口**（PRD §7.1）：后端只有 2 个 GET，配置/生成接入点仍走 API 调试页（PRD 允许 R1 只读 MVP）
2. **真实 ASR 端点**（PRD §7.2）：P2，当前浏览器 Web Speech API 规避；Chrome 需 HTTPS 才有麦克风权限（当前 http://sandyun.top:8001 部署下录音按钮在部分浏览器不可用，打字输入不受影响）
3. **设备删除**：后端无 DELETE /device（设备由 MAC 自注册生命周期），解绑已覆盖管理诉求
4. Qwen TTS changelog 登记（202610071100/1200）依赖下次 jar 重启补跑——**本次已重启，Liquibase 已补登**（副作用：顺带解决）
5. 浏览器兼容：链路模拟器 ASR 需 Chrome/Edge；Safari/Firefox 打字输入兜底

## 回滚剧本
- Python：sftp_push 旧版两文件（git 里上一个 commit 版本）→ restart
- Java：cp /root/backup/2026-10-08-doubao-v3/xiaozhi-esp32-api.jar.bak-20261007-ccconsole /opt/xiaozhi/ → restart
- Web：上一版 dist tar 在 .workbuddy/（cc_dist.tar.gz 旧档）→ 重推解包

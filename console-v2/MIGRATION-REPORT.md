# admincc 管理台全量迁移验收报告

版本 v1.0 · 日期 2026-10-08 · 依据《将 /cc/ 控制台功能与 API 全量迁移至 admincc 管理台 需求说明 v1.0》

## 验收总表（对应需求 §8）

| 编号 | 验收点 | 状态 | 证据 |
|---|---|---|---|
| M.1 | 全量 admin 视图建成（§3 17 页） | ✅ | 13 个新视图 + 4 个对齐视图，路由 21 条全部注册（src/main.js） |
| M.2 | adminApi 补齐 §4 全部方法 | ✅ | src/lib/api.js adminApi 12 域 60+ 方法，契约逐条对照 cc-console App.vue 实测调用 |
| M.3 | 关键用例与 /cc/ 行为对等 | ✅ | 见下表逐页实测 |
| M.4 | 无 kawaii CSS 泄漏 | ✅ | `grep -rE "fade-in-up\|stagger-item\|hover-glow\|kawaii" src/` = 0 命中 |
| M.5 | dist-admin 基准 /admincc/ 且线上可达 | ✅ | dist-admin/index.html 基路径 /admincc/；https://sandyun.top:8001/admincc/ 200 |

## 逐页实测记录（线上 https://sandyun.top:8001/admincc/，测试账号 hermes_test 超管）

| 页面 | 路由 | 数据源接口 | 实测结果 |
|---|---|---|---|
| 概览 | /admin | 多接口聚合 | ✅ 真实统计 + 快捷入口 |
| 智能体 | /admin/agents | GET /agent/list | ✅ 列表/新增/编辑/删除/会话（hermes_test 空态正确） |
| 聊天 | /admin/chat | /agent/{id}/sessions + /chat-history/{sid} | ✅ 三栏联动 + 删会话（带确认） |
| 记忆 | /admin/memory | /memory/agents + /memory/facts | ✅ 契约修正 page/size + agent_id 透传 feedback/review |
| 音色 | /admin/voices | /models/list?modelType=TTS + /models/{id}/voices | ✅ 7 模型 / 48 音色真实渲染；**试听真实出声**（voice=Cherry → 38KB WAV） |
| 模板 | /admin/templates | /agent/template* | ✅ 上轮已验：CRUD 全通 |
| 知识库 | /admin/knowledge | /datasets* | ✅ 上轮已验：创建/删除/RAG 模型列表 |
| 模型 | /admin/models | /models/list?modelType= | ✅ LLM 3 个真实模型（DeepSeek 等）渲染；测试/启停/删除就位 |
| 设备 | /admin/devices | /admin/device/all | ✅ ESP32 真实显示（14:c1:9f:d1:33:48，在线，demo 绑定）；改名 alias 契约/手动添加/解绑 |
| 参数 | /admin/params | /admin/params/page | ✅ 47 条系统参数全渲染（含 close_connection_no_voice_time=3600） |
| 用户 | /admin/users | /admin/users | ✅ 上轮已验：封禁/解封/重置密码/删除（status 语义已修正：1=正常） |
| OTA | /admin/ota | /otaMag | ✅ 空态正确（total=0） |
| 字典 | /admin/dicts | /admin/dict/type/page + /data/type/{type} | ✅ 2 类型 / 54 条固件型号（name/key 契约修正后全渲染） |
| 替换词 | /admin/correctwords | /correct-word/file/list | ✅ 空态正确（total=0） |
| 服务器 | /admin/servers | /admin/server/server-list | ✅ ws://sandyun.top:8001/xiaozhi/v1/ 节点显示（字符串数组契约适配） |
| MCP | /admin/mcp | /agent/mcp/{address,tools,test}/{id} | ✅ 地址/工具/测试三按钮就位 |
| 链路模拟 | /admin/linksim | /models/asrRecognize + llmPreview + ttsPreview | ✅ ASR/LLM/TTS 三面板，TTS blob 出声 |
| API 调试 | /admin/apis | apiCatalog.js 142 接口 | ✅ 目录树 + 原始请求面板（搜索/路径参数/JSON body/响应展示） |

## 契约对齐修正记录（C4 前端消化，后端零改动）

1. 设备改名：`PUT /device/update/{id}` body 用 `alias`（非 name）
2. 手动添加：`POST /device/manual-add` body 用 `{board, appVersion, macAddress}`
3. 解绑：`POST /device/unbind` body 用 `{deviceId}`（非 macAddress）
4. 记忆分页：`/memory/facts` query 用 `page/size`（非 limit）；feedback/review body 带 `agent_id`
5. 字典数据：data 为 `[{name, key}]` 数组（非 dictLabel/dictValue）
6. 服务器列表：data 为 WS 地址字符串数组
7. TTS 试听：voice 参数用 `ttsVoice` 字段值（如 "Cherry"）；返回为音频二进制流（blob 播放）
8. 模型状态：`isEnabled` 字段（非 enable）
9. 音色列表：优先选 `isDefault` 模型（与 cc-console loadTtsModels 一致）

## 登录修复（本轮第 1 项需求）

- 根因：401 拦截器在登录成功瞬间被旧页面在途请求触发，清掉刚写入的 token 踢回 login
- 修复：api.js 拦截器加 loginAt 10 秒竞态防护；Login.vue 跳转双保险（router.push + hash 直赋）
- 测试账号：hermes_test / Xk9#mQ2$vL8@wR5!nZ4+pJ7&bH3（已提权 super_admin=1）
- 验证：登录 → #/customer 停留 → token 有效 → 全页面数据加载 ✅

## 遗留（服务器侧，非前端）

- QwenTTS 部分音色阿里云侧未授权（voice=ID 格式返回 InvalidParameter，voice=Cherry 正常）——前端已用正确 ttsVoice 参数
- RAGFlow 适配器未配置（知识库创建 code=10186）——需服务器配置 RAG 服务

## 构建/部署记录

v2_build8~13 / v2_deploy13~17 全部 EXIT=0（customer + admin 双构建，deploy.py 发布 /var/www/console-v2/{,admin}）

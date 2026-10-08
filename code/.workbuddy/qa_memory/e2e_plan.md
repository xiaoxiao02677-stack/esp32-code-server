# 记忆功能 E2E 用户旅程测试方案（部署后 #7 阶段执行）

| 项 | 内容 |
|---|---|
| 版本 | v1.0 |
| 作者 | qa-e2e（QA 组端到端场景专项） |
| 状态 | 已本地预演；**线上未部署新代码，全场景为部署后执行物** |
| 覆盖 | PRD v1 §6：A1（跨会话被记住）、A2（管理页 CRUD 生效）、A6（mem0 降级）、A10（回退安全） |
| 脚本 | `qa_memory/e2e_memory_suite.py`（一体）、`qa_memory/preview_a1_local.py`（本地预演，已跑） |

> A3（搜索/筛选）、A5（mem0 有效 key）、A9（性能）不在本套件范围：A3 由 qa-api 的 API 级用例覆盖，A5 依赖外部 mem0 平台账号，A9 由 qa-api 延迟度量覆盖。

---

## 0. 环境实测情报（2026-10-05，已逐项验证）

| 项 | 实测值 | 对脚本的影响 |
|---|---|---|
| WS 入口 | `ws://sandyun.top:8001/xiaozhi/v1/`（nginx → 127.0.0.1:8000 python app.py） | 设备模拟沿用 verify_tts.py/qa_session.py 协议，无需改动 |
| 管理端 | `http://sandyun.top:8001/xiaozhi/**`（nginx → 127.0.0.1:8002 Java，**路径带 /xiaozhi/ 前缀**） | 脚本 API_BASE 已按此设置 |
| 内部管理 API | `http://127.0.0.1:8003/api/memory/**`（部署后），Bearer server.secret（`2d7b6bde-...`） | A1 兜底直连（可选） |
| demo Agent | `03532a34fcea46639099adb38474a2d9`（汪汪队长），当前引擎 `Memory_mem_local_short`，属主用户 `demo`(2106728446262718466，super_admin=1) | A1 前切引擎，清理时恢复 |
| Memory 模型 | 线上现有 `Memory_mem0ai / mem_local_short / nomem / mem_report_only / powermem`；**`Memory_mem_holographic` 未插入（种子 SQL 202610051800.sql 部署时写入）** | 部署检查第一关 |
| 服务器 sqlite3 | **无 sqlite3 CLI**，但 `/usr/bin/python3` 有 sqlite3 模块 | 库断言走 `python3 -c`，不用 sqlite3 命令 |
| xiaozhi-server 进程 | `systemd` 管理（`systemctl restart xiaozhi-server`）；回退 `pkill -f 'python app.py'` | 引擎切换后必须重启才生效 |
| 登录鉴权 | SM2 加密 + 图形验证码（captcha+密码拼接加密），**无法绕过图形验证码做纯 API 登录** | 已实测替代：MySQL 直插 token（见 §2） |
| 部署现状 | 远程无 `mem_holographic` 代码、`/api/memory` 404 | `--skip-deployed` 下全场景 SKIP（已跑通） |

---

## 1. 总体设计

### 1.1 执行形态

```text
e2e_memory_suite.py --case {A1|A2|A6|A10|all} [--skip-deployed] [--no-cleanup]
```

- 顺序：A1 → A2 → A10 有数据依赖（A2 用 A1 的条目、A10 前置 A1 数据）；A6 独立。
- 每场景产出 verdict（PASS/FAIL/SKIP）+ checks + notes，落 `qa_memory/reports/e2e_memory_<ts>.json`。
- 退出码：0 = 全 PASS/SKIP；1 = 存在 FAIL。
- `--skip-deployed`：部署检查失败 → SKIP（线上未部署时打印 SKIP 而非 FAIL，避免误报）。默认（不带该参数）部署检查失败 → FAIL，用于部署后强约束。
- `--no-cleanup`：保留现场供排查（默认执行清理）。

### 1.2 测试数据隔离（重点：不污染 demo Agent 的真实记忆）

| 层 | 策略 |
|---|---|
| 数据层 | A1 开始前把 demo 引擎由 `mem_local_short` 切为 `mem_holographic`——**两种引擎数据文件物理隔离**（holographic 写 `data/memory/{agent_id}.db` 新文件；mem_local_short 的压缩档案 YAML 不动）。且 holographic 库文件在切换前先 `cp` 备份到 `/tmp/e2e_memory_*.db.bak` |
| 结论：测试条目只落在**全新生成的** holographic 库文件中，demo 真实记忆（mem_local_short YAML 档案）全程零接触 |
| 身份层 | 设备会话模拟使用团队既有的测试设备 `14:c1:9f:d1:33:48`（verify_tts.py 同款），测试来源（device/session）可辨识可清理 |
| A2 编辑删除 | 只作用于 A1 刚产生的条目（fact_id 由 A1 数据库查询获得），编辑后的"张三丰"在用例内即删除，无残留 |
| A6 隔离 | **完全不碰 demo**：MySQL 直插专用 QA 用户 `qa_mem_e2e`(2110000000000000001) + 专用 Agent `21e2e...` + 专用 mem0 配置 `Memory_mem0ai_e2e_no_key`（无 api_key）+ 专用 Device-Id `e2:e2:qa:me:m0:01`，清理时三张表记录一并删除 |
| 引擎恢复 | A1 清理时恢复 `ai_agent.mem_model_id` 原值（`Memory_mem_local_short`）；A10 清理时恢复到 `Memory_mem_holographic`（A1/A2 数据仍在，供后续 A3 与回归）；恢复动作带 `mysql_restored` 防重入 |
| token | 每次运行生成独立 token 行（`sys_user_token`，token=md5(e2e-...seed)，4h 过期），清理时按 token 精确删除，不触碰 demo 用户既有 token |

### 1.3 管理端鉴权替代方案（已实测验证）

登录接口要求 SM2 加密 + 图形验证码，纯 API 无法自动化（A2 需管理 API 调 8002）。方案：**MySQL 直插 token**（经代码走读 + 线上实测）：

- `Oauth2Realm.doGetAuthenticationInfo` 按 `Authorization: Bearer <token>` → `sys_user_token` 表校验（无 Redis 缓存）；
- `sys_user_token` 结构：id/user_id/token/expire_date（12h 过期，logout 置过期）；
- token 值 = `md5(e2e-memory-<case>-token)`（与 TokenGenerator 的 md5(uuid) 同分布）；
- 实测：插 token 行后 `GET /xiaozhi/agent/list` code=0（鉴权链路通）；`GET /xiaozhi/memory/agents` code=404"资源不存在"（**证明鉴权通过、只是路由未部署**——正是部署检查需要的信号）。

### 1.4 部署检查 `check_deployed()`（三关）

1. 远程存在 `/root/xiaozhi-server/main/xiaozhi-server/core/providers/memory/mem_holographic/` 代码；
2. `curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8003/api/memory/agents` == 200；
3. `ai_model_config` 含 `Memory_mem_holographic`（is_enabled=1）。

---

## 2. 场景详情

### 2.1 A1 跨会话被记住（demo Agent → mem_holographic）

| 项 | 内容 |
|---|---|
| 前置 | 部署检查三关通过；demo 当前引擎 `Memory_mem_local_short`（实测） |
| 步骤 | ① MySQL 备份 `mem_model_id` + 切 `Memory_mem_holographic`；② `cp data/memory/{agent_id}.db /tmp/...bak`（不存在则跳过，说明是首测）；③ `systemctl restart xiaozhi-server` 等 8s 探活 `:8000`；④ 会话1（WS，Device-Id=14:c1:9f:d1:33:48）说"我叫张三，我喜欢听粤语歌"；⑤ 会话2（新连接）问"你还记得我吗？我喜欢听什么音乐？"+"我叫什么名字？"；⑥ SSH `python3` sqlite3 查询库条目；⑦ 管理 API `GET /xiaozhi/memory/facts?agent_id=...&keyword=张三` 验证同源可见 |
| 断言 | 会话2 回答含"张三"+"粤语"（整体+逐问句：T1 音乐问句含"粤语"、T2 名字问句含"张三"）；`data/memory/03532a34....db` 出现含"张三"/"粤语"条目（category=profile/preference、trust≈0.5、status=active、device_id/session_id 非空）；管理 API total≥1 |
| 召回缺陷 | ~~本地预演发现整句召回为空~~ **已修复并独立复验**（2026-10-05）：工程师修 `_merge_like_candidates` needles 交错构造（8→10），预演 18/18 PASS、我侧独立复跑确认。E2E 断言已升级：T1/T2 双问句均转正式断言 |
| 清理 | 恢复 `mem_model_id` 原值 + 删除 QA token；holographic 库与备份**保留**（A2/A10/A3 复用，且库文件与 demo 旧引擎档案物理隔离、无污染） |

### 2.2 A2 管理页 CRUD 生效（编辑→对话引用；删除→不引用）

| 项 | 内容 |
|---|---|
| 前置 | A1 已产生"张三"条目（依赖 A1 执行） |
| 步骤 | ① `GET /xiaozhi/memory/facts?agent_id&keyword=张三` 取 fact_id；② `PUT /xiaozhi/memory/facts/{fact_id}` body `{agent_id, content:"…张三丰…"}`；③ 设备会话问"我叫什么名字？"；④ `DELETE /xiaozhi/memory/facts/{fact_id}?agent_id=`；⑤ 新会话再问"我叫什么名字？" |
| 断言 | 编辑后 data.content 含"张三丰"；对话回答含"张三丰"且不再含"张三"；删除后对话回答不含"张三丰"；全程未登服务器 |
| 清理 | 无（条目已删）；token 删除 |

### 2.3 A6 mem0 未配 key 降级（专用 QA Agent，demo 零接触）

| 项 | 内容 |
|---|---|
| 前置 | 部署检查通过（get_status 相关代码随部署上线） |
| 步骤 | ① MySQL 建 QA 用户 `qa_mem_e2e`（幂等）；② 插 `ai_model_config` 行 `Memory_mem0ai_e2e_no_key`（type=mem0ai，**api_key 空**）；③ 建 QA Agent（user_id=QA 用户，mem_model_id=上述行）；④ 模拟设备（Device-Id=e2:e2:qa:me:m0:01）两轮对话；⑤ 查服务端 Mem0ai 日志尾部；⑥ `GET /xiaozhi/memory/agents` 断言 QA Agent VO |
| 断言 | 两轮对话均有回复、无失败话术（"抱歉/无法/稍后"等）；`/memory/agents` 返回 QA Agent：engine=mem0ai 且 available=false（黄徽标语义）；服务端仅告警日志不阻塞（记录为观察项） |
| 清理 | 删 QA Agent、删 mem0 配置行、删 QA 用户、删 token（全部按 id 精确删） |

### 2.4 A10 回退安全（holographic → mem_local_short）

| 项 | 内容 |
|---|---|
| 前置 | demo 当前为 `Memory_mem_holographic`（A1 遗留）且库有条目 |
| 步骤 | ① 记录条目数 N；② MySQL 切回 `Memory_mem_local_short` + 重启；③ 设备对话"你好呀"（压缩档案行为正常）；④ SSH 再查 holographic 库条目数 |
| 断言 | 服务重启存活；对话正常有回复；holographic 库文件仍在且条目数 ≥ N（数据保留不丢失） |
| 清理 | 恢复引擎为 `Memory_mem_holographic`（A1/A2 数据供回归）；token 无（本场景无 token） |

---

## 3. 本地预演报告（A1 语义，已执行）

**执行物**：`qa_memory/preview_a1_local.py`——真实 vendored 引擎（store/retrieval/holographic + provider 边界层）+ 两处打桩（`config_loader.get_project_dir` → 临时目录；`llm=None`，mem_holographic 全链路不用 LLM）。

**结果：18/18 PASS（召回缺陷修复后终态；修复前 16/18，FAIL 2 项即下述召回问题，已由 software-engineer 修复、我侧独立复跑确认）**

| 断言组 | 结果 |
|---|---|
| db 落 `data/memory/{agent_id}.db`（临时目录） | ✓ |
| `save_memory("我叫张三，我喜欢听粤语歌")` 自动抽取落库 | ✓ 1 条（正则首条规则命中，存全文） |
| 条目属性：trust=0.5 / status=active / device_id / session_id / agent_id | ✓ 全部正确记录 |
| `query_memory("我叫什么名字")` 召回含"张三" | ✓ |
| `query_memory("你还记得我吗？我喜欢听什么音乐？")` 召回含"粤语" | ✓（修复前为空——`_merge_like_candidates` needles[:8] 被"你还记得我吗"整段+bigram 独占，多 run 问句后段被挤出；修复：needles 三层交错构造、上限 10） |
| 管理侧：keyword=张三 命中 → 编辑张三丰可召回 → 旧词不再召回 → 删除后不再召回 | ✓（A2 语义全部预演通过） |

**结论**：抽取、落库、溯源、CRUD 同源生效、跨会话召回（含 PRD 原文长问句）链路语义全部正确；E2E 主套件 T1/T2 双问句均已转正式断言。

---

## 4. 交付物清单

| 文件 | 用途 |
|---|---|
| `qa_memory/e2e_plan.md` | 本方案 |
| `qa_memory/e2e_memory_suite.py` | A1/A2/A6/A10 一体脚本（`--case` 选择；`--skip-deployed` 未部署 SKIP；报告落 `qa_memory/reports/`） |
| `qa_memory/preview_a1_local.py` | 本地预演（已跑 16/18 PASS；依赖 `pip install colorama pyyaml certifi gmssl`） |
| `qa_memory/reports/e2e_memory_*.json` | SKIP 模式报告（当前两份，线上未部署） |

## 5. 部署后执行清单

```bash
cd G:/demo/21_xiaozhi/code/.workbuddy/qa_memory
python e2e_memory_suite.py --case all            # 部署后强校验（部署检查不过 = FAIL）
python e2e_memory_suite.py --case A1             # 单场景
python e2e_memory_suite.py --case A1 --no-cleanup  # 保留现场排查
```

注意事项：
- 执行会重启 xiaozhi-server 两次（A1/A10），选低峰时段；重启后探活 `:8000`。
- `--case all` 依赖顺序 A1→A2→A10；A2 单独跑会因无条目 FAIL（属预期，报告会注明）。

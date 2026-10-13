# 模拟通信链路延迟测试与优化总结报告

> 生成：2026-10-13 ｜ 方式：5 agent 协同（链路分析 / 测试器审计 / 远程实测 / 行业基准 / 成文）
> 约束：全程只读，未对项目代码做任何增删改
> 实测环境：sandyun.top 远程服务器（/root/yh/app/xiaozhi-server），原始数据见 `logs/perf_probe_20261013/`

---

## 1. 测试结论速览

### 1.1 端到端首响（TTFA）实测估算

模拟链路：**文字输入（代替 ASR）→ 意图识别 → LLM（流式）→ TTS 合成 → 音频首包下发**

| 阶段 | 实测值（P50） | 说明 |
|---|---|---|
| 意图前置检查 | ≈0（本地逻辑） | function_call 模式，无独立意图 LLM |
| LLM 首 token（TTFT） | **0.58s**（P95 0.84s） | DeepSeek deepseek-flash 流式，5/5 成功，总耗时 P50 1.09s |
| TTS 全句合成（首包前提） | **0.91~1.62s/句** | qwen3-tts-flash 非流式 HTTP；含 1 次 30.98s 瞬态长尾（复测未复现） |
| 队列/opus 编码/首包下发 | <100ms | 本地计算，60ms/帧流控 |
| **端到端 TTFA 估算** | **≈1.5~2.2s** | 各阶段串行相加 |

### 1.2 行业对标（bench-researcher，32 来源）

| 档位 | TTFA | 本项目位置 |
|---|---|---|
| 人类对话 | 200-300ms | — |
| 优秀 | <500ms（500-800ms 宽义优秀） | ❌ 未达 |
| 合格 | 500ms-1s | 接近上限 |
| 不可接受 | >2s | 长尾场景（TTS 30s 瞬态）会落入 |

**核心结论**：本项目延迟主要构成 = LLM 首 token（健康，轻量档模型正常水平）+ **非流式 TTS 整句合成（最大可压缩瓶颈）**。若把 TTS 换成流式首包方案（火山 doubao 双向流式 ~300ms 首包），TTFA 理论可降至 **≈0.6+0.3+0.1 ≈ 1.0s 内**，再叠加连接复用与并行化可逼近 800ms 优秀档。

---

## 2. 链路现状

### 2.1 生效链路（chain-mapper，文件+行号证据）

```
[文字输入] listen{text, state=detect}          （代替 ASR）
  ▼ WebSocket
connection._route_message                      core/connection.py:392
  ▼
handleTextMessage                              core/handle/textHandle.py:17
  ▼ TextMessageProcessor.process_message       textMessageProcessor.py:17
ListenTextMessageHandler.handle                textHandler/listenMessageHandler.py:29
  ├ 唤醒词/直出语本地检查（intentHandler.py:53, helloHandle.py:68-80）
  └ startToChat(conn, text)                    receiveAudioHandle.py:43
     ├ handle_user_intent（串行，当前≈0 开销）   intentHandler.py:20
     └ executor.submit(conn.chat)【线程池 5】    receiveAudioHandle.py:103
        ▼ chat()                               connection.py:1335
        ├ memory.query_memory【串行，nomem 零开销】 :1397-1401
        ├ llm.response_with_functions（流式）    :1448-1455
        │    逐 token → tts_text_queue           :1532-1539
        ▼
tts_text_priority_thread（单线程串行）          tts/base.py:475
  ├ 标点切句（首句遇"，"即切）                  base.py:590-627
  └ to_tts_stream → asyncio.run(text_to_speak) base.py:192
       EdgeTTS/qwen：整句合成完才返回            edge.py:67-71 ★瓶颈
  └ opus 60ms 帧 → tts_audio_queue             base.py:196-203
        ▼
_audio_play_priority_thread                    base.py:518
  └ sendAudioMessage（前 5 包直发，余 60ms/包） sendAudioHandle.py:21,233-261
        ▼
[设备] opus 播放
```

### 2.2 生产 provider（实测运行时 vs 静态配置）

| 组件 | 静态 config.yaml | **运行时实测** | 说明 |
|---|---|---|---|
| LLM | ChatGLMLLM / glm-4-flash | **DeepSeek deepseek-flash（流式）** | 配置经 Java manager-api 按设备/agent 动态下发，以运行时为准 |
| TTS | EdgeTTS（非流式） | **qwen3-tts-flash（非流式）** | EdgeTTS 已全部 403 不可用（见 §3.3） |
| ASR | FunASR 本地 | （本次文字模拟，不涉及） | |
| Memory | nomem | nomem | 记忆查询零开销 |
| Intent | function_call | function_call | 无独立意图 LLM 调用 |

> 裁决说明：chain-mapper 依据静态 config.yaml、live-prober 依据 MySQL `ai_model_config.config_json` 实测运行时——两者不冲突，差异源于"配置按设备动态下发"机制。

---

## 3. 实测数据详情（live-prober，样本量温和：LLM 5 轮 / TTS 4 句）

### 3.1 LLM（DeepSeek deepseek-flash，流式，5/5 成功）
- 首 token：**P50 0.58s / P95 0.84s**（单轮 0.45~0.84s）
- 总耗时：**P50 1.09s / P95 1.24s**（单轮 0.89~1.24s）
- 网络层健康：api.deepseek.com TTFB 115~127ms

### 3.2 TTS（qwen3-tts-flash / Cherry，非流式全句合成+音频下载，4 句样本）
- 正常区间：**0.91~1.62s/句**
- ⚠️ 瞬态长尾：1 次 **30.98s**（复测未复现）；模块无重试逻辑，`tts_timeout` 默认 15s/相位（POST 与下载各计一段，总等待可超 30s）
- 网络层健康：maas.qianwenaiapi.com TTFB 91~173ms

### 3.3 EdgeTTS：全部 403 不可用（功能性问题，非性能）
- 官方测试器与 edge_tts 7.2.6 直连均 403（wss://speech.platform.bing.com），服务器时钟正常，本机 Windows 对照同样 403 → 微软端点侧拒绝（token/DRM 失效或风控）
- 影响：config.yaml 中 EdgeTTS 及其 fallback 链（modules_initialize.py:151-208）实际不可用——这解释了运行时 TTS 为何是 qwen3-tts-flash

### 3.4 流式 vs 非流式对比：未能实测
可用 TTS 仅非流式 Qwen；stream_tts 测试器仅覆盖未配置的 AliyunStreamTTS；EdgeTTS 被 403 阻断。流式收益引用行业数据（§5）。

> 原始输出：`logs/perf_probe_20261013/{llm_probe_raw, qwents_probe_raw, edgetts_official_raw, net_rtt}.txt`、`REPORT.md`

---

## 4. 瓶颈诊断（按占比排序）

| # | 瓶颈 | 占 TTFA 比重 | 代码证据 | 可压缩空间 |
|---|---|---|---|---|
| 1 | **TTS 非流式整句合成** | 0.9~1.6s（最大单项） | edge.py:67-71 全量缓冲；qwen 非流式 HTTP 同理 | →流式首包 300ms，省 0.6~1.3s |
| 2 | TTS 瞬态长尾 | 偶发 +30s | 无重试逻辑；timeout 15s/相位双段 | 显式总超时+重试+降级，消除尾延迟 |
| 3 | 每段合成新建事件循环/无连接复用 | 每段几十~几百 ms | base.py:192/247/282/333 `asyncio.run`；EdgeTTS 每段重建 TLS | 进程级 Session 复用省 100-400ms/轮 |
| 4 | TTS 合成单线程串行 | 段 N+1 等段 N | base.py:496 顺序消费 | 段间预合成，避免播放空窗 |
| 5 | memory 串行阻塞 | 当前 0（nomem） | connection.py:1401 `future.result()` | 启用记忆后需并行化（gather） |
| 6 | 线程池 5 共享 | 多设备并发时排队 | connection.py:133 max_workers=5 | 容量评估/独立池 |
| 7 | 工具调用轮 | 命中工具时 +至 30s 上限 | connection.py:1667-1673 | 工具超时收紧+提示语填充 |
| 8 | 观测缺口 | — | 无 LLM TTFT/分句等待/TTS 请求级/队列等待打点 | 补 4 处打点（§6 第二步） |

**健康项（无需动）**：LLM 已流式且 TTFT 0.58s 属轻量档正常水平；意图为 function_call 无前置 LLM；网络 RTT 正常无跨区问题。

---

## 5. 优化方案清单

### A. 零代码改动（配置/选型，立即可做）

| 方案 | 原理 | 预期收益 | 成本 | 风险 |
|---|---|---|---|---|
| A1 **TTS 换流式供应商**（火山 doubao 双向流式，首包 ~300ms 官方标称；xiaozhi 社区实测平均合成 0.503s 最优） | 边合成边出帧，首句不等全文 | TTFA 1.5-2.2s → **≈1.0s**；对照讯飞 1509ms→火山 798ms | 低（config.yaml:815-879 已预留 huoshan_double_stream 段，dto.py:19-23 已预留 SINGLE/DUAL_STREAM 接口） | 需开通火山账号与计费；中文音色迁移 |
| A2 **TTS 长尾治理**：调小 tts_timeout（5-8s 总量）+ 供应商侧重试 | 消除 30s 级瞬态 | 尾延迟 30s→<8s | 极低（改配置） | 超时过紧增加失败率，需配合 fallback |
| A3 **fallback 链修复**：EdgeTTS 已 403，fallback 换 qwen-tts 或 huoshan（当前 fallback 也指向 EdgeTTS，modules_initialize.py:151-208，等于无兜底） | 恢复降级能力 | 可用性 | 极低 | 无 |
| A4 TTS 供应商区域就近 | 避免跨区 RTT 100-300ms（火山官方 FAQ：延迟>500ms 先查跨区域） | 保障项 | 极低 | 无 |
| A5 思考型模型黑名单 | R1/Kimi thinking TTFT 800ms-3s | 防劣化 | 极低（选型约定） | 无 |

### B. 低成本代码改动（几十行级）

| 方案 | 原理 | 预期收益 | 位置 |
|---|---|---|---|
| B1 **HTTP 连接复用**：进程级共享 aiohttp Session（keepalive_timeout=30, limit_per_host）替代每段 `asyncio.run` | 省 DNS+TCP+TLS 握手（100-300ms/次），实测案例 300ms→20ms | 每轮 2-3 次 API 调用省 100-400ms | tts/base.py:192/247/282/333 |
| B2 **补 4 处打点**：chat 首 token / 首句分句命中 / text_to_speak 前后 / handle_opus 首帧 | 现有"四把尺子"日志无法分解 TTFA | 精确量化后续优化 | connection.py:1457、base.py:590-627/192、base.py:145-147 |
| B3 **段间预合成**：合成段 N 时并行预取段 N+1 文本 | 消除段间播放空窗 | 播放连续性 | base.py:496 顺序消费改造 |
| B4 memory 查询与 LLM 并行（asyncio.gather） | 启用记忆后 query 不再串行阻塞 | 启用记忆后省 100-500ms/轮 | connection.py:1397-1401 |
| B5 首句加速：常用回复预合成缓存 | 0 网络延迟即播 | 感知首响 <300ms（特定场景） | 参考唤醒词回复缓存机制（config.yaml:70） |

### C. 结构性改动（周级工程）

| 方案 | 原理 | 预期收益 | 说明 |
|---|---|---|---|
| C1 **EdgeTTS chunk 直通编码**：edge.py:67-71 改为 chunk 级转发 opus 编码 | 免供应商迁移保住 Edge 音色 | EdgeTTS 路径首包 1.6s→~0.4s；需先解决 403 | 若 A1 已落地则优先级降低 |
| C2 线程池容量/隔离 | chat 与工具上报分池 | 多设备并发 TTFA 稳定 | connection.py:133 |
| C3 全链路模拟测试器（方案 A：进程内半真驱动） | mock conn + `await startToChat(conn, text)`，7 埋点瀑布报表 | 建立回归基线，后续优化可量化 | 复用 load_config/create_instance/MockConn（tester-auditor 已给出完整设计） |

---

## 6. 推荐优化路线图

| 阶段 | 动作 | 预期 TTFA | 工作量 |
|---|---|---|---|
| 现状 | — | **1.5~2.2s**（长尾 30s+） | — |
| **第一步（本周）** | A1 换流式 TTS + A2 长尾超时 + A3 fallback 修复 | **≈1.0s**（尾延迟 <8s） | 纯配置，0 代码 |
| **第二步** | B1 连接复用 + B2 四处打点（建立数据基线） | ≈0.9s | 几十行 |
| **第三步** | B4 memory 并行 + B3 段间预合成 + B5 首句缓存 | **≈0.8s（优秀档）** | 数天 |
| 可选 | C1（若需保 Edge 音色）/ C3（建立回归测试） | — | 周级 |

---

## 7. 附录

### 7.1 现有性能测试器使用说明（tester-auditor 审计结论）

- 目录 `performance_tester/` 下 6 个模块**独立直跑**（入口选择器与 doc 文档在镜像仓库不存在），必须以 xiaozhi-server 为 cwd，依赖 config.yaml + data/.config.yaml
- **可直接复用**：llm tester（首 token+总耗时，打点法 :98-101）、tts tester（MockConn 模式 :49-61 绕开 conn 依赖）、stream_tts（7 家硬编码，注意缺 config 节点会 KeyError）
- **本场景废弃**：asr / stream_asr（ASR 已文字模拟）；vllm（视觉）
- **缺口**：无端到端模拟器——现有工具均为组件孤立基准。全链路模拟器方案 A（推荐）：mock conn 后直接 `await startToChat(conn, text)`，T0 文字入 / T1 意图后 / T2 LLM 首 token / T3 LLM 完 / T4 TTS 首块 / T5 LAST 入播放队列 / T6 文件就绪，tabulate 瀑布报表（句子ID/LLM TTFT/LLM 生成/TTS 首块含队列/TTS 尾部/E2E + avg/p95）
- 远程实测注意：data/.config.yaml 含 manager-api.url 时配置走 Java API 动态下发，官方测试器测不到按设备下发的模型（live-prober 实证），需从 `ai_model_config.config_json` 取运行时配置

### 7.2 行业基准来源（节选，完整 32 条见 bench-researcher 报告）

- 端到端分界：rayvoc.ai/blog/voice-ai-latency-guide；telnyx.com/resources/low-latency-voice-ai
- LLM TTFT：global-apis.com 2026-05 横评；CSDN 引掘金国产模型压测
- TTS 首包：火山官方 volcengine.com/docs/6561/1257543（双向流式 300ms）；Vapi humannessindex（MiniMax 315ms median）
- xiaozhi 社区：GitHub Eivs/xiaozhi-esp32-server FAQ（AliLLM 0.547s + DoubaoTTS 0.503s 最优组合）；GitCode 串行 4s→流式改造案例
- 连接复用：CSDN 300ms→20ms 实测；async-concurrency.com aiohttp keepalive 规范

### 7.3 数据完整性声明

- 实测样本量温和（LLM 5 轮 / TTS 4 句），P95 置信度有限；流式 TTS 收益引自行业数据与供应商标称，未在本环境实测（可用 TTS 仅非流式）
- 全程未修改任何项目代码；探测脚本置于 /tmp 已清理；原始输出已落盘 `logs/perf_probe_20261013/`

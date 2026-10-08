# 模拟测试设计 v1 —— 「模拟普通用户」服务器侧 GATE

- 版本：v1（2026-10-05）
- 作者：高见远（架构师，software-architect）
- 状态：定稿，供任务 #8（QA 执行）与任务 #10（GATE 判定）使用
- 执行人：QA（任务 #8）；执行环境：本机 Python 3.13 + websockets（已验证可用）

## 0. 范围与前提

- 被测链路：模拟设备 → `ws://sandyun.top:8001/xiaozhi/v1/`（nginx 反代→8000 xiaozhi-server）→ LLM=DeepSeek（deepseek-flash）/ TTS=EdgeTTS（zh-CN-XiaoxiaoNeural）
- 注入路径：**文本注入**（`listen detect text`），与 `verify_tts.py` 一致；Device-Id 复用真机 `14:c1:9f:d1:33:48`
- ASR=FunASR 本轮不覆盖（见 §4 边界说明），不阻塞 GATE（主理人既定口径）
- 判据校准基线（历史实测）：2026-10-04/05 两次全链路成功，短回复 **134~211 帧 / 21~35KB**，tts stop 正常收尾
- 执行约束：顺序单并发，用例间隔 5s（避免 LLM 限流）；**测试窗口内真机须空闲**——同 Device-Id 新连接会顶掉旧连接（单设备单连接策略），遇顶号/被顶记录为观察项，不判 FAIL
- 开机问候：服务器连接后可能主动推送问候 TTS（基线现象）。脚本须先排空问候（≤15s，不判分）再开始用例，问候帧单独记账（P1-8）

## 1. 横切判分规则（适用于所有用例）

### 1.1 失败话术检测（一票否决，最高优先级）

历史根因（10-04）：LLM key 失效 → 所有回复退化为兜底话术"主人，小智现在有点忙"。故每个对话轮拼接全部 `tts sentence_start` 文本，命中以下任一关键词 → **该用例直接 FAIL**：

```
["有点忙", "抱歉", "稍后", "请稍候", "出了点问题", "失败"]
```

本轮所有输入均不会正常触发上述词汇；若出现语义确需道歉词的极端回复，允许人工复核豁免（须留证据）。

### 1.2 指标定义与预算

| 指标 | 定义 | P0 硬线（超即 FAIL） | 期望值（超仅记 SLOW） |
|---|---|---|---|
| WS 连接耗时 | connect() 完成 | ≤5s | ≤2s |
| TTFB_text | detect 发出 → 首个 `sentence_start` | ≤8s | ≤4s |
| TTFB_audio | detect 发出 → 首个音频二进制帧 | ≤10s | ≤6s |
| 短轮总耗时 | detect → `tts stop` | ≤30s | ≤15s |
| 长轮总耗时 | detect → `tts stop` | ≤120s | ≤60s |
| 打断收敛 | 打断信号发出 → 最后一帧音频 | ≤3s | ≤1s |

### 1.3 协议完整性（每个对话轮必须满足）

- 收到 ≥1 × `tts sentence_start`（含文本）+ 音频二进制帧 + `tts stop`
- 无 `ConnectionClosed` 异常、无服务器错误消息
- `stt` / `llm`(emotion) / `mcp` 等消息仅记录不计分

## 2. 测试矩阵

| # | 级别 | 场景 | 核心判据（量化） |
|---|---|---|---|
| P0-1 | P0 | 短问候 | tts stop ✓、≥1 句、≥40 帧、TTFB_audio≤10s、整轮≤30s |
| P0-2 | P0 | 多轮上下文×3（会话记忆） | T2 含"高见远"、T3 含"西瓜"、每轮协议完整 |
| P0-3 | P0 | 长文本回复 >100 字 | 拼接≥100 字、≥2 句、≥150 帧、整轮≤120s |
| P0-4 | P0 | 打断（首帧后发 listen stop） | 无异常；打断收敛或记录"不打断"；同连接恢复正常 |
| P0-5 | P0 | 连续 3 次会话稳定性 | 3/3 连接+整轮全绿、0 异常断开 |
| P1-6 | P1 | 服务器日志交叉验证 | 测试窗口内 app.log 无 ERROR/Traceback |
| P1-7 | P1 | 打断变体（listen start，真实固件语义） | 音频≤3s 停 + 恢复正常 |
| P1-8 | P1 | 开机问候行为观察 | 记录有无/延迟/帧数，不计分 |

失败话术检测（§1.1）横切作用于全部用例。

### P0-1 短问候

- 输入：`你好`
- 步骤：connect → 排空开机问候（≤15s）→ ask("你好") → 收至 tts stop
- 通过判据（全部满足）：
  1. 收到 `tts stop`，整轮 ≤30s
  2. `sentence_start` ≥1
  3. 音频帧 ≥40（≈2.4s 真实语音；基线 134~211 帧，40 仅为"真实合成"下限）
  4. TTFB_audio ≤10s
  5. 无失败话术

### P0-2 多轮上下文（同连接 3 轮，验证会话记忆）

同连接、同 session_id 连续 3 轮：

| 轮 | 输入 | 内容断言 |
|---|---|---|
| T1 | `我叫高见远，我最喜欢的水果是西瓜。` | 协议完整 + 无失败话术 |
| T2 | `我叫什么名字？` | 回复文本含 **"高见远"** |
| T3 | `我最喜欢的水果是什么？` | 回复文本含 **"西瓜"** |

- 通过判据：3 轮全部完成；T2/T3 内容断言命中；每轮 sentence≥1、帧≥20、TTFB_audio≤10s、整轮≤30s；无失败话术
- 说明：会话记忆应为服务器连接级（ConnectionHandler 持有上下文）。若 T2/T3 未命中 → 记忆链路缺陷（FAIL），不预设豁免

### P0-3 长文本回复

- 输入：`请讲一个关于小机器人第一次看海的小故事，至少讲100个字。`
- 通过判据：
  1. 拼接全部 sentence 文本，去标点后 **≥100 字**
  2. `sentence_start` ≥2（验证逐句流式下发，非整段等待）
  3. 音频帧 ≥150（≈9s）
  4. 整轮 ≤120s
  5. 无失败话术

### P0-4 打断（收到首帧后主动发 listen stop）

- 输入：主查询 `给我讲一个长长的睡前故事，越长越好。`；恢复查询 `你好，你还在吗？`
- 步骤：ask 主查询 → **收到首个音频帧后立即发 `listen stop`** → 继续接收 ≤5s → 同连接 ask 恢复查询
- 通过判据：
  1. 无协议错误、无连接异常关闭
  2. 打断收敛：stop 发出后 ≤3s 或 ≤30 帧内音频停止 → 记"打断生效"；若音频持续到自然结束 → 记"listen stop 不打断"**观察项（不判 FAIL）**——标准协议语义中打断通常由 `listen start` 触发，由 P1-7 确认
  3. 恢复查询完整通过（证明服务器状态机未卡死）
  4. 无失败话术

### P0-5 连续 3 次会话稳定性

- 步骤：3 次独立 connect（顺序执行、间隔 5s、session_id 分别 verify-s1/s2/s3），每次完整跑 P0-1 流程
- 通过判据：
  1. 3/3 连接成功（各 ≤5s）
  2. 3/3 整轮满足 P0-1 全部判据
  3. 0 次异常断开；无失败话术

### P1-6 服务器日志交叉验证（加分）

- 方法：记录套件起止时间戳，经 `ssh_run.py` 在窗口内 grep app.log `ERROR|Traceback|Exception`，计数须为 0
- 降级：SSH 不可达 → SKIP（不阻塞 GATE）；日志路径与过滤规则与运维任务 #7 对齐

### P1-7 打断变体：listen start（加分）

- 同 P0-4，但打断信号改为 `listen start`（真实固件行为：用户再开口/VAD 触发）
- 判据：音频 ≤3s 停止 + 恢复查询正常 + 无异常
- 若 P0-4 显示 stop 不打断而本例生效 → 确认打断语义归属 `listen start`，建议 v2 将本例升为 P0

### P1-8 开机问候行为观察（加分，不计分）

- 记录 connect 后服务器是否主动推送问候 TTS（有无 / 首帧延迟 / 帧数 / 文本），作为行为基线归档

## 3. 判分脚本设计

**决策：新写 `sim_user_suite.py`，`verify_tts.py` 保留不动。**

理由：现脚本为单轮硬编码流程，无法表达多轮编排、打断时序、多连接稳定性与判分报告；在已验证的冒烟工具上做手术会引入回归风险。两脚本并存：`verify_tts.py` 继续做单点快验（冒烟），`sim_user_suite.py` 承担完整矩阵（GATE 证据生产）。公共消息构造代码量小，v1 允许适度重复，v2 再抽公共模块。

### 3.1 函数级设计

```
sim_user_suite.py（仅依赖 websockets + stdlib，~400 行）
├─ 常量区
│    WS_URL / DEVICE_ID / BUDGETS(§1.2 表) / FAILURE_PHRASES / CASE_TEXTS
├─ @dataclass TurnResult          # 单轮对话全部观测
│    sent_at / first_text_at / first_audio_at / tts_stop_at
│    audio_frames / audio_bytes / sentences[{text, at}]
│    all_text / abnormal_close / others[]     # stt/llm/mcp 仅记录
├─ @dataclass CaseResult          # id / priority / verdict / metrics / notes
├─ class SimDevice                # 一条 WS 连接的设备模拟器
│    async connect()              # 握手 + hello + 排空开机问候(≤15s 不判分)
│    async ask(text) -> TurnResult       # listen start/detect/stop + 收集至 tts stop
│    async interrupt(text, signal) -> InterruptResult
│         # 发查询→等首帧→发 listen {stop|start}→继续收 5s，记录停帧时刻
│    async close()                # goodbye(可选) + 正常关闭
│    _drain_greeting() / _recv_until(deadline, cond)   # 内部工具
├─ 判分纯函数（可单测，不碰网络）
│    check_failure_phrases(all_text) -> str | None
│    count_content_chars(text) -> int          # 去标点计字数
│    judge_short(tr) / judge_turn(tr, must_contain)
│    judge_long(tr) / judge_interrupt(ir) / judge_stability(list[CaseResult])
├─ check_server_log(t0, t1) -> dict           # subprocess 调 ssh_run.py；异常→SKIP
├─ write_reports(results) -> (json_path, md_path)
└─ main()          # argparse: --only P0|all, --out-dir；顺序执行、间隔 5s
```

### 3.2 关键实现约定

- 计时用 `time.monotonic()`（防墙钟跳变）；报告同时落墙钟时间戳，供与 app.log 对时
- 每轮帧计数在 detect 发出后清零；开机问候帧单独记账（P1-8 数据源）
- "音频停止"判定 = 连续 3s 无新帧 **或** 收到 `tts stop`
- 收到 tts stop 后仍排空 ≤2s 尾部消息再返回，避免漏记
- 全部原始消息落盘 `reports/raw_<case>.ndjson`（GATE 证据链）
- 退出码：0 = P0 全绿，1 = 存在 P0 FAIL（对 QA/CI 友好）

### 3.3 报告产出（任务 #10 GATE 证据）

- 路径：`.workbuddy/reports/sim_user_v1_<时间戳>.json` + 同名 `.md`（人读摘要表）
- JSON 概要：

```json
{
  "suite": "sim-user-v1", "device_id": "14:c1:9f:d1:33:48", "started": "…",
  "cases": [
    {"id": "P0-1", "priority": "P0", "verdict": "PASS",
     "metrics": {"ttfb_text_ms": 0, "ttfb_audio_ms": 0, "total_ms": 0,
                  "audio_frames": 0, "audio_bytes": 0, "sentences": 0,
                  "content_chars": 0},
     "notes": ["SLOW: ttfb_audio 7.2s"]}
  ],
  "gate": {"p0_pass": true, "p0": "5/5", "p1": {"P1-6": "PASS", "P1-7": "PASS", "P1-8": "observed"}}
}
```

## 4. 边界说明（不纳入本轮 GATE）

| 项 | 归属 | 说明 |
|---|---|---|
| 喇叭出声（MAX98357A 播放/音量/杂音） | 固件实测 | 用户烧录后人工听测；模拟侧只能验证到"服务器下发音频帧" |
| 麦克风链路（INMP441→Opus 编码→上行） | 固件实测 | 本矩阵用文本注入绕过该链路 |
| 真实 ASR（语音→FunASR 识别） | 服务器组任务 #5 | 服务器侧另行验证，不阻塞本 GATE |
| 唤醒词"你好小智"（WN9 AFE） | 固件实测 | — |
| VAD 自动打断时序（设备端 listen auto） | 固件实测 | 模拟侧仅覆盖服务器对 listen stop/start 的响应（P0-4/P1-7） |
| OTA 升级（8002 NOT_ACTIVATED_FIRMWARE 已知） | 不在本轮 | 与对话链路无关 |
| 断线重连/心跳保活 | 固件实测 + 任务 #6 | 网关链路由服务器组覆盖 |

## 5. GATE 判定规则

- **本维度绿**：P0-1 ~ P0-5 全部 PASS（5/5）
- 任一 P0 FAIL → 本维度红，附 JSON 报告定位
- P1 用例与 SLOW 标注仅记录归档，不阻塞
- 衔接：任务 #8（QA）按本设计执行 `sim_user_suite.py` → 报告直接供任务 #10（主理人 GATE 判定）

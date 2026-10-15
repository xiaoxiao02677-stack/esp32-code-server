# xiaozhi-server 性能实测报告（live-prober，2026-10-13）

## 0. 环境与方法
- 服务器：root@sandyun.top:22223（Ubuntu 24.04，免密密钥登录；任务书中 22/60022 端口不适用，实际端口 22223）
- 项目：`/root/yh/app/xiaozhi-server`，Python venv 为 `/root/yh/app/xiaozhi-server/.venv`
- 方法：复用项目自身模块工厂（`core.utils.llm.create_instance` / `core.utils.tts.create_instance`），临时探测脚本只放 `/tmp`，测完已删除；**项目代码零修改**。官方 `performance_tester_llm/tts.py` 直接运行（需 `PYTHONPATH=/root/yh/app/xiaozhi-server`）。
- 测试对象（生产快照 DB 中的默认模型）：
  - LLM：`LLM_DeepSeek` → deepseek-flash @ https://api.deepseek.com（type=openai，流式 response()）
  - TTS：`TTS_QwenTTS_Flash` → qwen3-tts-flash，音色 Cherry @ https://maas.qianwenaiapi.com（非流式 HTTP：POST 合成 + GET 下载音频）
  - EdgeTTS：zh-CN-XiaoxiaoNeural（配置残留项，实测 403，见下）
- 采样规模：LLM 5 句；Qwen TTS 两次运行各 2 句（另各 1 次 warmup）；EdgeTTS 3 次重试。均属温和采样（≤10 轮）。

## A. 实测数据

### A1. LLM 阶段（DeepSeek deepseek-flash，流式，含系统提示词 5 句样本）
| # | 首 token (s) | 总耗时 (s) | chunks | 输出字符数 |
|---|-------------|-----------|--------|-----------|
| 1 | 0.84 | 1.14 | 36 | 61 |
| 2 | 0.45 | 0.89 | 41 | 73 |
| 3 | 0.58 | 1.24 | 81 | 142 |
| 4 | 0.48 | 0.92 | 47 | 84 |
| 5 | 0.64 | 1.09 | 57 | 92 |
| **统计** | **P50=0.58 / P95=0.84** | **P50=1.09 / P95=1.24** | 成功 5/5 | — |

### A2. TTS 阶段（qwen3-tts-flash / Cherry，非流式全句合成+下载）
| 运行 | 样本 | 总耗时 (s) | 音频大小 (bytes) |
|------|------|-----------|-----------------|
| run1 warmup | 连接测试 | 0.67 | ok |
| run1 | 句1「你好，这是一段性能测试语音。」 | **30.98 ⚠️ 异常单例** | 126,764 |
| run1 | 句2「今天天气真不错…」 | 1.62 | 299,564 |
| run2 warmup | 连接测试 | 0.72 | ok |
| run2 | 句1 | 0.91 | 134,444 |
| run2 | 句2 | 1.56 | 234,284 |

- 正常区间 0.9~1.6 s/句；run1 句1 的 30.98s 为单次瞬态（复测未复现）。模块无重试逻辑；`tts_timeout` 默认 15s（per-socket 相位超时），30.98s ≈ POST+下载两段均接近各自超时上限所致，推测上游偶发冷启动/限流。

### A3. EdgeTTS —— 不可用（403）
- 官方测试器：`EdgeTTS 测试失败: 403, Invalid response status (wss://speech.platform.bing.com/...)` → 「网络错误 0/3」
- 直接调用 `edge_tts`（7.2.6）重试 3 次：全部 403 WSServerHandshakeError（约 1.4~1.7s 内失败）
- 服务器时钟检查：`System clock synchronized: yes`，UTC/CST 均正确（排除 Sec-MS-GEC 时间戳偏移）
- **对照实验：本机 Windows 直连同一端点同样 403** → 判定为微软端点侧拒绝（客户端 token/DRM 过期或风控），与服务器环境无关
- 该断点影响：所有走 Edge 音色的智能体当前无法播报（需换官方音色 provider 或升级/修补 edge-tts）

### A4. 流式 vs 非流式对比
- **不可测**：当前可用的 TTS 只有非流式（Qwen HTTP 全句合成后下载）；`performance_tester_stream_tts.py` 仅支持 AliyunStreamTTS（未配置）；EdgeTTS 走流式协议但被 403 阻断。→ 无有效流式样本，无法对比。

### A5. 网络 RTT（服务器 → 上游，curl 直连 3 次）
| 上游 | tcp connect | tls 握手 | TTFB | total |
|------|------------|---------|------|-------|
| api.deepseek.com | 22~33ms | 58~72ms | 115~127ms | 115~127ms |
| maas.qianwenaiapi.com | 27~102ms | 63~146ms | 91~173ms | 91~173ms |
| speech.platform.bing.com | 58~147ms | 179~272ms | 236~331ms | 236~331ms |

## B. 数据解读
1. **LLM 阶段健康**：首 token P50 0.58s、P95 0.84s；总耗时 P50 1.09s。与 DeepSeek 官方典型首 token 延迟（约 0.4~1.0s）一致，无异常。首 token 与总耗时差 ~0.5s 属正常流式输出节奏。
2. **TTS 阶段基本正常但有瞬态风险**：稳定值 ~0.9~1.6s/句（含完整音频下载），与千问 TTS-Flash 官方量级相符；但出现一次 30.98s 瞬态（约占样本 1/4），叠加模块无重试、超时语义偏宽（15s/socket 相位，总等待可达 30s+）→ 建议对 TTS 加显式总超时（如 5~8s）+ 重试/降级。
3. **瓶颈定位**：全链路（ASR→LLM→TTS）中，LLM 首 token ~0.6s、TTS 全句合成 ~1~1.5s。对非流式 TTS 而言，**等全句合成完才能吐出首音频包**，设备端感知延迟 ≈ LLM 首 token + TTS 全句耗时，TTS 是最大可压缩项（换支持流式首包的 provider 收益最大）。
4. **网络侧无问题**：三条上游 RTT/TLS 均正常（国内直连几十~百余 ms），无网络层异常；异常只出现在应用层（EdgeTTS 403、Qwen 瞬态）。
5. **EdgeTTS 403 是功能性阻断**（非性能问题）：需产品/配置层面处理（换 provider 或修复 edge-tts）。

## C. 运行中遇到的环境问题与解决
1. 任务书给 22/60022 端口 + 密码认证，实际为 22223 端口 + 密钥免密（见 MEMORY.md）；直接使用 22223 成功。
2. 服务器 `doc/` 下无 performance_testerer.md；在本仓库「网页后台」镜像中找到文档，按其要求配置已在 `data/.config.yaml`。
3. `performance_tester.py` 为交互式（input()），SSH 非交互跑不了 → 直接运行子模块脚本；子模块直接跑报 `ModuleNotFoundError: core` → 需 `PYTHONPATH=/root/yh/app/xiaozhi-server`。
4. `data/.config.yaml` 含 manager-api.url → 配置实际从 Java API（server-base）拉取，而 **LLM 与 QwenTTS 不在 server-base 返回中**（按设备在 /config/agent-models 下发）→ 官方 LLM 测试器报「没有可用的测试结果」。解决：从 MySQL `ai_model_config.config_json` 读取真实配置，经环境变量注入临时探测脚本（密钥不出服务器、日志脱敏），复现与线上一致的调用路径。
5. EdgeTTS 403 排查：时钟正常 + 本地对照同样 403 → 定位为上游端点拒绝，非环境问题（详见 A3）。
6. Qwen TTS 30.98s 单例：复测 2 句恢复正常，判定瞬态；已记录。
7. 收尾：`/tmp` 临时脚本已删除；未修改任何项目文件；未重启任何服务。

## 附件（本目录）
- `perf_probe_llm.py` / `perf_probe_qwents.py`：可复用探测脚本（本地留档）
- `llm_probe_raw.txt`：LLM 原始输出（5/5 成功 + SUMMARY）
- `qwents_probe_raw.txt`：Qwen TTS 两次运行原始输出
- `edgetts_official_raw.txt`：EdgeTTS 官方测试器原始输出（403 证据）
- `net_rtt.txt`：三条上游 RTT 原始数据

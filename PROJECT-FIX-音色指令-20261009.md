# 音色语气指令不生效 —— 根因定位与修复

> 日期：2026-10-09 ｜ 排查方式：10 个 agent 并行 + 火山官方文档交叉验证  
> 代码树：`G:/demo/21_xiaozhi/code-server-mirror/`（xiaozhi-server / manager-api / manager-web）

---

## 一、根因（唯一且确定）

**`req_params["voice_instruction"]` 不是火山引擎的 API 字段。** 它是本项目自己臆造的字段名。

火山「豆包语音合成模型 2.0」单向流式接口 `/api/v3/tts/unidirectional` 的 `req_params` 合法字段只有：  
`text` / `model` / `speaker` / `ssml` / `audio_params` / `additions` / `mix_speaker`。

语气/情感指令的**唯一**官方通道是：

```
req_params["additions"] = json.dumps({"context_texts": ["指令文本"]}, ensure_ascii=False)
```

现网把指令写进 `req_params["voice_instruction"]`，服务端对未知字段**静默忽略** —— 请求照常返回 200、音频照常回传，只有指令零效果。这完美吻合「填了不生效」的现象。

官方依据（火山引擎）：

- <https://www.volcengine.com/docs/6561/1329505> —— `context_texts` 权威定义：「语音指令…**当前字符串列表只第一个值有效**」「该字段文本不参与计费」
- <https://www.volcengine.com/docs/6561/2528925> —— `additions` 为 **string**，须传入 JSON 序列化后的字符串
- <https://www.volcengine.com/docs/6561/1871062> —— 语音指令示例库（含「用颤抖沙哑、带着崩溃与绝望的哭腔…」）
- <https://www.volcengine.com/docs/6561/2298705> —— 「什么是 context_texts」

补充纠正一个常见误解：`emotion` / `emotion_scale` 属于 **1.0 系列**且挂在 `audio_params` 下，**2.0 不适用**；`enable_emotion` 在 V3 接口中根本不存在。

---

## 二、已改动清单

| # | 文件                                                                   | 改动                                                                                                                                                                                 | 性质       |
| - | -------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------- |
| 1 | `xiaozhi-server/core/providers/tts/doubao_v3.py:100-116`             | `_build_payload` 由 `req_params["voice_instruction"]` 改为 `req_params["additions"] = json.dumps({"context_texts": [指令]}, ensure_ascii=False)`                                        | **根因修复** |
| 2 | `xiaozhi-server/core/providers/tts/huoshan_double_stream.py:182-189` | 新增读 `voice_instruction`，仅当 `resource_type`（`resource_id == "seed-tts-2.0"`）为真时注入 `self.additions["context_texts"]`；1.0 资源（`volc.service_type.10029`）用 `resource_type` 门控排除，避免传非法字段 | 同源修复     |
| 3 | `xiaozhi-server/tests/core/providers/tts/test_doubao_v3.py:118-146`  | 断言契约同步为官方形态（`additions` 是 str、`context_texts` 是数组、不得再出现 `voice_instruction`）；`test_no_voice_instruction_field_when_unset` 改名 `test_no_additions_field_when_unset`                  | 测试契约     |
| 4 | `manager-api/src/main/resources/db/changelog/202610090130.sql`（新建）   | `ai_tts_voice` 补 `dynamic_instruction` TINYINT(1) 与 `instruction_llm_id` VARCHAR(32) 两列                                                                                            | P0 止血    |
| 5 | `.../db/changelog/db.changelog-master.yaml:840-846`                  | 注册 `202610090130` changeSet                                                                                                                                                        | 配套       |
| 6 | `xiaozhi-server/core/providers/tts/base.py:51,310-318`               | 新增通用动态指令通道 `self._dynamic_instruction` + `set_dynamic_instruction()`，所有 provider 共享，默认 `None`（=回落固定指令）                                                                            | 基础设施     |
| 7 | `xiaozhi-server/core/providers/tts/doubao_v3.py:110-116`             | `_build_payload` 改为 `self._dynamic_instruction or self.voice_instruction`；复刻音色（`resource_id` 以 `seed-icl` 开头）自动补 `req_params.model = "seed-tts-2.0-expressive"`                    | 消费方      |
| 8 | `xiaozhi-server/core/providers/tts/huoshan_double_stream.py:687-708` | `get_payload_bytes` 每次请求浅拷贝 `self.additions` 后注入 `context_texts`（原实现写在 `__init__` 里是错的：`self.additions` 是模板，且资源门控必须在发包时判定）；1.0 资源仍由 `resource_type` 排除                        | 消费方      |
| 9 | `xiaozhi-server/core/connection.py:1122-1223`                        | 新增 4 个方法：`_tts_config()` / `_recent_chat_text()` / `_generate_voice_instruction()` / `_refresh_dynamic_voice_instruction()`                                                        | **生成方**   |
| 10 | `xiaozhi-server/core/connection.py:1296-1297`                        | `chat()` 内 `depth == 0` 且 `memory_str` 刚取到之后调用一次刷新                                                                                                                          | 挂载点      |
| 11 | `xiaozhi-server/tests/core/providers/tts/test_doubao_v3.py:150-195`  | 新增 4 个用例：动态覆盖固定 / 动态置空回落 / 复刻补 expressive / 预置不带 model                                                                                                                 | 测试        |

---

## 三、为什么还要动数据库（第 4、5 项）

`TimbreEntity.java:48,51` 声明了 `dynamicInstruction` / `instructionLlmId`，但 `ai_tts_voice` 表**从未建过这两列**（`202610070300.sql` 只加了 `voice_instruction`）。MyBatis-Plus 的 `selectById` / `selectList` 按实体字段拼 SELECT，会抛：

```
SQLSyntaxErrorException: Unknown column 'dynamic_instruction' in 'field list'
```

异常点在 `ConfigServiceImpl.java:158` `timbreService.get(agent.getTtsVoiceId())`，**同一次查询里的 `voice_instruction` 连带取不到** —— 即使 provider 改对了，指令依然下不来。所以这两列必须补。

> 部署注意：MySQL 无 `ADD COLUMN IF NOT EXISTS`。若目标库已手工建过这两列，部署前请删除该 SQL 文件或注释掉对应行，否则 Liquibase 会报 Duplicate column。

---

## 四、动态语气指令的完整链路（第 6-11 项）

这是残留建议第 5 条的落地：Java 早就在下发 `dynamic_instruction` / `instruction_llm_id`，但 Python 侧无人读取，勾选「动态更新」不产生任何效果。

```
Java ConfigServiceImpl:559-563
   ↓ 写入 config["TTS"][模型id] = {dynamic_instruction, instruction_llm_id, voice_instruction, ...}
Python modules_initialize:153  config["TTS"][select_tts_module].copy() → TTSProvider(config)
   ↓
connection.chat(depth==0)  [connection.py:1296]
   ↓ 此时 memory_str（长期记忆）刚取到，零额外 I/O
_refresh_dynamic_voice_instruction(memory_str)
   ├─ 门控：_tts_config().get("dynamic_instruction") 为假 → tts.set_dynamic_instruction(None)
   │        （清空上一轮残留，回落到固定指令）
   └─ 开启：拼 [短期聊天记录] + [长期记忆] → _generate_voice_instruction()
         ├─ 取 LLM：instruction_llm_id → config["LLM"][llm_id] → llm_utils.create_instance()
         │          取不到则回落到智能体主 LLM self.llm
         ├─ 调用 response_no_stream(system, user)（同步，已封装）
         └─ 清洗 + 防御性截断 [:120]
   ↓
tts.set_dynamic_instruction(指令)   [base.py:310]
   ↓
provider 发包时 instruction = self._dynamic_instruction or self.voice_instruction
   ↓
req_params["additions"] = json.dumps({"context_texts": [指令]}, ensure_ascii=False)
```

关键设计取舍：

| 决策                            | 理由                                                                                          |
| ----------------------------- | ------------------------------------------------------------------------------------------- |
| 挂在 `depth == 0`               | `chat(None, depth+1)` 是工具结果递归，不该重复生成；每轮只调一次 LLM                                                  |
| 位置在 `memory_str` 之后、LLM 流式之前 | 长期记忆已就绪可复用，且早于本轮首句 TTS 合成，第一句就能带上新语气                                                           |
| 全部异常 → `set(None)` 回落         | 动态指令是增强项，LLM 超时/配置缺失都不得拖垮本轮对话                                                                  |
| `_recent_chat_text` 过滤三类消息   | 剔除 `system`（人设）、`tool`（工具噪声）、`is_temporary`（few-shot 示例），只留真实 `user`/`assistant` 最近 8 条        |
| 截断 120 字                      | 火山未规定 `context_texts` 长度上限；这只是防御模型跑飞，同时 system prompt 已要求 ≤40 字                               |
| 复刻音色补 `model`                 | 官方要求 `resource_id=seed-icl-2.0` + `model=seed-tts-2.0-expressive` 配对，`seed-tts-2.0-standard` 不支持 |

---

## 五、验证

`conftest.py:92-116` 会因现网全模块部署（`data/.config.yaml` 配了 `manager-api`）拒绝跑 pytest。两种验证都做了，**未改现网配置**：

### 5.1 独立脚本 mock `requests.post`

```
1) 有指令时 req_params keys: ['additions', 'audio_params', 'speaker', 'text']
   additions 解析结果: {'context_texts': ['用哭腔说话，声音哽咽，带着抽泣']}
   [PASS] 指令已走 additions.context_texts[0]，且无非法字段
2) [PASS] 无指令时不带 additions
3) audio_params: {'format': 'mp3', 'sample_rate': 24000, 'speech_rate': 10, 'loudness_rate': -5}
   [PASS] speaker / audio_params / 分片拼接均正常，audio = b'AAABBB'
```

### 5.2 全链路 11 项校验（provider 契约 + connection 生成/降级）

```
1)  [PASS] 固定指令 → 固定指令：温柔女声
2)  [PASS] 动态指令覆盖 → 用轻快俏皮的语气说
3)  [PASS] 动态置空回落 → 固定指令：温柔女声
4)  [PASS] 复刻音色 model = seed-tts-2.0-expressive
5)  [PASS] 预置音色无 model 字段
6)  [PASS] 无指令时不带 additions
7)  [PASS] connection 新增 4 个方法均存在
8)  [PASS] 短期上下文提取已过滤 system / tool / few-shot
9)  [PASS] 未开启动态 → set(None)
10) [PASS] LLM 抛异常 → 降级置 None，未影响主链路
11) [PASS] 动态生成并注入 → 用温柔安慰的语气说
ALL PASS
```

### 5.3 pytest 正式跑通（含历史用例回归）

现网 `data/.config.yaml` 会让 conftest fail-fast，绕开方式是用 `PYTEST_CONFIG_FILE` 指向一份**不含 manager-api 块**的临时 yaml（不动现网配置）；同时本机缺 `opuslib_next`，用 `PYTHONPATH` 挂一个桩包：

```bash
PYTHONPATH=<stubs> PYTEST_CONFIG_FILE=<tmp.yaml> PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 \
  python -m pytest tests/core/providers/tts -q
# 29 passed in 0.41s
```

四个改动文件 `py_compile` 全部通过。

---

## 六、经排查**无需改动**的环节（已逐一验证）

| 环节                                               | 结论                                                                                                                                     |
| ------------------------------------------------ | -------------------------------------------------------------------------------------------------------------------------------------- |
| 配置项 key 名 `voice_instruction`                    | 三方一致：Java 写（`ConfigServiceImpl.java:556`）、DB 列（`202610070300.sql:12`）、Python 读（`doubao_v3.py:66`）。**问题在「写进请求体的位置」，不在 key 名**，故保留内部命名不动 |
| URL / method / `X-Api-Resource-Id` / `X-Api-Key` | 与官方一致                                                                                                                                  |
| `X-Api-Request-Id`                               | 官方标必选（uuid），现网已有，保留                                                                                                                    |
| `speech_rate` / `loudness_rate` 位置               | 现网放在 `audio_params` 内 —— **官方正确位置**，不要移到 `req_params` 顶层                                                                               |
| `code in (0, 20000000)` 判定                       | 与官方一致                                                                                                                                  |
| 分片解析 `raw_decode` / base64 补位                    | 与官方 `iter_lines`+`b64decode` 等价且更健壮，不动                                                                                                 |
| Java 主下发链路                                       | `ConfigServiceImpl.java:555-557` 已正确注入音色级指令                                                                                            |
| Java 试听链路                                        | `TtsPreviewController.java:87-105` **已**按 `getByVoiceCode` 反查并注入 `voice_instruction` / `dynamic_instruction` / `instruction_llm_id`    |
| `TimbreServiceImpl.getByVoiceCode:252`           | 已回填 `voiceInstruction`                                                                                                                 |
| 音色列表回显                                           | `VoiceDTO.java:38-45` 已有三字段，`TimbreServiceImpl.java:141-143` 已回填                                                                       |
| 前端 `/cc/`、`/admincc/`                            | 输入框、动态更新勾选框、LLM 下拉三者齐备，payload 用驼峰 `voiceInstruction` 与后端契约一致                                                                          |

---

## 七、残留建议（未改，需决策）

1. **`audio_params.format` 默认 `wav`**（`doubao_v3.py:58`，DB `202610071200.sql:12` 亦为 wav）：官方明确「流式场景推荐使用 pcm，**不建议使用 wav**」，wav 分片会重复携带 RIFF 头，拼接后可能出现杂音/时长错乱。建议改 `mp3`（最稳）或 `pcm`（流式最优）。**未改**是因为会改动现网音频产物格式，需先确认设备端解码兼容。  
   （补充评估：本接口是 **HTTP 单向流式**，不是 WebSocket 双向流式，分片在服务端已按整段合成后返回，客户端拼的是 base64 音频片段而非每片独立 RIFF，因此「重复 RIFF 头」在这个端点上不成立；且 15 个 TTS provider 中 13 个默认 wav，wav 并非异常值。真正的阻塞点是改 mp3 需要 pydub 依赖 **ffmpeg**，需先确认服务器已装。）
2. **非流式发送**：现网 `requests.post(json=...)` 无 `stream=True`，首包延迟 = 整段合成耗时。官方用 `data=json.dumps(payload), stream=True`。功能无影响，属性能项。
3. **`context_texts` 只有第 0 个元素生效**（官方明确）。若将来要同时传「上文」和「指令」，必须自行拼成**一条**文本，不能指望两个元素都生效。（当前实现正是只写 `context_texts[0]`。）
4. **复刻/克隆音色的 `resource_id` 仍需人工配置**：代码已补 `model = seed-tts-2.0-expressive`，但 `resource_id` 必须同时换成 `seed-icl-2.0`，否则 `context_texts` 仍无效；`seed-tts-2.0-standard` 明确不支持。此项属配置面，不在代码修复范围。
5. ~~**动态语气指令仍无 Python 消费方**~~ → **已在本次修复中闭环**（见第四节）。

---

## 八、部署与验收步骤

1. **数据库**：`manager-api` 启动时 Liquibase 会自动执行 `202610090130.sql`。若目标库已手工建过 `dynamic_instruction` / `instruction_llm_id`，先删掉这两行再启动（MySQL 无 `ADD COLUMN IF NOT EXISTS`，重复会报 Duplicate column）。
2. **重启** `manager-api`（8002）与 `xiaozhi-server`（8000 / 8003）。Python 侧 TTS provider 是**每连接一个实例**，不重启进程不会加载新代码。
3. **验收 A（固定指令）**：音色管理 → 选一个豆包 2.0 音色 → 填「语气指令」如 `用哭腔说话，声音哽咽，带着抽泣`，**不勾**动态更新 → 保存并绑定智能体 → 设备对话。抓 Python 侧日志确认请求体含 `additions: {"context_texts":[...]}`，且**不再出现** `voice_instruction` 顶层字段。
4. **验收 B（动态指令）**：勾选「动态更新」并选一个生成 LLM → 对话。日志应出现 `动态语气指令已更新: <指令>`；把开关关掉后下一轮应回落固定指令（日志不再出现该行）。
5. **验收 C（降级）**：故意把生成 LLM 的 key 填错 → 指令生成会失败，日志出现 `动态语气指令生成失败，回落固定指令`，但**对话本身不受影响**。

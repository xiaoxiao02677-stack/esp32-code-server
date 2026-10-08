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

---

## 三、为什么还要动数据库（第 4、5 项）

`TimbreEntity.java:48,51` 声明了 `dynamicInstruction` / `instructionLlmId`，但 `ai_tts_voice` 表**从未建过这两列**（`202610070300.sql` 只加了 `voice_instruction`）。MyBatis-Plus 的 `selectById` / `selectList` 按实体字段拼 SELECT，会抛：

```
SQLSyntaxErrorException: Unknown column 'dynamic_instruction' in 'field list'
```

异常点在 `ConfigServiceImpl.java:158` `timbreService.get(agent.getTtsVoiceId())`，**同一次查询里的 `voice_instruction` 连带取不到** —— 即使 provider 改对了，指令依然下不来。所以这两列必须补。

> 部署注意：MySQL 无 `ADD COLUMN IF NOT EXISTS`。若目标库已手工建过这两列，部署前请删除该 SQL 文件或注释掉对应行，否则 Liquibase 会报 Duplicate column。

---

## 四、验证

`conftest.py:92-116` 会因现网全模块部署（`data/.config.yaml` 配了 `manager-api`）拒绝跑 pytest，故用独立脚本 mock `requests.post` 验证（未改现网配置）：

```
1) 有指令时 req_params keys: ['additions', 'audio_params', 'speaker', 'text']
   additions 解析结果: {'context_texts': ['用哭腔说话，声音哽咽，带着抽泣']}
   [PASS] 指令已走 additions.context_texts[0]，且无非法字段
2) [PASS] 无指令时不带 additions
3) audio_params: {'format': 'mp3', 'sample_rate': 24000, 'speech_rate': 10, 'loudness_rate': -5}
   [PASS] speaker / audio_params / 分片拼接均正常，audio = b'AAABBB'
```

三个 Python 文件 `py_compile` 通过。

---

## 五、经排查**无需改动**的环节（已逐一验证）

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

## 六、残留建议（未改，需决策）

1. **`audio_params.format` 默认 `wav`**（`doubao_v3.py:58`，DB `202610071200.sql:12` 亦为 wav）：官方明确「流式场景推荐使用 pcm，**不建议使用 wav**」，wav 分片会重复携带 RIFF 头，拼接后可能出现杂音/时长错乱。建议改 `mp3`（最稳）或 `pcm`（流式最优）。**未改**是因为会改动现网音频产物格式，需先确认设备端解码兼容。
2. **非流式发送**：现网 `requests.post(json=...)` 无 `stream=True`，首包延迟 = 整段合成耗时。官方用 `data=json.dumps(payload), stream=True`。功能无影响，属性能项。
3. **`context_texts` 只有第 0 个元素生效**（官方明确）。若将来要同时传「上文」和「指令」，必须自行拼成**一条**文本，不能指望两个元素都生效。
4. **复刻/克隆音色**：需同时 `req_params.model = "seed-tts-2.0-expressive"`，且 `resource_id` 换 `seed-icl-2.0`，否则 `context_texts` 无效；`seed-tts-2.0-standard` 明确不支持。
5. **动态语气指令仍无 Python 消费方**：Java 已下发 `dynamic_instruction` / `instruction_llm_id`，但全仓 `xiaozhi-server` 无读取方，勾选「动态更新」目前还不产生实际效果。  

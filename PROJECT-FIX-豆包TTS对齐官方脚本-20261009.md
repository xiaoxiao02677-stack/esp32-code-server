# 修复：豆包 TTS 请求包严格对齐官方「声音复刻 V3」脚本

- 时间：2026-10-09
- 触发：用户贴出火山官方 声音复刻 V3 Python 脚本，要求「用户传入的语气指令 = CONTEXT_TEXTS 参数，和脚本对齐，用 json 去请求」
- 影响文件：`xiaozhi-server/core/providers/tts/doubao_v3.py`
- 服务器备份：`doubao_v3.py.bak-20261009T073304Z`
- 部署 md5：`2d0353eadc931b600c434c8a4990672d`

---

## 一、改了什么

以官方脚本为唯一基准，逐字段对齐 `_build_payload`。

### 1. 请求体结构（顶层三件套 + req_params 顺序）

```json
{
  "user": {"uid": "xiaozhi-esp32-server"},
  "req_params": {
    "text": "...",
    "speaker": "S_N8pC5xwg2",
    "audio_params": {"format","sample_rate","speech_rate","loudness_rate","emotion?"},
    "additions": "{\"context_texts\": [\"用户语气指令\"]}"
  },
  "namespace": "BidirectionalTTS"
}
```

`speaker` 从「audio_params 之后」移到官方脚本的位置（text → speaker → audio_params）。

### 2. 用户语气指令 → `additions.context_texts`（核心）

`instruction = self._dynamic_instruction or self.voice_instruction`，
即 `connection.py:1224 set_dynamic_instruction()` 每轮注入的值优先，
回落到音色的固定 `voice_instruction`。最终写成：

```python
additions["context_texts"] = [instruction]   # 官方明确「只第一个值有效」
```

### 3. 删掉三个非官方字段（改为默认不发送）

| 字段 | 改前 | 改后 |
|---|---|---|
| `req_params.model` | 复刻音色强制发 `seed-tts-2.0-expressive` | **默认不发**；配置里显式写 `model` 才发 |
| `audio_params.enable_emotion` | 强制发 `True` | **默认不发**；显式配置才发 |
| `audio_params.emotion_scale` | 强制发（默认 4） | **默认不发**；显式配置才发（仍钳制 1~5） |

官方脚本 `req_params` 里没有 `model`；`audio_params` 里只有 `emotion` 一个情感字段：

```python
# 官方脚本
if EMOTION: req_params["audio_params"]["emotion"] = EMOTION
```

### 4. `explicit_language` 默认留空

官方脚本 `EXPLICIT_LANGUAGE = ""`（注释「中文可不填」）。改前我们默认填 `"zh"`，
导致 `additions` 永远非空。改为默认 `None`，中文场景不发送。

### 5. 流解析修掉官方脚本的大小写坑

官方脚本终止判定是 `code == 20000000 and message == "ok"`，
但**实测火山返回的结束 message 是 `"OK"`（大写）**，官方脚本这个分支永远不命中，
实际是靠「流读完」退出的。

改造后：先收尾片 data，再判 `message.strip().lower() == "ok"` 才 break；
message 文案变化也不报错、不丢数据，靠流结束自然退出。

```python
if code == 20000000:
    if data: audio.extend(...)
    if str(obj.get("message") or "").strip().lower() == "ok":
        break
    continue
```

---

## 二、实测结论（重要）

### 火山 TTS 输出是**非确定性**的

同一份请求连跑两次，md5 完全不同：

```
A 基线 run1  27885B  md5=0d2bc9b0ff0c0f48
A 基线 run2  27693B  md5=3b29c7d547efe704   -> 两次不同
```

**推论**：任何基于文件大小 / md5 / 波形 rms 的 A/B 判定都是噪声，全部无效。
「字段是否生效」只能人耳试听，程序无法自动验证。
（之前用 md5 比对得出的「所有字段都生效」是假结论，已作废。）

### 服务器线上实测：5/5 出音频

部署后用项目真实的 `TTSProvider` 驱动（服务器网络、真实 API Key）：

| 用例 | 发出的 emotion | context_texts | 音频 |
|---|---|---|---|
| 01 基线 | — | — | 27693 B ✔ |
| 02 固定指令·开心 | `happy` | ✓ | 24429 B ✔ |
| 03 动态指令·生气 | `angry` | ✓ | 27885 B ✔ |
| 04 动态指令·难过 | `sad` | ✓ | 27693 B ✔ |
| 05 显式 model（回退验证） | `happy` | ✓ | 29229 B ✔ |

去掉 `model` / `enable_emotion` / `emotion_scale` 后**全部正常出音频**，
无报错、无空音频。

---

## 三、顺带修好的测试基础设施

`tests/core/providers/tts/test_doubao_v3.py` 的 `_chunked_response()` 只设了
`status_code` 和 `text`，**没给 Mock 配 `iter_lines`**，而 provider 正是用
`resp.iter_lines(decode_unicode=True)` 读流的。

结果：整个测试套件以 `'Mock' object is not iterable` 全军覆没 ——
**改动前 20 failed / 2 passed，改动后同样 20 failed / 2 passed**（已用备份版验证，
确认是预存在缺陷，非本次引入）。

修复：

```python
resp.iter_lines = lambda **kwargs: iter(body.splitlines())
```

并新增 `_mock_response()` 用于畸形分片等异常场景。
修复后 **22 passed**。

新增/改写的用例：

- `test_clone_resource_has_no_model_by_default` — 复刻音色默认不带 model
- `test_model_sent_only_when_explicitly_configured` — 显式配置才发
- `test_no_explicit_language_by_default` — 对齐官方，默认不发
- `test_emotion_only_field_by_default` — 只发 emotion 单字段
- `test_emotion_extras_sent_only_when_configured` — extra 仅在配置时发（scale 9 → 钳到 5）

---

## 四、给用户自测的独立脚本

`G:/demo/21_xiaozhi/tts_voice_probe.py`（只依赖 `requests`），与线上请求包逐字段一致，
7 个用例产物在 `tts_out/`。顶部有三个开关可做 A/B：

```python
USE_MODEL = False          # True → 加 model=seed-tts-2.0-expressive
USE_EMOTION_SCALE = False  # True → 加 enable_emotion + emotion_scale
EXPLICIT_LANGUAGE = ""     # 官方脚本默认留空
```

---

## 五、遗留问题

1. **音色「清清」的 `voice_instruction` 仍是垃圾文本** `大幅度发大幅度发的`
   —— 无任何情感关键词，`infer_emotion()` 返回 None，不会发 `emotion` 字段。
   需要在后台改成含情感词的指令，或给该音色开 `dynamic_instruction=1`。
2. 情感是否真的生效**无法程序验证**，需用户人耳试听确认。
3. 若试听后发现 `context_texts` 单独不够、必须配 `model`，
   只需在 TTS 模型配置里加 `model: seed-tts-2.0-expressive` 即可回退。

---

## 六、本地跑 pytest 的环境坑（备忘）

在本机跑这个项目测试需要绕四个坑：

1. `conftest.py` 检测到全模块部署会 `sys.exit(3)` → 用 `--noconftest`，
   并临时清空 `data/.config.yaml` 的 `manager-api` 块（否则会去连 127.0.0.1:8002）
2. `opuslib_next` 缺 Windows 原生 libopus → PYTHONPATH 前置 stub 包
3. Python 3.13 移除了 `audioop`，pydub 导不进 → PYTHONPATH 前置 stub 包
   两者 stub 位于 `G:/demo/21_xiaozhi/.workbuddy/pystubs/`

完整命令：

```bash
cd G:/demo/21_xiaozhi/code-server-mirror/xiaozhi-server
PYTHONPATH="G:/demo/21_xiaozhi/.workbuddy/pystubs" \
  <venv>/Scripts/python.exe -m pytest tests/core/providers/tts/test_doubao_v3.py -q --noconftest
```

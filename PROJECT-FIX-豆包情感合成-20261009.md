# 豆包声音复刻「语气指令 / 情感」修复报告

日期：2026-10-09
范围：`xiaozhi-server/core/providers/tts/doubao_v3.py`
结论：**已按火山官方 声音复刻 V3 脚本的通信方式重写请求体，并已上线验证通过。**

---

## 一、先说结论：为什么你的脚本行、项目里不行

项目原来**只发了一条通道**——`additions.context_texts`，而你的脚本发的是**三条通道叠加**：
`emotion 三件套` + `context_texts` + `explicit_language`，外加顶层 `namespace`。

`context_texts` 本质是「上下文参考文本」，用来让模型参考前文语气，它**不是情感开关**。
真正的情感强度控制是 `audio_params.emotion / enable_emotion / emotion_scale`。
项目一个都没发，所以听起来「指令没起作用」。

### 关键澄清：两边都不是「请求失败」

用你的真实 api_key 对**同一个复刻音色 `S_N8pC5xwg2`** 做 A/B，两个 payload **都返回 200 + 正常音频**：

| 变体 | HTTP | 音频字节 |
|---|---|---|
| 你的官方 payload（namespace+emotion+explicit_language） | 200 | 24621 |
| 项目原 payload（仅 context_texts + model） | 200 | 25965 |
| 官方去掉 namespace | 200 | 27693 |
| 官方去掉 emotion | 200 | 27693 |
| 官方去掉 explicit_language | 200 | 27693 |

也就是说：**服务端从不报错，只是韵律不一样**。这正是最难排查的一类问题——静默退化。

---

## 二、实测发现的硬坑（文档里没写）

用 `format=pcm` 直采波形（24kHz）定量测了一遍：

### 1. `emotion_scale` 只在 **1~5** 有效，越界直接返回**空音频**

| scale | 结果 |
|---|---|
| 0 | **0 字节**（code 正常，data 全空） |
| 1 | 正常 |
| 3 | 正常 |
| 5 | 正常 |
| **6** | **0 字节** |
| **10 / 100** | **0 字节** |

这是静默失败：HTTP 200、code 正常，但一个字节音频都没有。
新实现已强制钳制到 `[1,5]`（实测 `emotion_scale=99 → 5`）。

### 2. 非法 `emotion` 值被**静默忽略**

测了 `garbage_value`、`开心`（中文）等 23 个取值，全部返回 200 + 音频，无报错。
所以**不能靠报错来校验枚举**，只能严格使用官方英文枚举。

### 3. `namespace: BidirectionalTTS` 在复刻与非复刻下都安全

| 资源 | 音色 | namespace | 结果 |
|---|---|---|---|
| seed-tts-2.0 | 官方预置音色 | 无 | OK |
| seed-tts-2.0 | 官方预置音色 | 有 | OK |
| seed-icl-2.0 | S_ 复刻 | 无 | OK |
| seed-icl-2.0 | S_ 复刻 | 有 | OK |

因此新实现**默认无条件带上** `namespace`，与你的脚本完全一致。

### 4. 结束标记是 `OK` 不是 `ok`

火山返回的结束帧 `message` 是 **`OK`（大写）**。官方脚本里 `message == "ok"` 的判定实际不匹配。
新实现**只判 `code == 20000000`**，避免大小写差异导致误判为错误。

---

## 三、改了什么（字段级对照）

| 位置 | 你的脚本 | 项目（改前） | 项目（改后） |
|---|---|---|---|
| 顶层 `namespace` | `BidirectionalTTS` | ❌ 缺失 | ✅ 默认 `BidirectionalTTS` |
| `req_params.emotion` | `happy` 等 | ❌ 缺失 | ✅ 配置指定 + 指令自动推断 |
| `req_params.enable_emotion` | `True` | ❌ 缺失 | ✅ 随 emotion 一起发 |
| `req_params.emotion_scale` | 4~5 | ❌ 缺失 | ✅ 默认 4，钳制 [1,5] |
| `additions.explicit_language` | `zh` | ❌ 缺失 | ✅ 默认 `zh` |
| `additions.context_texts` | 有 | ✅ 有 | ✅ 有（保留） |
| `req_params.model` | 未发 | 仅 seed-icl 时补 | ✅ seed-icl **或** S_ 音色时补 `seed-tts-2.0-expressive` |
| `custom_speaker_id` | postpaid 用 | ❌ 缺失 | ✅ `speaker_type=postpaid` 时启用 |
| 请求方式 | `stream=True` + `iter_lines` | `response.text` + `raw_decode` | ✅ `stream=True` + `iter_lines(decode_unicode=True)` |
| 终止判定 | `code==20000000` | `code not in (0,20000000)` 抛错 | ✅ `code==20000000` 终止 |
| `emotion_scale` 越界 | 未处理 | 未处理 | ✅ 钳制，杜绝空音频 |

### 情感自动推断（核心新增）

你说"用户输入语气指令"——现在**中文指令会自动映射到官方 emotion 枚举**，不用你手写英文：

| 指令关键词 | 推断出的 emotion |
|---|---|
| 开心 / 高兴 / 快乐 / 愉快 / 雀跃 / 笑 / 甜 | `happy` |
| 难过 / 伤心 / 悲伤 / 沮丧 / 哭 / 委屈 | `sad` |
| 生气 / 愤怒 / 恼火 / 暴躁 / 发火 / 训斥 | `angry` |
| 害怕 / 恐惧 / 惊慌 / 紧张 / 发抖 | `scared` |
| 惊讶 / 震惊 / 意外 / 没想到 | `surprised` |
| 厌恶 / 讨厌 / 嫌弃 / 鄙视 / 不屑 | `hate` |
| 激动 / 亢奋 / 热血 / 振奋 / 欢呼 | `excited` |
| 冷淡 / 冷漠 / 高冷 / 敷衍 / 无所谓 | `coldness` |
| 平静 / 平淡 / 中性 / 自然 / 客观 | `neutral` |

推断结果**叠加在 `context_texts` 之上**——两条通道同时发，和你脚本一致。

---

## 四、线上实测（服务器网络 · 真实 API · 你的密钥）

部署后直接用服务器 venv 解释器跑的真实结果：

| 用例 | namespace | emotion | scale | 音频字节 |
|---|---|---|---|---|
| 01 基线无指令 | BidirectionalTTS | — | — | 30957 |
| 02「用非常开心、兴奋、雀跃的语气说话」 | BidirectionalTTS | **happy** | 4 | 25965 |
| 03「用很生气愤怒的语气说话」 | BidirectionalTTS | **angry** | 4 | 27885 |
| 04「用难过伤心的语气说话」 | BidirectionalTTS | **sad** | 4 | 30957 |
| 05 现网 DB 指令「大幅度发大幅度发的」 | BidirectionalTTS | —（无关键词，不猜） | — | 32301 |
| 06 越界 `emotion_scale=99` | BidirectionalTTS | happy | **5**（已钳制） | 25965 |

全部产出有效音频，无一条空音频。

---

## 五、部署信息

| 项 | 值 |
|---|---|
| 文件 | `/root/xiaozhi-server/main/xiaozhi-server/core/providers/tts/doubao_v3.py` |
| 备份 | `doubao_v3.py.bak-20261008T195327Z` |
| md5 | `1a301b4c0d02d8d0bfb908021e41985d`（本地/远端一致） |
| 编译 | `python3 -m py_compile` 通过 |
| 服务 | `systemctl restart xiaozhi-server` → `active` |
| 生效确认 | 文件落盘 03:53:33，进程启动 03:53:37，**新代码已加载** |
| 端口 | 8000 / 8003 正常监听（pid 68637） |
| 日志 | 近 200 行无 error / traceback |
| **配置改动** | **无**。默认值即可工作，不需要改数据库 |

现网音色配置（取自 `ai_model_config`）：

```json
{"type":"doubao_v3","format":"mp3","api_key":"d9f77...",
 "api_url":"https://openspeech.bytedance.com/api/v3/tts/unidirectional",
 "speaker":"S_N8pC5xwg2","resource_id":"seed-icl-2.0","sample_rate":"24000"}
```

---

## 六、可选配置项（都不配也能用）

| 键 | 默认 | 说明 |
|---|---|---|
| `emotion` | 无 | 强制指定情感，优先级高于自动推断 |
| `enable_emotion` | `true` | 情感总开关 |
| `emotion_scale` | `4` | 情感强度，钳制 [1,5] |
| `auto_emotion` | `true` | 是否从语气指令自动推断 emotion |
| `explicit_language` | `zh` | 显式语言 |
| `namespace` | `BidirectionalTTS` | 传空串可关闭 |
| `speaker_type` | `prepaid` | 后付费复刻设为 `postpaid` |
| `custom_speaker_id` | 无 | `postpaid` 时必填 |

---

## 七、还需要你做的一件事

数据库里音色「清清」的语气指令目前是 **`大幅度发大幅度发的`**（显然是测试乱码），
它不含任何情感关键词 → 推断不出 emotion → 只有 `context_texts` 生效。

建议在管理后台改成人话，例如：
`用温柔、亲切、略带开心的语气说话`，或打开该音色的**动态指令**（`dynamic_instruction=1`）让 LLM 每轮生成。

---

## 八、验证产物

本地生成的对照音频（可直接试听对比）：

- `v3_01_无指令.mp3` — 基线
- `v3_02_开心指令.mp3` — emotion=happy
- `v3_03_生气指令.mp3` — emotion=angry
- `v3_04_难过指令.mp3` — emotion=sad
- `v3_05_中性指令.mp3` — emotion=neutral
- `v3_06_越界scale99.mp3` — 钳制到 5 后的产物

脚本：`.workbuddy/ab_tts_test.py`、`ab_tts_pcm.py`、`probe_emotion.py`、
`probe_emotion_pcm.py`、`probe_ns.py`、`test_doubao_v3_new.py`、
`server_tts_probe.py`、`deploy_tts_emotion.py`

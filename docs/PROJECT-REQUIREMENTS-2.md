# 需求说明：音色语气指令「动态更新」 + ESP32 固件去小智特征

> 版本：v1.0 · 生成日期：2026-10-08
> 配套：前序 `PROJECT-REQUIREMENTS.md`（CC 控制台 4 项诉求 PRD）、`PROJECT-HANDOFF.md`
> 范围：两类工作项 —— **A.** `/cc/` 音色「语气指令」增强 + 已知缺陷；**B.** ESP32 固件去除可观测的 `yuhe` 品牌特征。
> 所有结论均锚定真实代码证据（附 `文件:行号`）。

---

## 1. 现状核查（关键证据）

### 1.1 `/cc/` 音色「语气指令」字段与缺陷线索
- 字段位置：音色编辑模态中 `<input v-model.trim="editVoice.voiceInstruction">`，标签「语气指令（doubao 2.0 音色生效，如「用标准大陆普通话说话」）」—— `cc-console/src/App.vue:914-915`。
- 保存链路：前端 `saveVoice()` **已携带** `voiceInstruction`（App.vue:1333 `voiceInstruction: ev.voiceInstruction || ''`）。
- **缺陷根因假设**：前端已传值，但用户反馈「填入音色提示词没有更新」。结合代码，根因大概率落在**后端落库**环节——`PUT /models/{ttsModelId}/voices` 的 DB 表 `tts_voice` 可能无 `voice_instruction` 列，或 Mapper/Entity 未映射该字段，或编辑回填时未读取。需在实现前用 DB schema + Mapper 核实（见 FR-A.0）。

### 1.2 ESP32 固件中可观测的 `yuhe` 特征清单
逐项来自 `yuhe-esp32/main/` 实测：

| 类别 | 证据 | 可观测性 |
|---|---|---|
| 唤醒词音频 | `wake_word="你好小智"` 硬编码于 `boards/bread-compact-esp32/esp32_bread_board.cc:116`、`boards/bread-compact-esp32-lcd/esp32_bread_board_lcd.cc:148`；模型二进制 `wakenet9l_tts1h8_你好小智_3_0.631_0.635`（用户监听输出直接证据）| ** audible（被听到）** |
| WS 接入路径 | `ws://sandyun.top:8001/yuhe/v1/` —— `main/application.cc:863`；服务端同路径硬编码 `app.py:110`、`config.yaml:20`、`core/http_server.py:124`、`core/api/ota_handler.py:141` | 网络可嗅探 |
| 设备 ID 前缀 | `device_id_ = "yuhe-" + compact;` —— `main/yh/yh_protocol.cc:77` | 网络可嗅探 |
| 内容过滤域名 | `std::strstr(content, "yuhe.me")` —— `main/display/emote_display.cc:148` | 服务端/日志可见 |
| 品牌注释 | `main/yh/yh_protocol.h:9-11`「小智固件」「小智原有 AI/ASR/TTS…」等 | 源码/审计可见 |

> 注：内部标识符 `CONFIG_YUHE_*`、`xiaozhi-fonts` 组件、`YUHE_I2S_PORT` 宏（`main/audio/audio_codec.h:22-24` 等）属**编译期符号**，不在"监听时看到"的可观测范畴，且移除会破坏构建——**不列入本次去品牌范围**（见 §3.4 边界）。

---

## 2. 需求 A：音色语气指令「动态更新」

### A.0 先决缺陷修复
- **FR-A.0.1** 核实 `tts_voice` 表是否存在 `voice_instruction` 列；若不存在，通过 Liquibase changelog 新增列（遵循 `PROJECT-HANDOFF.md` 的 changelog 惯例，禁止手改表）。
- **FR-A.0.2** 核实 `PUT /models/{ttsModelId}/voices` 的 Mapper/Entity 是否映射 `voiceInstruction`；修复使写入与编辑回填一致。
- **FR-A.0.3** 验收：在音色模态填写「语气指令」→ 保存 → 重新打开该音色，值仍在；调用 TTS 试听（`/api/tts/preview`，doubao 2.0 音色）能体现该指令。

### A.1 「动态更新」开关（核心新增）
- **FR-A.1.1** 在语气指令输入框**旁**新增一个大号勾选框，文案「动态更新」（视觉权重高于普通复选框，符合用户描述"大对勾的选项"）。
- **FR-A.1.2** 勾选后，原地展开一个 **LLM 选择下拉**（数据来源复用 `modelOptions.LLM`，即 `GET /models/names?modelType=LLM`）+「生成语气指令」按钮。
- **FR-A.1.3** 点击生成：调用**新增后端端点**（建议 `POST /agent/tone/generate` 或复用智能体对话），该端点读取**①短期聊天记录**（`/agent/{agentId}/chat-history/{sessionId}`）+ **②长期记忆**（`/memory/facts`）→ 交由所选 LLM 生成一段「语气指令」→ 回填到 `editVoice.voiceInstruction` 输入框。
- **FR-A.1.4** 生成约束（prompt 层面）：语气指令**尽量口语化、简短、像真人说话习惯**（呼应现有 placeholder「用标准大陆普通话说话」风格）。
- **FR-A.1.5** **未勾选**时：`voiceInstruction` 保持用户固定手填值，**绝不自动变更**，直到用户再次勾选并生成。
- **FR-A.1.6** 动态标志位随音色存档（建议在 `tts_voice` 表增 `dynamic_tone` 布尔列，或并入 `voice_instruction` 生成策略），编辑回填时恢复开关状态。
- **FR-A.1.7** 生成中展示 loading，失败弹具体错误（`res.msg`），不静默。

### A.2 后端依赖（需新增/确认）
- 端点需聚合：短期会话拉取 + 长期记忆拉取 + LLM 调用（可复用 `llmPreview` 同类通道）。
- 若服务端无现成聚合接口，需在 `manager-api` 或 `yuhe-server` 新增，并纳入 API 调试目录（§2 现状已含 `llmPreview` 先例）。

### A.3 验收
- [ ] 填固定语气指令并保存 → 重开仍在（FR-A.0）。
- [ ] 勾「动态更新」→ 出现 LLM 下拉 + 生成按钮。
- [ ] 选 LLM + 生成 → 语气指令框被口语化文本填充，且试听音色风格变化。
- [ ] 取消勾选 → 指令固定为上一次值，不自动改写。

---

## 3. 需求 B：ESP32 固件去小智特征

### B.1 唤醒词（最高优先，被用户直接听到）
- **FR-B.1.1** 将板级硬编码 `wake_word="你好小智"` 改为自定义唤醒词（如客户指定词），涉及文件 `esp32_bread_board.cc:116`、`esp32_bread_board_lcd.cc:148`（及所有 board 变体中同类赋值）。
- **FR-B.1.2** 同步更换 **wakenet 唤醒词模型二进制**：当前加载 `wakenet9l_tts1h8_你好小智_...`，需替换为与自定义词对应的训练模型（放在模型分区 / `srmodel` 加载路径）。
- **FR-B.1.3** 验收：监听设备唤醒，不再出现「你好小智」音频；`make` 加载的 wakenet 模型名不含「你好小智」。

### B.2 网络标识去品牌
- **FR-B.2.1** 设备侧 WS 路径 `/yuhe/v1/`（`application.cc:863`）改为自定义路径（如 `/yh/v1/`）；**必须同步**服务端四处硬编码：`app.py:110`、`config.yaml:20`、`core/http_server.py:124`、`core/api/ota_handler.py:141`（否则设备无法连接）。
- **FR-B.2.2** 设备 ID 前缀 `"yuhe-"`（`yh_protocol.cc:77`）改为自定义前缀（如 `"yh-"`）。
- **FR-B.2.3** 内容过滤中对 `"yuhe.me"` 的硬编码引用（`emote_display.cc:148`）移除或替换为自定义域名判断。

### B.3 品牌注释清理
- **FR-B.3.1** 删除源码注释中明确「小智」品牌表述（如 `yh_protocol.h:9-11` 的「小智固件」「小智原有 AI/ASR/TTS…」），改为中性/自研描述。

### B.4 范围边界（重要）
- **FR-B.4.1** 内部编译符号 `CONFIG_YUHE_*`、`xiaozhi-fonts`、`YUHE_I2S_PORT` 等**不在本次去品牌范围**——它们不可观测且移除会导致编译失败。
- **FR-B.4.2** 若用户后续要求"全量重命名"（含内部符号），须单独评估：涉及 Kconfig、组件名、宏、sdkconfig 重命名脚本（`main/sdkconfig.rename`），工作量与回归风险显著，需另立变更。

### B.5 验收
- [ ] 监听唤醒：无「你好小智」音频，模型名无该词。
- [ ] 网络抓包：WS 路径、设备 ID 前缀均不含 `yuhe`/`小智`。
- [ ] 源码 grep `小智`/`yuhe`（排除内部符号与文档目录）零命中。
- [ ] 固件正常编译、设备正常联调（OTA/对话不受影响）。

---

## 4. 风险与待确认项

1. **自定义唤醒词模型来源**：`wakenet9l_tts1h8_你好小智_...` 是训练好的二进制，替换需客户提供/训练对应自定义词模型（或改用 ESP-SR 自定义命令词流程 `CONFIG_CUSTOM_WAKE_WORD`）。**阻塞 FR-B.1.2**。
2. **WS 路径耦合**：FR-B.2.1 是固件+服务端双端改动，须一起发版，否则设备掉线。
3. **后端 tone 生成端点**：FR-A.1.3 依赖新增聚合接口，需确认由我方在 `manager-api` 实现，还是已有内部接口可复用。
4. **去品牌范围**：是否接受"仅去可观测特征"（本文默认），还是要求内部符号全量重命名（FR-B.4.2），需用户拍板。
5. **语音提示词 vs 语气指令术语**：用户表述混用"音色提示词/语气指令"，本文统一为 `voiceInstruction`（音色级语气指令）；若用户实际指"人设提示词(systemPrompt)"，需校正（systemPrompt 保存链路已正常，见 App.vue:1570）。

---

## 5. 验收总表（交付时勾选）

| 编号 | 验收点 | 状态 |
|---|---|---|
| A.0 | 语气指令固定值保存生效 | ☐ |
| A.1 | 动态更新勾选 + LLM 生成口语化语气指令 | ☐ |
| A.2 | 未勾选时语气指令不自动变 | ☐ |
| B.1 | 唤醒词无「你好小智」 | ☐ |
| B.2 | WS 路径/设备ID 无 yuhe（含服务端同步）| ☐ |
| B.3 | 源码品牌注释清理 | ☐ |
| B.4 | 固件编译+联调正常 | ☐ |

> 下一步：确认 §4 待确认项（尤其 自定义唤醒词模型、tone 端点归属、去品牌范围）后，按 B.1（唤醒词）→ A.0（缺陷）→ A.1（动态更新）→ B.2/B.3 顺序实现。
